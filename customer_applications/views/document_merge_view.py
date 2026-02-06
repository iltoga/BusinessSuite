"""
View for merging multiple documents into a single PDF and downloading.
"""

import logging

from django.contrib.auth.mixins import PermissionRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.utils.text import slugify
from django.views import View

from core.services.document_merger import DocumentMerger, DocumentMergerError
from core.services.logger_service import Logger
from customer_applications.models import DocApplication, Document

logger = Logger.get_logger(__name__)


class DocumentMergeDownloadView(PermissionRequiredMixin, View):
    """
    View to merge selected documents into a single PDF and download.

    Accepts POST request with document IDs to merge.
    """

    permission_required = ("customer_applications.view_document",)

    def post(self, request, *args, **kwargs):
        """
        Handle POST request to merge documents.

        Expected POST data:
        - document_ids: comma-separated list of document IDs, or
        - document_ids[]: array of document IDs (for form submission)
        """
        # Get document IDs from request
        document_ids = request.POST.getlist("document_ids[]")

        if not document_ids:
            # Try comma-separated format
            ids_string = request.POST.get("document_ids", "")
            if ids_string:
                document_ids = [id.strip() for id in ids_string.split(",") if id.strip()]

        if not document_ids:
            return JsonResponse(
                {"error": "No documents selected for merging."},
                status=400,
            )

        try:
            # Convert to integers
            document_ids = [int(id) for id in document_ids]
        except ValueError:
            return JsonResponse(
                {"error": "Invalid document IDs provided."},
                status=400,
            )

        # Get the documents - we'll preserve the order from the request
        documents_dict = {
            doc.pk: doc
            for doc in Document.objects.filter(
                pk__in=document_ids,
                completed=True,  # Only merge completed documents
            ).select_related("doc_type", "doc_application__customer")
        }

        if not documents_dict:
            return JsonResponse(
                {"error": "No valid documents found with the provided IDs."},
                status=404,
            )

        # Preserve the order from the request (user-defined order via drag-and-drop)
        ordered_documents = [documents_dict[doc_id] for doc_id in document_ids if doc_id in documents_dict]

        # Check that all documents have files
        documents_with_files = [doc for doc in ordered_documents if doc.file and doc.file.name]
        if not documents_with_files:
            return JsonResponse(
                {"error": "Selected documents have no uploaded files."},
                status=400,
            )

        # Get application info for filename
        first_doc = documents_with_files[0]
        application = first_doc.doc_application
        customer_name = application.customer.full_name

        try:
            # Merge documents
            merged_pdf = DocumentMerger.merge_document_models(documents_with_files)

            # Generate filename
            safe_customer_name = slugify(customer_name, allow_unicode=False).replace("-", "_")
            filename = f"documents_{safe_customer_name}_{application.pk}.pdf"
            filename = filename[:200]  # Limit filename length

            # Return the merged PDF
            response = HttpResponse(merged_pdf, content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            response["Content-Length"] = len(merged_pdf)

            logger.info(
                f"Successfully merged {len(documents_with_files)} documents " f"for application {application.pk}"
            )

            return response

        except DocumentMergerError as e:
            logger.error(f"Document merge failed: {e}")
            return JsonResponse(
                {"error": f"Failed to merge documents: {str(e)}"},
                status=500,
            )
        except Exception as e:
            logger.exception(f"Unexpected error during document merge: {e}")
            return JsonResponse(
                {"error": "An unexpected error occurred while merging documents."},
                status=500,
            )


class ApplicationDocumentMergeView(PermissionRequiredMixin, View):
    """
    View to merge all completed documents for a specific application.
    """

    permission_required = ("customer_applications.view_document",)

    def get(self, request, pk, *args, **kwargs):
        """
        Merge all completed documents for the given application.
        """
        try:
            application = DocApplication.objects.select_related("customer").get(pk=pk)
        except DocApplication.DoesNotExist:
            return JsonResponse(
                {"error": f"Application with ID {pk} not found."},
                status=404,
            )

        # Get all completed documents with files
        documents = (
            application.documents.filter(
                completed=True,
            )
            .select_related("doc_type")
            .order_by("doc_type__name")
        )

        documents_with_files = [doc for doc in documents if doc.file and doc.file.name]

        if not documents_with_files:
            return JsonResponse(
                {"error": "No documents with files found for this application."},
                status=400,
            )

        try:
            # Merge documents
            merged_pdf = DocumentMerger.merge_document_models(documents_with_files)

            # Generate filename
            customer_name = application.customer.full_name
            safe_customer_name = slugify(customer_name, allow_unicode=False).replace("-", "_")
            filename = f"all_documents_{safe_customer_name}_{pk}.pdf"
            filename = filename[:200]

            # Return the merged PDF
            response = HttpResponse(merged_pdf, content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            response["Content-Length"] = len(merged_pdf)

            logger.info(f"Successfully merged all {len(documents_with_files)} documents " f"for application {pk}")

            return response

        except DocumentMergerError as e:
            logger.error(f"Document merge failed for application {pk}: {e}")
            return JsonResponse(
                {"error": f"Failed to merge documents: {str(e)}"},
                status=500,
            )
        except Exception as e:
            logger.exception(f"Unexpected error during document merge: {e}")
            return JsonResponse(
                {"error": "An unexpected error occurred while merging documents."},
                status=500,
            )
