import json
import logging
import time

from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.files.storage import default_storage
from django.http import FileResponse, HttpResponse, JsonResponse, StreamingHttpResponse
from django.urls import reverse
from django.utils.text import slugify
from django.views.generic import View

from core.services.logger_service import Logger
from core.utils.pdf_converter import PDFConverter, PDFConverterError
from invoices.models import Invoice, InvoiceDownloadJob
from invoices.services.InvoiceService import InvoiceService
from invoices.tasks.download_jobs import run_invoice_download_job

logger = Logger.get_logger(__name__)


class InvoiceDownloadView(View):
    def get(self, request, *args, **kwargs):
        pk = kwargs.get("pk")
        format_type = request.GET.get("format", "docx").lower()

        # Validate format parameter
        if format_type not in ["docx", "pdf"]:
            return HttpResponse("Invalid format. Use 'docx' or 'pdf'.", status=400)

        try:
            invoice = Invoice.objects.get(pk=pk)
        except Invoice.DoesNotExist:
            return HttpResponse(f"Invoice with ID {pk} not found.", status=404)

        invoice_service = InvoiceService(invoice)

        # if payment is complete, generate the full invoice
        if invoice.total_paid_amount == 0 or invoice.is_payment_complete:
            data, items = invoice_service.generate_invoice_data()
            buf = invoice_service.generate_invoice_document(data, items)
        else:
            data, items, payments = invoice_service.generate_partial_invoice_data()
            buf = invoice_service.generate_invoice_document(data, items, payments)

        # Build a safe filename containing the invoice display and the customer full name.
        # Use django's slugify to remove/replace special characters then convert hyphens to underscores.
        raw_name = f"{invoice.invoice_no_display}_{invoice.customer.full_name}"
        safe_name = slugify(raw_name, allow_unicode=False).replace("-", "_") or f"Invoice_{pk}"
        # Limit filename length to avoid filesystem issues
        safe_name = safe_name[:200]

        # Return DOCX directly if requested
        if format_type == "docx":
            return FileResponse(buf, as_attachment=True, filename=f"{safe_name}.docx")

        # Convert to PDF using LibreOffice (via PDFConverter utility)
        try:
            pdf_bytes = PDFConverter.docx_buffer_to_pdf(buf)
            response = HttpResponse(pdf_bytes, content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="{safe_name}.pdf"'
            return response

        except PDFConverterError as e:
            logger.error(f"PDF conversion failed for invoice {pk}: {e}")
            return HttpResponse(
                f"PDF conversion failed: {str(e)}. " "Please ensure LibreOffice is installed in the container.",
                status=500,
            )


class InvoiceDownloadAsyncStartView(PermissionRequiredMixin, View):
    permission_required = ("invoices.view_invoice",)

    def post(self, request, *args, **kwargs):
        pk = kwargs.get("pk")
        format_type = request.POST.get("format", "pdf").lower()

        if request.body and not request.POST:
            try:
                payload = json.loads(request.body.decode("utf-8"))
                format_type = payload.get("format", format_type).lower()
            except Exception:
                format_type = format_type

        if format_type not in [InvoiceDownloadJob.FORMAT_DOCX, InvoiceDownloadJob.FORMAT_PDF]:
            return JsonResponse({"error": "Invalid format. Use 'docx' or 'pdf'."}, status=400)

        try:
            invoice = Invoice.objects.select_related("customer").get(pk=pk)
        except Invoice.DoesNotExist:
            return JsonResponse({"error": f"Invoice with ID {pk} not found."}, status=404)

        job = InvoiceDownloadJob.objects.create(
            invoice=invoice,
            status=InvoiceDownloadJob.STATUS_QUEUED,
            progress=0,
            format_type=format_type,
            created_by=request.user,
            request_params={"format": format_type},
        )

        run_invoice_download_job(str(job.id))

        return JsonResponse(
            {
                "job_id": str(job.id),
                "status": job.status,
                "progress": job.progress,
                "status_url": reverse("invoice-download-async-status", kwargs={"job_id": str(job.id)}),
                "stream_url": reverse("invoice-download-async-stream", kwargs={"job_id": str(job.id)}),
                "download_url": reverse("invoice-download-async-file", kwargs={"job_id": str(job.id)}),
            },
            status=202,
        )


class InvoiceDownloadAsyncStatusView(PermissionRequiredMixin, View):
    permission_required = ("invoices.view_invoice",)

    def get(self, request, job_id, *args, **kwargs):
        try:
            job = InvoiceDownloadJob.objects.select_related("invoice", "invoice__customer").get(id=job_id)
        except InvoiceDownloadJob.DoesNotExist:
            return JsonResponse({"error": "Job not found."}, status=404)

        data = {
            "job_id": str(job.id),
            "status": job.status,
            "progress": job.progress,
            "download_url": reverse("invoice-download-async-file", kwargs={"job_id": str(job.id)}),
        }

        if job.status == InvoiceDownloadJob.STATUS_FAILED:
            data["error"] = job.error_message or "Job failed"

        return JsonResponse(data)


class InvoiceDownloadAsyncStreamView(PermissionRequiredMixin, View):
    permission_required = ("invoices.view_invoice",)

    def get(self, request, job_id, *args, **kwargs):
        response = StreamingHttpResponse(self._stream_job(job_id), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response

    def _stream_job(self, job_id):
        last_progress = None
        try:
            job = InvoiceDownloadJob.objects.select_related("invoice").get(id=job_id)
        except InvoiceDownloadJob.DoesNotExist:
            yield self._send_event("error", {"message": "Job not found"})
            return

        yield self._send_event("start", {"message": "Starting invoice generation...", "progress": job.progress})

        while True:
            job.refresh_from_db()

            if last_progress != job.progress:
                yield self._send_event(
                    "progress",
                    {"progress": job.progress, "status": job.status},
                )
                last_progress = job.progress

            if job.status == InvoiceDownloadJob.STATUS_COMPLETED:
                yield self._send_event(
                    "complete",
                    {
                        "message": "Invoice ready",
                        "download_url": reverse("invoice-download-async-file", kwargs={"job_id": str(job.id)}),
                        "status": job.status,
                    },
                )
                break

            if job.status == InvoiceDownloadJob.STATUS_FAILED:
                yield self._send_event(
                    "error",
                    {"message": job.error_message or "Invoice generation failed", "status": job.status},
                )
                break

            yield ": keep-alive\n\n"
            time.sleep(0.5)

    @staticmethod
    def _send_event(event_type, data):
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


class InvoiceDownloadAsyncFileView(PermissionRequiredMixin, View):
    permission_required = ("invoices.view_invoice",)

    def get(self, request, job_id, *args, **kwargs):
        try:
            job = InvoiceDownloadJob.objects.select_related("invoice", "invoice__customer").get(id=job_id)
        except InvoiceDownloadJob.DoesNotExist:
            return JsonResponse({"error": "Job not found."}, status=404)

        if job.status != InvoiceDownloadJob.STATUS_COMPLETED or not job.output_path:
            return JsonResponse({"error": "Job not completed yet."}, status=400)

        invoice = job.invoice
        raw_name = f"{invoice.invoice_no_display}_{invoice.customer.full_name}"
        safe_name = slugify(raw_name, allow_unicode=False).replace("-", "_") or f"Invoice_{invoice.pk}"
        safe_name = safe_name[:200]
        extension = "pdf" if job.format_type == InvoiceDownloadJob.FORMAT_PDF else "docx"

        file_handle = default_storage.open(job.output_path, "rb")
        content_type = (
            "application/pdf"
            if extension == "pdf"
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        response = FileResponse(file_handle, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{safe_name}.{extension}"'
        return response
