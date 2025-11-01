"""
Invoice Import Views
Handles single and batch invoice imports via file upload.
"""

import json
import logging

from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.http import JsonResponse
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
    Handle multiple invoice files upload and import.
    Returns JSON response with results for all files.
    """

    permission_required = ("invoices.add_invoice",)

    def post(self, request, *args, **kwargs):
        """
        Process multiple uploaded invoice files.
        """
        files = request.FILES.getlist("files")

        if not files:
            return JsonResponse({"success": False, "error": "No files uploaded"}, status=400)

        results = []
        importer = InvoiceImporter(user=request.user)

        for uploaded_file in files:
            # Validate file extension
            allowed_extensions = [".pdf", ".xlsx", ".xls", ".docx", ".doc"]
            file_ext = uploaded_file.name.lower().split(".")[-1]

            if f".{file_ext}" not in allowed_extensions:
                results.append(
                    {
                        "success": False,
                        "status": "error",
                        "message": f"Unsupported file format: .{file_ext}",
                        "filename": uploaded_file.name,
                        "errors": [f"File type .{file_ext} not supported"],
                    }
                )
                continue

            try:
                # Import the invoice
                result = importer.import_from_file(uploaded_file, uploaded_file.name)

                result_data = {
                    "success": result.success,
                    "status": result.status,
                    "message": result.message,
                    "filename": uploaded_file.name,
                }

                if result.invoice:
                    result_data["invoice"] = {
                        "id": result.invoice.pk,
                        "invoice_no": result.invoice.invoice_no_display,
                        "customer_name": result.invoice.customer.full_name,
                        "total_amount": str(result.invoice.total_amount),
                        "invoice_date": result.invoice.invoice_date.strftime("%Y-%m-%d"),
                        "status": result.invoice.get_status_display(),
                        "url": reverse_lazy("invoice-detail", kwargs={"pk": result.invoice.pk}),
                    }

                if result.customer:
                    result_data["customer"] = {
                        "id": result.customer.pk,
                        "name": result.customer.full_name,
                    }

                if result.errors:
                    result_data["errors"] = result.errors

                results.append(result_data)

            except Exception as e:
                logger.error(f"Error processing {uploaded_file.name}: {str(e)}", exc_info=True)
                results.append(
                    {
                        "success": False,
                        "status": "error",
                        "message": f"Server error: {str(e)}",
                        "filename": uploaded_file.name,
                        "errors": [str(e)],
                    }
                )

        # Calculate summary
        total = len(results)
        imported = sum(1 for r in results if r["status"] == "imported")
        duplicates = sum(1 for r in results if r["status"] == "duplicate")
        errors = sum(1 for r in results if r["status"] == "error")

        return JsonResponse(
            {
                "success": True,
                "summary": {"total": total, "imported": imported, "duplicates": duplicates, "errors": errors},
                "results": results,
            },
            status=200,
        )
