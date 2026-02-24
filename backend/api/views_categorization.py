"""
Document Categorization API Views

Endpoints for AI-powered document classification:
- POST /api/customer-applications/{id}/categorize-documents/ — upload & categorize multiple files
- GET /api/document-categorization/stream/{job_id}/ — SSE progress streaming
- POST /api/document-categorization/{job_id}/apply/ — apply confirmed mappings
- POST /api/documents/{id}/validate-category/ — single-file type validation
"""

import json
import os
import time
import traceback as tb_module
from typing import Any, cast

from api.serializers.categorization_serializer import CategorizationApplySerializer, DocumentCategorizationJobSerializer
from api.utils.sse_auth import sse_token_auth_required
from core.services.ai_document_categorizer import AIDocumentCategorizer
from core.services.logger_service import Logger
from core.tasks.document_categorization import run_document_categorization_item
from customer_applications.models import DocApplication, Document, DocumentCategorizationItem, DocumentCategorizationJob
from django.core.files.storage import default_storage
from django.http import JsonResponse, StreamingHttpResponse
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

logger = Logger.get_logger(__name__)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def categorize_documents(request, application_id):
    """
    Upload multiple files and start AI categorization.
    Files are saved to temp storage and Huey tasks are dispatched in parallel.
    """
    try:
        doc_application = DocApplication.objects.get(id=application_id)
    except DocApplication.DoesNotExist:
        return Response(
            {"code": "not_found", "errors": {"detail": ["Application not found."]}},
            status=status.HTTP_404_NOT_FOUND,
        )

    files = request.FILES.getlist("files")
    if not files:
        return Response(
            {"code": "validation_error", "errors": {"files": ["No files provided."]}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    model = request.data.get("model")
    provider_order_raw = request.data.get("providerOrder")
    provider_order = None
    if provider_order_raw:
        if isinstance(provider_order_raw, str):
            provider_order = [p.strip() for p in provider_order_raw.split(",") if p.strip()]
        elif isinstance(provider_order_raw, list):
            provider_order = provider_order_raw

    # Create the job
    job = DocumentCategorizationJob.objects.create(
        doc_application=doc_application,
        total_files=len(files),
        request_params={
            "model": model,
            "provider_order": provider_order,
        },
        created_by=request.user,
    )

    # Save files and create items
    temp_dir = f"tmp/categorization/{job.id}"
    items = []

    for idx, uploaded_file in enumerate(files):
        # Sanitize filename
        safe_filename = os.path.basename(uploaded_file.name)
        file_path = f"{temp_dir}/{safe_filename}"

        # Save to storage
        saved_path = default_storage.save(file_path, uploaded_file)

        item = DocumentCategorizationItem.objects.create(
            job=job,
            sort_index=idx,
            filename=safe_filename,
            file_path=saved_path,
        )
        items.append(item)

    # Dispatch Huey tasks (one per file for parallel processing)
    for item in items:
        run_document_categorization_item(str(item.id))

    return Response(
        {
            "jobId": str(job.id),
            "totalFiles": len(files),
            "status": "queued",
        },
        status=status.HTTP_201_CREATED,
    )


@sse_token_auth_required
def categorization_stream_sse(request, job_id):
    """SSE endpoint for real-time categorization progress."""

    try:
        job = DocumentCategorizationJob.objects.get(id=job_id)
    except DocumentCategorizationJob.DoesNotExist:
        return JsonResponse({"error": "Job not found"}, status=404)

    # Only owner or staff can stream
    if not request.user.is_staff and job.created_by_id != request.user.id:
        return JsonResponse({"error": "Forbidden"}, status=403)

    def event_stream():
        sent_states = {}
        total_files = job.total_files

        yield _send_event(
            "start",
            {
                "jobId": str(job.id),
                "total": total_files,
                "message": f"Starting categorization of {total_files} file(s)...",
            },
        )

        while True:
            job.refresh_from_db()
            items = list(job.items.all().order_by("sort_index"))

            for item in items:
                state = sent_states.get(item.id, {"processing": False, "done": False})

                if item.status == DocumentCategorizationItem.STATUS_PROCESSING and not state["processing"]:
                    yield _send_event(
                        "file_start",
                        {
                            "index": item.sort_index,
                            "filename": item.filename,
                            "message": f"Categorizing {item.filename}...",
                        },
                    )
                    state["processing"] = True

                if item.status == DocumentCategorizationItem.STATUS_CATEGORIZED and not state["done"]:
                    yield _send_event(
                        "file_categorized",
                        {
                            "index": item.sort_index,
                            "filename": item.filename,
                            "documentType": item.result.get("document_type") if item.result else None,
                            "documentTypeId": item.result.get("document_type_id") if item.result else None,
                            "documentId": item.document_id,
                            "confidence": item.confidence,
                            "reasoning": item.result.get("reasoning", "") if item.result else "",
                            "message": f"✓ {item.filename} → {item.result.get('document_type', 'Unknown') if item.result else 'Unknown'}",
                        },
                    )
                    state["done"] = True

                if item.status == DocumentCategorizationItem.STATUS_ERROR and not state["done"]:
                    yield _send_event(
                        "file_error",
                        {
                            "index": item.sort_index,
                            "filename": item.filename,
                            "message": f"✗ {item.filename}: {item.error_message or 'Unknown error'}",
                            "error": item.error_message or "Unknown error",
                        },
                    )
                    state["done"] = True

                sent_states[item.id] = state

            if job.processed_files >= job.total_files and all(s.get("done", False) for s in sent_states.values()):
                # Build final results
                results = []
                for item in items:
                    results.append(
                        {
                            "itemId": str(item.id),
                            "filename": item.filename,
                            "status": item.status,
                            "documentType": item.result.get("document_type") if item.result else None,
                            "documentTypeId": item.result.get("document_type_id") if item.result else None,
                            "documentId": item.document_id,
                            "confidence": item.confidence,
                            "reasoning": item.result.get("reasoning", "") if item.result else "",
                            "error": item.error_message or None,
                        }
                    )

                yield _send_event(
                    "complete",
                    {
                        "message": f"Categorization complete: {job.success_count} categorized, "
                        f"{job.error_count} errors",
                        "summary": {
                            "total": job.total_files,
                            "success": job.success_count,
                            "errors": job.error_count,
                        },
                        "results": results,
                    },
                )
                break

            yield ": keep-alive\n\n"
            time.sleep(0.5)

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def categorization_apply(request, job_id):
    """Apply confirmed categorization results: attach files to Document rows."""
    try:
        job = DocumentCategorizationJob.objects.get(id=job_id)
    except DocumentCategorizationJob.DoesNotExist:
        return Response(
            {"code": "not_found", "errors": {"detail": ["Job not found."]}},
            status=status.HTTP_404_NOT_FOUND,
        )

    if not request.user.is_staff and job.created_by_id != request.user.id:
        return Response(
            {"code": "forbidden", "errors": {"detail": ["Permission denied."]}},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = CategorizationApplySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    # validated_data is guaranteed to be populated after is_valid().
    # Cast for static type-checkers that otherwise infer "empty | None".
    validated_data = cast(dict[str, list[dict[str, Any]]], serializer.validated_data)
    mappings = validated_data.get("mappings", [])
    applied = []
    errors = []

    for mapping in mappings:
        item_id = mapping["itemId"]
        document_id = mapping["documentId"]

        try:
            item = DocumentCategorizationItem.objects.get(id=item_id, job=job)
        except DocumentCategorizationItem.DoesNotExist:
            errors.append({"itemId": str(item_id), "error": "Item not found"})
            continue

        try:
            document = Document.objects.get(
                id=document_id,
                doc_application=job.doc_application,
            )
        except Document.DoesNotExist:
            errors.append({"itemId": str(item_id), "error": "Document not found in this application"})
            continue

        try:
            # Read the temp file
            with default_storage.open(item.file_path, "rb") as f:
                file_content = f.read()

            # Determine the final path
            _, extension = os.path.splitext(item.filename)
            from core.utils.helpers import whitespaces_to_underscores

            final_filename = f"{whitespaces_to_underscores(document.doc_type.name)}{extension}"
            doc_application_folder = document.doc_application.upload_folder
            final_path = f"{doc_application_folder}/{final_filename}"

            # Save to final location
            from django.core.files.base import ContentFile

            saved_path = default_storage.save(final_path, ContentFile(file_content))

            # Update the Document
            document.file.name = saved_path
            document.updated_by = request.user
            document.save()  # This triggers auto-complete calculation

            # Update the item
            item.document = document
            item.save(update_fields=["document", "updated_at"])

            applied.append(
                {
                    "itemId": str(item_id),
                    "documentId": document_id,
                    "documentType": document.doc_type.name,
                    "filename": item.filename,
                }
            )

        except Exception as exc:
            logger.error("Error applying categorization item %s: %s", item_id, exc, exc_info=True)
            errors.append({"itemId": str(item_id), "error": str(exc)})

    # Clean up temp files for applied items
    for item_data in applied:
        try:
            item = DocumentCategorizationItem.objects.get(id=item_data["itemId"])
            if default_storage.exists(item.file_path):
                default_storage.delete(item.file_path)
        except Exception:
            pass

    return Response(
        {
            "applied": applied,
            "errors": errors,
            "totalApplied": len(applied),
            "totalErrors": len(errors),
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def validate_document_category(request, document_id):
    """Validate that a single uploaded file matches its expected DocumentType."""
    try:
        document = Document.objects.select_related("doc_type").get(id=document_id)
    except Document.DoesNotExist:
        return Response(
            {"code": "not_found", "errors": {"detail": ["Document not found."]}},
            status=status.HTTP_404_NOT_FOUND,
        )

    file = request.FILES.get("file")
    if not file:
        return Response(
            {"code": "validation_error", "errors": {"file": ["No file provided."]}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        file_bytes = file.read()
        categorizer = AIDocumentCategorizer()
        result = categorizer.validate_file_matches_type(
            file_bytes=file_bytes,
            filename=file.name,
            expected_type_name=document.doc_type.name,
        )
        return Response(result)
    except Exception as exc:
        logger.error("Document validation error: %s", exc, exc_info=True)
        return Response(
            {"code": "server_error", "errors": {"detail": [str(exc)]}},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def categorization_job_status(request, job_id):
    """Polling fallback for categorization job status."""
    try:
        job = DocumentCategorizationJob.objects.prefetch_related("items").get(id=job_id)
    except DocumentCategorizationJob.DoesNotExist:
        return Response(
            {"code": "not_found", "errors": {"detail": ["Job not found."]}},
            status=status.HTTP_404_NOT_FOUND,
        )

    if not request.user.is_staff and job.created_by_id != request.user.id:
        return Response(
            {"code": "forbidden", "errors": {"detail": ["Permission denied."]}},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = DocumentCategorizationJobSerializer(job)
    return Response(serializer.data)


def _send_event(event_type: str, data: dict) -> str:
    """Format an SSE event."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
