"""
Invoice Import Views
Handles single and batch invoice imports via file upload with SSE progress streaming.
Supports parallel processing with configurable concurrency.
"""

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.http import JsonResponse, StreamingHttpResponse
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from invoices.services.invoice_importer import InvoiceImporter
from payments.models import Payment

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
                    "name": result.customer.full_name,
                    "email": result.customer.email or "N/A",
                    "phone": result.customer.telephone or "N/A",
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

        # Return SSE stream
        response = StreamingHttpResponse(
            self.process_files_stream(files, paid_status_list, request.user, llm_provider, llm_model),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response

    def process_files_stream(self, files, paid_status_list, user, llm_provider=None, llm_model=None):
        """
        Generator that yields SSE events for each step of the import process.
        Uses parallel processing with ThreadPoolExecutor for faster imports.

        Args:
            llm_provider: Optional LLM provider override ("openrouter" or "openai")
            llm_model: Optional LLM model override
        """
        total_files = len(files)
        results = []
        max_workers = getattr(settings, "INVOICE_IMPORT_MAX_WORKERS", 3)

        # Send initial event
        yield self.send_event(
            "start",
            {
                "total": total_files,
                "message": f"Starting parallel import of {total_files} file(s) (max {max_workers} concurrent)...",
            },
        )

        # Prepare file data for parallel processing
        file_tasks = []
        for index, uploaded_file in enumerate(files, 1):
            filename = uploaded_file.name
            is_paid = paid_status_list[index - 1].lower() == "true" if index - 1 < len(paid_status_list) else False

            # Read file content to bytes (so it's safe to pass to threads)
            file_content = uploaded_file.read()
            uploaded_file.seek(0)  # Reset file pointer

            file_tasks.append(
                {
                    "index": index,
                    "filename": filename,
                    "file_content": file_content,
                    "is_paid": is_paid,
                }
            )

        # Process files in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_file = {
                executor.submit(self._process_single_file, task, user, llm_provider, llm_model): task
                for task in file_tasks
            }

            # Process results as they complete (not necessarily in order)
            for future in as_completed(future_to_file):
                task = future_to_file[future]
                index = task["index"]
                filename = task["filename"]

                try:
                    result_data = future.result()
                    results.append(result_data)

                    # Send appropriate event based on status
                    if result_data["status"] == "imported":
                        yield self.send_event(
                            "file_success",
                            {
                                "index": index,
                                "filename": filename,
                                "message": f"✓ Successfully imported {filename}",
                                "result": result_data,
                            },
                        )
                    elif result_data["status"] == "duplicate":
                        yield self.send_event(
                            "file_duplicate",
                            {
                                "index": index,
                                "filename": filename,
                                "message": f"⚠ Duplicate invoice detected: {filename}",
                                "result": result_data,
                            },
                        )
                    else:
                        yield self.send_event(
                            "file_error",
                            {
                                "index": index,
                                "filename": filename,
                                "message": f"✗ Error processing {filename}: {result_data.get('message', 'Unknown error')}",
                                "result": result_data,
                            },
                        )

                except Exception as e:
                    logger.error(f"Error processing {filename}: {str(e)}", exc_info=True)
                    result_data = {
                        "success": False,
                        "status": "error",
                        "message": f"Server error: {str(e)}",
                        "filename": filename,
                        "errors": [str(e)],
                    }
                    results.append(result_data)

                    yield self.send_event(
                        "file_error",
                        {
                            "index": index,
                            "filename": filename,
                            "message": f"✗ Server error processing {filename}",
                            "result": result_data,
                        },
                    )

        # Calculate summary
        total = len(results)
        imported = sum(1 for r in results if r["status"] == "imported")
        duplicates = sum(1 for r in results if r["status"] == "duplicate")
        errors = sum(1 for r in results if r["status"] == "error")

        summary = {"total": total, "imported": imported, "duplicates": duplicates, "errors": errors}

        # Send final completion event
        yield self.send_event(
            "complete",
            {
                "message": f"Import complete: {imported} imported, {duplicates} duplicates, {errors} errors",
                "summary": summary,
                "results": results,
            },
        )

    def _process_single_file(self, task, user, llm_provider=None, llm_model=None):
        """
        Process a single file import. This method runs in a separate thread.

        Args:
            task: Dict with index, filename, file_content, is_paid
            user: Django user for import
            llm_provider: Optional LLM provider override
            llm_model: Optional LLM model override

        Returns:
            Dict with result data
        """
        from io import BytesIO

        from django.core.files.uploadedfile import InMemoryUploadedFile
        from django.db import close_old_connections

        # CRITICAL: Each thread needs its own database connection
        # Close any stale connections inherited from parent thread
        close_old_connections()

        filename = task["filename"]
        file_content = task["file_content"]
        is_paid = task["is_paid"]

        # Validate file extension
        allowed_extensions = [".pdf", ".xlsx", ".xls", ".docx", ".doc"]
        file_ext = filename.lower().split(".")[-1]

        if f".{file_ext}" not in allowed_extensions:
            return {
                "success": False,
                "status": "error",
                "message": f"Unsupported file format: .{file_ext}",
                "filename": filename,
                "errors": [f"File type .{file_ext} not supported"],
            }

        try:
            # Import the invoice (with database locking to prevent race conditions)
            # Pass the bytes content directly, not a BytesIO object
            importer = InvoiceImporter(user=user, llm_provider=llm_provider, llm_model=llm_model)
            result = importer.import_from_file(file_content, filename)

            # If invoice was successfully imported and marked as paid, create payments
            if result.success and result.status == "imported" and is_paid and result.invoice:
                try:
                    # Create full payment for each invoice application
                    payment_count = 0
                    for invoice_app in result.invoice.invoice_applications.all():
                        Payment.objects.create(
                            invoice_application=invoice_app,
                            from_customer=result.invoice.customer,
                            payment_date=result.invoice.due_date,
                            amount=invoice_app.amount,
                            payment_type=Payment.CASH,
                            notes=f"Auto-created payment for imported invoice {result.invoice.invoice_no_display}",
                            created_by=user,
                            updated_by=user,
                        )
                        payment_count += 1

                    logger.info(f"Created {payment_count} payment(s) for invoice {result.invoice.invoice_no_display}")
                    result.message += f" (Marked as paid with {payment_count} payment(s))"
                except Exception as e:
                    logger.error(f"Error creating payments for {filename}: {str(e)}", exc_info=True)
                    result.message += " (Warning: Failed to create payments)"

            result_data = {
                "success": result.success,
                "status": result.status,
                "message": result.message,
                "filename": filename,
            }

            if result.invoice:
                result_data["invoice"] = {
                    "id": result.invoice.pk,
                    "invoice_no": result.invoice.invoice_no_display,
                    "customer_name": result.invoice.customer.full_name,
                    "total_amount": str(result.invoice.total_amount),
                    "invoice_date": result.invoice.invoice_date.strftime("%Y-%m-%d"),
                    "status": result.invoice.get_status_display(),
                    "url": str(reverse_lazy("invoice-detail", kwargs={"pk": result.invoice.pk})),
                }

            if result.customer:
                result_data["customer"] = {
                    "id": result.customer.pk,
                    "name": result.customer.full_name,
                }

            if result.errors:
                result_data["errors"] = result.errors

            return result_data

        except Exception as e:
            logger.error(f"Error processing {filename}: {str(e)}", exc_info=True)
            return {
                "success": False,
                "status": "error",
                "message": f"Server error: {str(e)}",
                "filename": filename,
                "errors": [str(e)],
            }

    def send_event(self, event_type, data):
        """
        Format and send an SSE event.
        """
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
