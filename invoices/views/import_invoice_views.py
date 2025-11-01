"""
Invoice Import Views
Handles single and batch invoice imports via file upload with SSE progress streaming.
"""

import json
import logging
import time

from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.http import JsonResponse, StreamingHttpResponse
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import TemplateView

from invoices.services.invoice_importer import InvoiceImporter

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

        # Validate file extension
        allowed_extensions = [".pdf", ".xlsx", ".xls", ".docx", ".doc"]
        file_ext = uploaded_file.name.lower().split(".")[-1]
        if f".{file_ext}" not in allowed_extensions:
            return JsonResponse(
                {"success": False, "error": f"Unsupported file format: .{file_ext}", "filename": uploaded_file.name},
                status=400,
            )

        try:
            # Import the invoice
            importer = InvoiceImporter(user=request.user)
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

        if not files:
            return JsonResponse({"success": False, "error": "No files uploaded"}, status=400)

        # Return SSE stream
        response = StreamingHttpResponse(
            self.process_files_stream(files, request.user), content_type="text/event-stream"
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response

    def process_files_stream(self, files, user):
        """
        Generator that yields SSE events for each step of the import process.
        """
        total_files = len(files)
        results = []
        importer = InvoiceImporter(user=user)

        # Send initial event
        yield self.send_event(
            "start", {"total": total_files, "message": f"Starting import of {total_files} file(s)..."}
        )

        for index, uploaded_file in enumerate(files, 1):
            filename = uploaded_file.name

            # Send file start event
            yield self.send_event(
                "file_start",
                {
                    "index": index,
                    "total": total_files,
                    "filename": filename,
                    "message": f"Processing {filename} ({index}/{total_files})...",
                },
            )

            # Validate file extension
            allowed_extensions = [".pdf", ".xlsx", ".xls", ".docx", ".doc"]
            file_ext = filename.lower().split(".")[-1]

            if f".{file_ext}" not in allowed_extensions:
                result_data = {
                    "success": False,
                    "status": "error",
                    "message": f"Unsupported file format: .{file_ext}",
                    "filename": filename,
                    "errors": [f"File type .{file_ext} not supported"],
                }
                results.append(result_data)

                yield self.send_event(
                    "file_error",
                    {
                        "index": index,
                        "filename": filename,
                        "message": f"Unsupported file format: .{file_ext}",
                        "result": result_data,
                    },
                )
                continue

            try:
                # Send parsing event
                yield self.send_event(
                    "parsing",
                    {"index": index, "filename": filename, "message": f"Parsing {filename} with AI vision..."},
                )

                # Import the invoice (this will take a few seconds)
                result = importer.import_from_file(uploaded_file, filename)

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

                results.append(result_data)

                # Send completion event based on status
                if result.status == "imported":
                    yield self.send_event(
                        "file_success",
                        {
                            "index": index,
                            "filename": filename,
                            "message": f"✓ Successfully imported {filename}",
                            "result": result_data,
                        },
                    )
                elif result.status == "duplicate":
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
                            "message": f"✗ Error processing {filename}: {result.message}",
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

    def send_event(self, event_type, data):
        """
        Format and send an SSE event.
        """
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
