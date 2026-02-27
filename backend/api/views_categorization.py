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
from core.services.ai_document_categorizer import (
    AIDocumentCategorizer,
    extract_validation_details_markdown,
    extract_validation_doc_number,
    extract_validation_expiration_date,
)
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


class _ProgressTrackedUploadedFile:
    """File wrapper that reports bytes read while delegating to Django UploadedFile."""

    def __init__(self, wrapped_file, on_bytes_read):
        self._wrapped_file = wrapped_file
        self._on_bytes_read = on_bytes_read

    def read(self, *args, **kwargs):
        data = self._wrapped_file.read(*args, **kwargs)
        if data:
            self._on_bytes_read(len(data))
        return data

    def chunks(self, chunk_size=None):
        for chunk in self._wrapped_file.chunks(chunk_size=chunk_size):
            if chunk:
                self._on_bytes_read(len(chunk))
            yield chunk

    def __getattr__(self, name):
        return getattr(self._wrapped_file, name)


def _parse_provider_order(raw_value: Any) -> list[str] | None:
    if not raw_value:
        return None
    if isinstance(raw_value, str):
        parsed = [p.strip() for p in raw_value.split(",") if p.strip()]
        return parsed or None
    if isinstance(raw_value, list):
        parsed = [str(p).strip() for p in raw_value if str(p).strip()]
        return parsed or None
    return None


def _normalize_total_files(raw_total_files: Any) -> int:
    try:
        total = int(raw_total_files)
    except (TypeError, ValueError):
        return 0
    return max(0, total)


def _clamp_ratio(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _compute_overall_progress_percent(
    *,
    total_files: int,
    uploaded_files: int,
    uploaded_bytes: int,
    total_bytes: int,
    processed_files: int,
) -> int:
    total = max(0, int(total_files))
    if total <= 0:
        return 0

    if total_bytes > 0:
        upload_ratio = _clamp_ratio(uploaded_bytes / total_bytes)
    else:
        upload_ratio = _clamp_ratio(uploaded_files / total)

    processing_ratio = _clamp_ratio(processed_files / total)
    weighted = (0.4 * upload_ratio) + (0.6 * processing_ratio)
    return int(round(_clamp_ratio(weighted) * 100))


def _create_categorization_job(
    *, doc_application: DocApplication, created_by, model: Any, provider_order: list[str] | None, total_files: int
) -> DocumentCategorizationJob:
    return DocumentCategorizationJob.objects.create(
        doc_application=doc_application,
        total_files=total_files,
        request_params={
            "model": model,
            "provider_order": provider_order,
        },
        result={
            "stage": "uploading",
            "overall_progress_percent": 0,
            "upload": {
                "uploaded_files": 0,
                "total_files": total_files,
                "uploaded_bytes": 0,
                "total_bytes": 0,
                "current_file": None,
                "complete": False,
            },
        },
        created_by=created_by,
    )


def _update_upload_progress(
    job: DocumentCategorizationJob,
    *,
    uploaded_files: int,
    total_files: int,
    uploaded_bytes: int,
    total_bytes: int,
    current_file: str | None,
    complete: bool,
) -> None:
    overall_percent = _compute_overall_progress_percent(
        total_files=total_files,
        uploaded_files=uploaded_files,
        uploaded_bytes=uploaded_bytes,
        total_bytes=total_bytes,
        processed_files=int(getattr(job, "processed_files", 0) or 0),
    )

    current_result = job.result if isinstance(job.result, dict) else {}
    current_result["stage"] = "uploaded" if complete else "uploading"
    current_result["upload"] = {
        "uploaded_files": max(0, uploaded_files),
        "total_files": max(0, total_files),
        "uploaded_bytes": max(0, uploaded_bytes),
        "total_bytes": max(0, total_bytes),
        "current_file": current_file,
        "complete": bool(complete),
    }
    current_result["overall_progress_percent"] = overall_percent
    job.result = current_result
    job.total_files = max(0, total_files)
    job.save(update_fields=["result", "total_files", "updated_at"])


def _upload_files_to_job(*, job: DocumentCategorizationJob, files: list) -> tuple[int, int]:
    temp_dir = f"tmp/categorization/{job.id}"
    dispatched_tasks = 0

    total_files = max(job.total_files, len(files))
    total_bytes = sum(int(getattr(uploaded_file, "size", 0) or 0) for uploaded_file in files)

    uploaded_files = 0
    uploaded_bytes = 0

    _update_upload_progress(
        job,
        uploaded_files=uploaded_files,
        total_files=total_files,
        uploaded_bytes=uploaded_bytes,
        total_bytes=total_bytes,
        current_file=None,
        complete=False,
    )

    last_saved_bytes = 0
    last_saved_at = 0.0

    def persist_progress(*, current_file: str | None, force: bool = False) -> None:
        nonlocal last_saved_bytes, last_saved_at
        now = time.monotonic()
        bytes_delta = uploaded_bytes - last_saved_bytes
        time_delta = now - last_saved_at
        should_save = force or bytes_delta >= 256 * 1024 or time_delta >= 0.35
        if not should_save:
            return

        _update_upload_progress(
            job,
            uploaded_files=uploaded_files,
            total_files=total_files,
            uploaded_bytes=uploaded_bytes,
            total_bytes=total_bytes,
            current_file=current_file,
            complete=False,
        )
        last_saved_bytes = uploaded_bytes
        last_saved_at = now

    for idx, uploaded_file in enumerate(files):
        safe_filename = os.path.basename(uploaded_file.name)
        file_path = f"{temp_dir}/{safe_filename}"
        before_file_bytes = uploaded_bytes

        item = DocumentCategorizationItem.objects.create(
            job=job,
            sort_index=idx,
            filename=safe_filename,
            file_path="",
            result={"stage": "uploading", "ai_validation_enabled": None},
        )

        def on_bytes_read(byte_count: int) -> None:
            nonlocal uploaded_bytes
            uploaded_bytes += int(byte_count or 0)
            persist_progress(current_file=safe_filename)

        tracked_file = _ProgressTrackedUploadedFile(uploaded_file, on_bytes_read)
        saved_path = default_storage.save(file_path, tracked_file)

        # Ensure each file contributes at least its declared size even if backend read pattern did not trigger callbacks.
        declared_size = int(getattr(uploaded_file, "size", 0) or 0)
        read_for_current_file = uploaded_bytes - before_file_bytes
        if declared_size > 0 and read_for_current_file < declared_size:
            uploaded_bytes += declared_size - read_for_current_file
            uploaded_bytes = min(uploaded_bytes, total_bytes)

        item.file_path = saved_path
        item.result = {"stage": "uploaded", "ai_validation_enabled": None}
        item.save(update_fields=["file_path", "result", "updated_at"])

        run_document_categorization_item(str(item.id))
        dispatched_tasks += 1

        uploaded_files += 1
        persist_progress(current_file=safe_filename, force=True)

    _update_upload_progress(
        job,
        uploaded_files=uploaded_files,
        total_files=total_files,
        uploaded_bytes=total_bytes if total_bytes > 0 else uploaded_bytes,
        total_bytes=total_bytes,
        current_file=None,
        complete=True,
    )

    return uploaded_files, dispatched_tasks


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def categorize_documents_init(request, application_id):
    """Create a categorization job first so frontend can subscribe to SSE before file upload starts."""
    try:
        doc_application = DocApplication.objects.get(id=application_id)
    except DocApplication.DoesNotExist:
        return Response(
            {"code": "not_found", "errors": {"detail": ["Application not found."]}},
            status=status.HTTP_404_NOT_FOUND,
        )

    model = request.data.get("model")
    provider_order_raw = request.data.get("providerOrder", request.data.get("provider_order"))
    provider_order = _parse_provider_order(provider_order_raw)
    total_files_raw = request.data.get("totalFiles", request.data.get("total_files"))
    total_files = _normalize_total_files(total_files_raw)

    job = _create_categorization_job(
        doc_application=doc_application,
        created_by=request.user,
        model=model,
        provider_order=provider_order,
        total_files=total_files,
    )

    return Response(
        {
            "jobId": str(job.id),
            "totalFiles": total_files,
            "status": "queued",
        },
        status=status.HTTP_201_CREATED,
    )


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
    provider_order_raw = request.data.get("providerOrder", request.data.get("provider_order"))
    provider_order = _parse_provider_order(provider_order_raw)

    job = _create_categorization_job(
        doc_application=doc_application,
        created_by=request.user,
        model=model,
        provider_order=provider_order,
        total_files=len(files),
    )

    _upload_files_to_job(job=job, files=files)

    return Response(
        {
            "jobId": str(job.id),
            "totalFiles": len(files),
            "status": "queued",
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def categorization_upload_files(request, job_id):
    """Upload files into an existing categorization job and dispatch item tasks."""
    try:
        job = DocumentCategorizationJob.objects.select_related("doc_application").get(id=job_id)
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

    files = request.FILES.getlist("files")
    if not files:
        return Response(
            {"code": "validation_error", "errors": {"files": ["No files provided."]}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    uploaded_files, dispatched_count = _upload_files_to_job(job=job, files=files)

    return Response(
        {
            "jobId": str(job.id),
            "uploadedFiles": uploaded_files,
            "dispatchedTasks": dispatched_count,
            "status": "processing",
        },
        status=status.HTTP_202_ACCEPTED,
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

        upload_state = {
            "uploaded_bytes": -1,
            "uploaded_files": -1,
            "complete_sent": False,
        }
        unified_progress_state = {
            "percent": -1,
            "phase": "",
            "message": "",
        }

        initial_result = job.result if isinstance(job.result, dict) else {}
        initial_stage = initial_result.get("stage")
        initial_upload = initial_result.get("upload") if isinstance(initial_result.get("upload"), dict) else {}
        initial_total_files = int(initial_upload.get("total_files") or total_files or 0)

        yield _send_event(
            "start",
            {
                "jobId": str(job.id),
                "total": initial_total_files,
                "message": (
                    f"Uploading {initial_total_files} file(s)..."
                    if initial_stage == "uploading"
                    else f"Starting categorization of {initial_total_files} file(s)..."
                ),
            },
        )

        while True:
            job.refresh_from_db()
            total_files = job.total_files

            job_result = job.result if isinstance(job.result, dict) else {}
            upload_info = job_result.get("upload") if isinstance(job_result.get("upload"), dict) else {}

            uploaded_files = int(upload_info.get("uploaded_files") or 0)
            upload_total_files = int(upload_info.get("total_files") or total_files or 0)
            uploaded_bytes = int(upload_info.get("uploaded_bytes") or 0)
            total_bytes = int(upload_info.get("total_bytes") or 0)
            current_file = upload_info.get("current_file")
            upload_complete = bool(upload_info.get("complete"))

            processing_complete = total_files > 0 and int(job.processed_files or 0) >= total_files
            overall_percent = _compute_overall_progress_percent(
                total_files=upload_total_files,
                uploaded_files=uploaded_files,
                uploaded_bytes=uploaded_bytes,
                total_bytes=total_bytes,
                processed_files=int(job.processed_files or 0),
            )

            if upload_complete and not processing_complete:
                phase = "processing"
                unified_message = (
                    f"Processing files... {int(job.processed_files or 0)}/{max(upload_total_files, total_files)}"
                )
            elif processing_complete:
                phase = "completed"
                overall_percent = 100
                unified_message = "Processing complete"
            else:
                phase = "uploading"
                if total_bytes > 0:
                    unified_message = f"Uploading files... {overall_percent}%"
                else:
                    unified_message = f"Uploading files... {uploaded_files}/{upload_total_files}"

            if (
                overall_percent != unified_progress_state["percent"]
                or phase != unified_progress_state["phase"]
                or unified_message != unified_progress_state["message"]
            ):
                yield _send_event(
                    "progress",
                    {
                        "jobId": str(job.id),
                        "phase": phase,
                        "overallPercent": overall_percent,
                        "uploadedFiles": uploaded_files,
                        "totalFiles": upload_total_files,
                        "processedFiles": int(job.processed_files or 0),
                        "uploadedBytes": uploaded_bytes,
                        "totalBytes": total_bytes,
                        "message": unified_message,
                    },
                )
                unified_progress_state["percent"] = overall_percent
                unified_progress_state["phase"] = phase
                unified_progress_state["message"] = unified_message

            if uploaded_bytes != upload_state["uploaded_bytes"] or uploaded_files != upload_state["uploaded_files"]:
                yield _send_event(
                    "upload_progress",
                    {
                        "jobId": str(job.id),
                        "uploadedFiles": uploaded_files,
                        "totalFiles": upload_total_files,
                        "uploadedBytes": uploaded_bytes,
                        "totalBytes": total_bytes,
                        "currentFile": current_file,
                        "message": f"Uploading files... {uploaded_files}/{upload_total_files}",
                    },
                )
                upload_state["uploaded_bytes"] = uploaded_bytes
                upload_state["uploaded_files"] = uploaded_files

            if upload_complete and not upload_state["complete_sent"]:
                yield _send_event(
                    "upload_complete",
                    {
                        "jobId": str(job.id),
                        "uploadedFiles": uploaded_files,
                        "totalFiles": upload_total_files,
                        "uploadedBytes": uploaded_bytes,
                        "totalBytes": total_bytes,
                        "message": f"Upload complete: {uploaded_files}/{upload_total_files} file(s).",
                    },
                )
                upload_state["complete_sent"] = True

            items = list(job.items.all().order_by("sort_index"))

            for item in items:
                state = sent_states.get(
                    item.id,
                    {
                        "upload_started": False,
                        "upload_done": False,
                        "processing": False,
                        "pass2_sent": False,
                        "categorized_sent": False,
                        "validating_sent": False,
                        "validated_sent": False,
                        "done": False,
                    },
                )
                result = item.result or {}
                stage = result.get("stage", "")

                if stage == "uploading" and not state["upload_started"]:
                    yield _send_event(
                        "file_upload_start",
                        {
                            "index": item.sort_index,
                            "filename": item.filename,
                            "message": f"Uploading {item.filename}...",
                        },
                    )
                    state["upload_started"] = True

                if stage != "uploading" and not state["upload_done"]:
                    yield _send_event(
                        "file_uploaded",
                        {
                            "index": item.sort_index,
                            "filename": item.filename,
                            "message": f"Uploaded {item.filename}",
                        },
                    )
                    state["upload_done"] = True

                # Processing started
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

                # Pass 2 fallback triggered
                if stage == "categorizing_pass_2" and not state["pass2_sent"]:
                    yield _send_event(
                        "file_categorizing_pass2",
                        {
                            "index": item.sort_index,
                            "filename": item.filename,
                            "message": f"🔄 Retrying {item.filename} with higher-tier model...",
                        },
                    )
                    state["pass2_sent"] = True

                # Categorized (but may still be validating)
                if item.status == DocumentCategorizationItem.STATUS_CATEGORIZED and not state["categorized_sent"]:
                    pass_used = result.get("pass_used", 1)
                    yield _send_event(
                        "file_categorized",
                        {
                            "index": item.sort_index,
                            "filename": item.filename,
                            "documentType": result.get("document_type"),
                            "documentTypeId": result.get("document_type_id"),
                            "documentId": item.document_id,
                            "confidence": item.confidence,
                            "reasoning": result.get("reasoning", ""),
                            "categorizationPass": pass_used,
                            "aiValidationEnabled": bool(result.get("ai_validation_enabled")),
                            "message": f"✓ {item.filename} → {result.get('document_type', 'Unknown')}"
                            + (f" (pass {pass_used})" if pass_used > 1 else ""),
                        },
                    )
                    state["categorized_sent"] = True

                # Validating in progress
                if stage == "validating" and not state["validating_sent"]:
                    yield _send_event(
                        "file_validating",
                        {
                            "index": item.sort_index,
                            "filename": item.filename,
                            "aiValidationEnabled": bool(result.get("ai_validation_enabled")),
                            "message": f"🔍 Validating {item.filename}...",
                        },
                    )
                    state["validating_sent"] = True

                # Validation complete
                if item.validation_status and not state["validated_sent"]:
                    v_result = item.validation_result or {}
                    yield _send_event(
                        "file_validated",
                        {
                            "index": item.sort_index,
                            "filename": item.filename,
                            "validationStatus": item.validation_status,
                            "validationReasoning": v_result.get("reasoning", ""),
                            "validationNegativeIssues": v_result.get("negative_issues", []),
                            "aiValidationEnabled": bool(result.get("ai_validation_enabled")),
                            "validationConfidence": v_result.get("confidence", 0),
                            "message": f"{'✅' if item.validation_status == 'valid' else '⚠️'} "
                            f"{item.filename}: {item.validation_status}",
                        },
                    )
                    state["validated_sent"] = True

                # Mark done: error items are done immediately; categorized items
                # are done after validation completes (or if no validation will happen)
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

                if item.status == DocumentCategorizationItem.STATUS_CATEGORIZED:
                    # Done when validation is finished or stage is back to "validated"/"categorized"
                    if stage in ("validated", "categorized") and state["categorized_sent"]:
                        # If validation was run, wait for validated_sent; if skipped (stage=categorized), done
                        if stage == "validated" and state["validated_sent"]:
                            state["done"] = True
                        elif stage == "categorized":
                            state["done"] = True

                sent_states[item.id] = state

            all_done = (
                total_files > 0
                and len(sent_states) >= total_files
                and all(s.get("done", False) for s in sent_states.values())
            )

            if total_files > 0 and job.processed_files >= total_files and all_done:
                # Build final results
                results = []
                for item in items:
                    item_result = item.result or {}
                    v_result = item.validation_result or {}
                    results.append(
                        {
                            "itemId": str(item.id),
                            "filename": item.filename,
                            "status": item.status,
                            "documentType": item_result.get("document_type"),
                            "documentTypeId": item_result.get("document_type_id"),
                            "documentId": item.document_id,
                            "confidence": item.confidence,
                            "reasoning": item_result.get("reasoning", ""),
                            "categorizationPass": item_result.get("pass_used", 1),
                            "error": item.error_message or None,
                            "pipelineStage": item_result.get("stage"),
                            "aiValidationEnabled": bool(item_result.get("ai_validation_enabled")),
                            "validationStatus": item.validation_status or None,
                            "validationReasoning": v_result.get("reasoning", ""),
                            "validationNegativeIssues": v_result.get("negative_issues", []),
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
        item_id = mapping["item_id"]
        document_id = mapping["document_id"]

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
            validation_result = item.validation_result or {}
            extracted_expiration_date = extract_validation_expiration_date(validation_result)
            extracted_doc_number = extract_validation_doc_number(validation_result)
            extracted_details_markdown = extract_validation_details_markdown(validation_result)
            if (
                document.doc_type.ai_validation
                and document.doc_type.has_expiration_date
                and extracted_expiration_date
                and not document.expiration_date
            ):
                document.expiration_date = extracted_expiration_date
            if (
                document.doc_type.ai_validation
                and document.doc_type.has_doc_number
                and extracted_doc_number
                and not (document.doc_number or "").strip()
            ):
                document.doc_number = extracted_doc_number
            if (
                document.doc_type.ai_validation
                and document.doc_type.has_details
                and extracted_details_markdown
                and not (document.details or "").strip()
            ):
                document.details = extracted_details_markdown
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


@sse_token_auth_required
def document_validation_stream_sse(request, document_id):
    """SSE endpoint for streaming AI validation progress of a single document."""
    try:
        document = Document.objects.select_related("doc_type").get(id=document_id)
    except Document.DoesNotExist:
        return JsonResponse({"error": "Document not found"}, status=404)

    def event_stream():
        yield _send_event(
            "start",
            {
                "documentId": document.id,
                "message": "Waiting for AI validation...",
            },
        )

        last_status = None
        max_polls = 120  # 60 seconds at 0.5s intervals

        for _ in range(max_polls):
            document.refresh_from_db()
            current_status = document.ai_validation_status

            if current_status != last_status:
                if current_status == Document.AI_VALIDATION_VALIDATING:
                    yield _send_event(
                        "validating",
                        {
                            "documentId": document.id,
                            "message": f"🔍 Validating {document.doc_type.name}...",
                        },
                    )

                elif current_status in (
                    Document.AI_VALIDATION_VALID,
                    Document.AI_VALIDATION_INVALID,
                    Document.AI_VALIDATION_ERROR,
                ):
                    v_result = document.ai_validation_result or {}
                    yield _send_event(
                        "complete",
                        {
                            "documentId": document.id,
                            "validationStatus": current_status,
                            "validationResult": v_result,
                            "message": f"{'✅' if current_status == 'valid' else '⚠️'} "
                            f"{document.doc_type.name}: {current_status}",
                        },
                    )
                    return

                last_status = current_status

            yield ": keep-alive\n\n"
            time.sleep(0.5)

        # Timeout
        yield _send_event(
            "timeout",
            {
                "documentId": document.id,
                "message": "Validation timed out.",
            },
        )

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
