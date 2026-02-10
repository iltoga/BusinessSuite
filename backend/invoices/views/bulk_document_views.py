import json
import time

from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.files.storage import default_storage
from django.http import JsonResponse, StreamingHttpResponse
from django.urls import reverse
from django.views import View

from invoices.models import Invoice, InvoiceDocumentItem, InvoiceDocumentJob
from invoices.tasks.document_jobs import run_invoice_document_job


class InvoiceBulkDocumentCreateView(PermissionRequiredMixin, View):
    permission_required = ("invoices.view_invoice",)

    def post(self, request, *args, **kwargs):
        format_type = request.POST.get("format", "docx").lower()
        if format_type not in [InvoiceDocumentJob.FORMAT_DOCX, InvoiceDocumentJob.FORMAT_PDF]:
            return JsonResponse({"error": "Invalid format. Use 'docx' or 'pdf'."}, status=400)

        invoice_ids = request.POST.getlist("invoice_ids")
        if not invoice_ids and request.body:
            try:
                payload = json.loads(request.body.decode("utf-8"))
                invoice_ids = payload.get("invoice_ids", [])
                format_type = payload.get("format", format_type).lower()
            except Exception:
                invoice_ids = []

        if format_type not in [InvoiceDocumentJob.FORMAT_DOCX, InvoiceDocumentJob.FORMAT_PDF]:
            return JsonResponse({"error": "Invalid format. Use 'docx' or 'pdf'."}, status=400)

        if isinstance(invoice_ids, str):
            invoice_ids = [val.strip() for val in invoice_ids.split(",") if val.strip()]

        if not invoice_ids:
            return JsonResponse({"error": "No invoice IDs provided."}, status=400)

        invoices = list(Invoice.objects.filter(id__in=invoice_ids).select_related("customer"))
        if len(invoices) != len(invoice_ids):
            return JsonResponse({"error": "One or more invoices not found."}, status=404)

        invoice_map = {str(inv.id): inv for inv in invoices}

        job = InvoiceDocumentJob.objects.create(
            status=InvoiceDocumentJob.STATUS_QUEUED,
            format_type=format_type,
            total_invoices=len(invoice_ids),
            created_by=request.user,
            request_params={"invoice_ids": invoice_ids},
        )

        for index, invoice_id in enumerate(invoice_ids, start=1):
            invoice = invoice_map[str(invoice_id)]
            InvoiceDocumentItem.objects.create(
                job=job,
                sort_index=index,
                invoice=invoice,
                status=InvoiceDocumentItem.STATUS_QUEUED,
            )

        run_invoice_document_job(str(job.id))

        return JsonResponse(
            {
                "job_id": str(job.id),
                "status": job.status,
                "status_url": reverse("invoice-bulk-download-status", kwargs={"job_id": str(job.id)}),
                "stream_url": reverse("invoice-bulk-download-stream", kwargs={"job_id": str(job.id)}),
                "download_url": reverse("invoice-bulk-download-file", kwargs={"job_id": str(job.id)}),
            },
            status=202,
        )


class InvoiceBulkDocumentStatusView(PermissionRequiredMixin, View):
    permission_required = ("invoices.view_invoice",)

    def get(self, request, job_id, *args, **kwargs):
        try:
            job = InvoiceDocumentJob.objects.get(id=job_id)
        except InvoiceDocumentJob.DoesNotExist:
            return JsonResponse({"error": "Job not found."}, status=404)

        items = job.items.select_related("invoice", "invoice__customer").order_by("sort_index")
        data = {
            "job_id": str(job.id),
            "status": job.status,
            "progress": job.progress,
            "total": job.total_invoices,
            "processed": job.processed_invoices,
            "download_url": reverse("invoice-bulk-download-file", kwargs={"job_id": str(job.id)}),
            "items": [
                {
                    "invoice_id": item.invoice_id,
                    "invoice_no": item.invoice.invoice_no_display,
                    "customer_name": item.invoice.customer.full_name,
                    "status": item.status,
                    "error": item.error_message,
                }
                for item in items
            ],
        }

        if job.status == InvoiceDocumentJob.STATUS_FAILED:
            data["error"] = job.error_message or "Job failed"

        return JsonResponse(data)


class InvoiceBulkDocumentStreamView(PermissionRequiredMixin, View):
    permission_required = ("invoices.view_invoice",)

    def get(self, request, job_id, *args, **kwargs):
        response = StreamingHttpResponse(self._stream_job(job_id), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response

    def _stream_job(self, job_id):
        sent_states = {}
        try:
            job = InvoiceDocumentJob.objects.get(id=job_id)
        except InvoiceDocumentJob.DoesNotExist:
            yield self._send_event("error", {"message": "Job not found"})
            return

        yield self._send_event(
            "start",
            {
                "total": job.total_invoices,
                "message": f"Starting document generation for {job.total_invoices} invoice(s)...",
            },
        )

        while True:
            job.refresh_from_db()
            items = list(job.items.select_related("invoice", "invoice__customer").order_by("sort_index"))

            for item in items:
                state = sent_states.get(item.id, {"file_start": False, "done": False})

                if item.status == InvoiceDocumentItem.STATUS_PROCESSING and not state["file_start"]:
                    yield self._send_event(
                        "file_start",
                        {
                            "index": item.sort_index,
                            "invoice_id": item.invoice_id,
                            "message": f"Generating document for {item.invoice.invoice_no_display}...",
                        },
                    )
                    state["file_start"] = True

                if (
                    item.status in [InvoiceDocumentItem.STATUS_COMPLETED, InvoiceDocumentItem.STATUS_FAILED]
                    and not state["done"]
                ):
                    if item.status == InvoiceDocumentItem.STATUS_COMPLETED:
                        event_type = "file_success"
                        message = f"✓ Generated {item.invoice.invoice_no_display}"
                    else:
                        event_type = "file_error"
                        message = f"✗ Failed {item.invoice.invoice_no_display}: {item.error_message or 'Unknown error'}"

                    yield self._send_event(
                        event_type,
                        {
                            "index": item.sort_index,
                            "invoice_id": item.invoice_id,
                            "message": message,
                            "status": item.status,
                        },
                    )
                    state["done"] = True

                sent_states[item.id] = state

            if job.processed_invoices >= job.total_invoices and all(state["done"] for state in sent_states.values()):
                yield self._send_event(
                    "complete",
                    {
                        "message": "Document generation complete",
                        "download_url": reverse("invoice-bulk-download-file", kwargs={"job_id": str(job.id)}),
                        "status": job.status,
                    },
                )
                break

            yield ": keep-alive\n\n"
            time.sleep(0.5)

    @staticmethod
    def _send_event(event_type, data):
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


class InvoiceBulkDocumentDownloadView(PermissionRequiredMixin, View):
    permission_required = ("invoices.view_invoice",)

    def get(self, request, job_id, *args, **kwargs):
        try:
            job = InvoiceDocumentJob.objects.get(id=job_id)
        except InvoiceDocumentJob.DoesNotExist:
            return JsonResponse({"error": "Job not found."}, status=404)

        if job.status != InvoiceDocumentJob.STATUS_COMPLETED or not job.output_path:
            return JsonResponse({"error": "Job not completed yet."}, status=400)

        file_handle = default_storage.open(job.output_path, "rb")
        response = StreamingHttpResponse(file_handle, content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="invoice_documents_{job.id}.zip"'
        return response
