"""
Invoice Import Views
Handles single and batch invoice imports via file upload with SSE progress streaming.
Supports parallel processing with configurable concurrency.
"""

import json
import logging
import os
import time

from django.conf import settings
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.files.storage import default_storage
from django.http import JsonResponse, StreamingHttpResponse
from django.urls import reverse_lazy
from django.utils.text import get_valid_filename
from django.views import View
from django.views.generic import TemplateView

from invoices.models import InvoiceImportItem, InvoiceImportJob
from invoices.services.invoice_importer import InvoiceImporter
from invoices.tasks.import_jobs import run_invoice_import_item

logger = logging.getLogger(__name__)


class InvoiceImportView(PermissionRequiredMixin, TemplateView):
    """
    Display the invoice import page with drag-and-drop interface.
    """

    permission_required = ("invoices.add_invoice",)
    template_name = "invoices/invoice_import.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Import Invoices"
        context["supported_formats"] = [".pdf", ".xlsx", ".xls", ".docx", ".doc"]
        context["max_workers"] = getattr(settings, "INVOICE_IMPORT_MAX_WORKERS", 3)

        # Add current LLM configuration
        context["current_provider"] = getattr(settings, "LLM_PROVIDER", "openrouter")
        context["current_model"] = getattr(settings, "LLM_DEFAULT_MODEL", "google/gemini-2.0-flash-001")

        return context


class InvoiceSingleImportView(PermissionRequiredMixin, View):
    """
    Handle single invoice file upload and import.
    Returns JSON response with import result.
    """

    permission_required = ("invoices.add_invoice",)

    def post(self, request, *args, **kwargs):
        """
        Process uploaded invoice file.
        """
        if "file" not in request.FILES:
            return JsonResponse({"success": False, "error": "No file uploaded"}, status=400)

        uploaded_file = request.FILES["file"]

        # Get optional LLM override parameters
        llm_provider = request.POST.get("llm_provider")
        llm_model = request.POST.get("llm_model")

        # Validate file extension
        allowed_extensions = [".pdf", ".xlsx", ".xls", ".docx", ".doc"]
        file_ext = uploaded_file.name.lower().split(".")[-1]
        if f".{file_ext}" not in allowed_extensions:
            return JsonResponse(
                {"success": False, "error": f"Unsupported file format: .{file_ext}", "filename": uploaded_file.name},
                status=400,
            )

        try:
            # Import the invoice with optional LLM overrides
            importer = InvoiceImporter(user=request.user, llm_provider=llm_provider, llm_model=llm_model)
            result = importer.import_from_file(uploaded_file, uploaded_file.name)

            response_data = {
                "success": result.success,
                "status": result.status,
                "message": result.message,
                "filename": uploaded_file.name,
            }

            if result.invoice:
                response_data["invoice"] = {
                    "id": result.invoice.pk,
                    "invoice_no": result.invoice.invoice_no_display,
                    "customer_name": result.invoice.customer.full_name,
                    "total_amount": str(result.invoice.total_amount),
                    "invoice_date": result.invoice.invoice_date.strftime("%Y-%m-%d"),
                    "status": result.invoice.get_status_display(),
                    "url": reverse_lazy("invoice-detail", kwargs={"pk": result.invoice.pk}),
                }

            if result.customer:
                response_data["customer"] = {
                    "id": result.customer.pk,
                    "title": result.customer.title or "N/A",
                    "name": result.customer.full_name,
                    "email": result.customer.email or "N/A",
                    "phone": result.customer.telephone or "N/A",
                    "address": result.customer.address_bali or "N/A",
                    "company": result.customer.company_name or "N/A",
                    "npwp": result.customer.npwp or "N/A",
                }

            if result.errors:
                response_data["errors"] = result.errors

            # Status code based on result
            status_code = 200 if result.success else (409 if result.status == "duplicate" else 400)

            return JsonResponse(response_data, status=status_code)

        except Exception as e:
            logger.error(f"Error processing upload: {str(e)}", exc_info=True)
            return JsonResponse(
                {"success": False, "error": f"Server error: {str(e)}", "filename": uploaded_file.name}, status=500
            )


class InvoiceBatchImportView(PermissionRequiredMixin, View):
    """
    Handle multiple invoice files upload and import with SSE progress streaming.
    Returns Server-Sent Events stream with real-time progress updates.
    """

    permission_required = ("invoices.add_invoice",)

    def post(self, request, *args, **kwargs):
        """
        Process multiple uploaded invoice files with real-time progress streaming.
        """
        files = request.FILES.getlist("files")
        paid_status_list = request.POST.getlist("paid_status")  # List of 'true'/'false' strings

        # Get optional LLM override parameters
        llm_provider = request.POST.get("llm_provider")
        llm_model = request.POST.get("llm_model")

        if not files:
            return JsonResponse({"success": False, "error": "No files uploaded"}, status=400)

        job = InvoiceImportJob.objects.create(
            status=InvoiceImportJob.STATUS_QUEUED,
            progress=0,
            total_files=len(files),
            created_by=request.user,
            request_params={"llm_provider": llm_provider, "llm_model": llm_model},
        )

        for index, uploaded_file in enumerate(files, 1):
            filename = uploaded_file.name
            is_paid = paid_status_list[index - 1].lower() == "true" if index - 1 < len(paid_status_list) else False
            safe_name = get_valid_filename(os.path.basename(filename))
            tmp_dir = os.path.join(settings.TMPFILES_FOLDER, "invoice_imports", str(job.id))
            tmp_path = os.path.join(tmp_dir, safe_name)
            file_path = default_storage.save(tmp_path, uploaded_file)

            item = InvoiceImportItem.objects.create(
                job=job,
                sort_index=index,
                filename=filename,
                file_path=file_path,
                is_paid=is_paid,
                status=InvoiceImportItem.STATUS_QUEUED,
            )
            run_invoice_import_item(str(item.id))

        # Return SSE stream
        response = StreamingHttpResponse(
            self.stream_job(job.id),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response

    def stream_job(self, job_id):
        """Stream SSE updates for a running Huey import job."""
        sent_states = {}
        job = InvoiceImportJob.objects.get(id=job_id)
        total_files = job.total_files

        yield self.send_event(
            "start",
            {
                "total": total_files,
                "message": f"Starting background import of {total_files} file(s)...",
            },
        )

        while True:
            job.refresh_from_db()
            items = list(job.items.all().order_by("sort_index"))

            for item in items:
                state = sent_states.get(item.id, {"file_start": False, "parsing": False, "done": False})

                if item.status == InvoiceImportItem.STATUS_PROCESSING and not state["file_start"]:
                    yield self.send_event(
                        "file_start",
                        {
                            "index": item.sort_index,
                            "filename": item.filename,
                            "message": f"Processing {item.filename}...",
                        },
                    )
                    state["file_start"] = True

                if (
                    item.status == InvoiceImportItem.STATUS_PROCESSING
                    and item.result
                    and item.result.get("stage") == "parsing"
                    and not state["parsing"]
                ):
                    yield self.send_event(
                        "parsing",
                        {
                            "index": item.sort_index,
                            "filename": item.filename,
                            "message": f"Parsing {item.filename} with AI...",
                        },
                    )
                    state["parsing"] = True

                if (
                    item.status
                    in [
                        InvoiceImportItem.STATUS_IMPORTED,
                        InvoiceImportItem.STATUS_DUPLICATE,
                        InvoiceImportItem.STATUS_ERROR,
                    ]
                    and not state["done"]
                ):
                    result_data = self._build_result(item)
                    if item.status == InvoiceImportItem.STATUS_IMPORTED:
                        event_type = "file_success"
                        message = f"✓ Successfully imported {item.filename}"
                    elif item.status == InvoiceImportItem.STATUS_DUPLICATE:
                        event_type = "file_duplicate"
                        message = f"⚠ Duplicate invoice detected: {item.filename}"
                    else:
                        event_type = "file_error"
                        message = f"✗ Error processing {item.filename}: {result_data.get('message', 'Unknown error')}"

                    yield self.send_event(
                        event_type,
                        {
                            "index": item.sort_index,
                            "filename": item.filename,
                            "message": message,
                            "result": result_data,
                        },
                    )
                    state["done"] = True

                sent_states[item.id] = state

            if job.processed_files >= job.total_files and all(state["done"] for state in sent_states.values()):
                summary = self._build_summary(job, items)
                yield self.send_event(
                    "complete",
                    {
                        "message": f"Import complete: {summary['summary']['imported']} imported, "
                        f"{summary['summary']['duplicates']} duplicates, {summary['summary']['errors']} errors",
                        **summary,
                    },
                )
                break

            yield ": keep-alive\n\n"
            time.sleep(0.5)

    def _build_result(self, item):
        if item.result and isinstance(item.result, dict) and item.result.get("status"):
            return item.result
        return {
            "success": item.status == InvoiceImportItem.STATUS_IMPORTED,
            "status": item.status,
            "message": item.error_message or "Processing",
            "filename": item.filename,
        }

    def _build_summary(self, job, items):
        results = [self._build_result(item) for item in items]
        summary = {
            "total": job.total_files,
            "imported": job.imported_count,
            "duplicates": job.duplicate_count,
            "errors": job.error_count,
        }
        return {"summary": summary, "results": results}

    def send_event(self, event_type, data):
        """
        Format and send an SSE event.
        """
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
