from __future__ import annotations

import json
from typing import Any

from django.urls import reverse

from core.services.ocr_preview_storage import get_ocr_preview_url


def first_present(payload: dict[str, Any] | None, *keys: str, default: Any = None) -> Any:
    if not isinstance(payload, dict):
        return default
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return default


def _coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_datetime(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return str(value)


def _snake_to_camel_key(key: str) -> str:
    if "_" not in key:
        return key

    parts = [part for part in key.split("_") if part]
    if not parts:
        return key

    head, *tail = parts
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


def camelize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {_snake_to_camel_key(str(key)): camelize_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [camelize_payload(item) for item in value]
    if isinstance(value, tuple):
        return [camelize_payload(item) for item in value]
    return value


def normalize_ocr_result_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    normalized = camelize_payload(payload)
    if not isinstance(normalized, dict):
        return None

    preview_storage_path = first_present(payload, "previewStoragePath", "preview_storage_path")
    preview_url = first_present(payload, "previewUrl", "preview_url")
    if not preview_url and preview_storage_path:
        preview_url = get_ocr_preview_url(str(preview_storage_path))
    if preview_url:
        normalized["previewUrl"] = str(preview_url)
    normalized.pop("previewStoragePath", None)
    return normalized


def build_async_job_links(
    request,
    job_id: Any,
    *,
    status_route: str | None = None,
    stream_route: str | None = None,
    download_route: str | None = None,
) -> dict[str, str]:
    links: dict[str, str] = {}
    job_id_text = str(job_id)

    if status_route:
        links["statusUrl"] = request.build_absolute_uri(reverse(status_route, kwargs={"job_id": job_id_text}))
    if stream_route:
        links["streamUrl"] = request.build_absolute_uri(reverse(stream_route, kwargs={"job_id": job_id_text}))
    if download_route:
        links["downloadUrl"] = request.build_absolute_uri(reverse(download_route, kwargs={"job_id": job_id_text}))
    return links


def build_async_job_start_payload(
    *,
    job_id: Any,
    status: str,
    progress: int,
    queued: bool,
    deduplicated: bool,
    links: dict[str, str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "jobId": str(job_id),
        "status": status,
        "progress": int(progress or 0),
        "queued": bool(queued),
        "deduplicated": bool(deduplicated),
    }
    if links:
        payload.update(links)
    if extra:
        payload.update(extra)
    return payload


def serialize_async_job_payload(job) -> dict[str, Any]:
    result = camelize_payload(job.result) if isinstance(job.result, dict) else job.result
    return {
        "id": str(job.id),
        "jobId": str(job.id),
        "taskName": job.task_name,
        "status": job.status,
        "progress": int(job.progress or 0),
        "message": job.message,
        "result": result,
        "errorMessage": job.error_message,
        "createdAt": _coerce_datetime(getattr(job, "created_at", None)),
        "updatedAt": _coerce_datetime(getattr(job, "updated_at", None)),
        "createdBy": int(job.created_by_id) if job.created_by_id is not None else None,
    }


def normalize_async_job_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    progress = _coerce_int(first_present(payload, "progress"))
    job_id = first_present(payload, "jobId", "id", "job_id")
    status = first_present(payload, "status")
    if not job_id or status is None or progress is None:
        return None
    return {
        "id": str(job_id),
        "jobId": str(job_id),
        "taskName": first_present(payload, "taskName", "task_name", default=""),
        "status": str(status),
        "progress": progress,
        "message": first_present(payload, "message"),
        "result": camelize_payload(first_present(payload, "result")),
        "errorMessage": first_present(payload, "errorMessage", "error_message", "error", default=""),
        "createdAt": _coerce_datetime(first_present(payload, "createdAt", "created_at")),
        "updatedAt": _coerce_datetime(first_present(payload, "updatedAt", "updated_at")),
        "createdBy": _coerce_int(first_present(payload, "createdBy", "created_by")),
    }


def serialize_ocr_job_payload(job) -> dict[str, Any]:
    result = normalize_ocr_result_payload(job.result)
    return {
        "jobId": str(job.id),
        "status": job.status,
        "progress": int(job.progress or 0),
        "result": result,
        "errorMessage": job.error_message,
    }


def normalize_ocr_job_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    progress = _coerce_int(first_present(payload, "progress"))
    job_id = first_present(payload, "jobId", "id", "job_id")
    status = first_present(payload, "status")
    if not job_id or status is None or progress is None:
        return None
    return {
        "jobId": str(job_id),
        "status": str(status),
        "progress": progress,
        "result": normalize_ocr_result_payload(first_present(payload, "result")),
        "errorMessage": first_present(payload, "errorMessage", "error_message", "error", default=""),
    }


def serialize_document_ocr_job_payload(job) -> dict[str, Any]:
    result_text = job.result_text
    structured_data = None
    if result_text:
        try:
            parsed_result = json.loads(result_text)
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed_result = None
        if isinstance(parsed_result, dict):
            structured_data = camelize_payload(parsed_result)
    return {
        "jobId": str(job.id),
        "status": job.status,
        "progress": int(job.progress or 0),
        "resultText": result_text,
        "structuredData": structured_data,
        "errorMessage": job.error_message,
    }


def normalize_document_ocr_job_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    progress = _coerce_int(first_present(payload, "progress"))
    job_id = first_present(payload, "jobId", "id", "job_id")
    status = first_present(payload, "status")
    if not job_id or status is None or progress is None:
        return None
    text = first_present(payload, "resultText", "result_text", "text", default="")
    structured_data = first_present(payload, "structuredData", "structured_data")
    return {
        "jobId": str(job_id),
        "status": str(status),
        "progress": progress,
        "resultText": text,
        "structuredData": camelize_payload(structured_data) if isinstance(structured_data, dict) else structured_data,
        "errorMessage": first_present(payload, "errorMessage", "error_message", "error", default=""),
    }


def serialize_invoice_download_job_payload(job) -> dict[str, Any]:
    return {
        "jobId": str(job.id),
        "status": job.status,
        "progress": int(job.progress or 0),
        "formatType": job.format_type,
        "outputPath": job.output_path,
        "errorMessage": job.error_message,
    }


def normalize_invoice_download_job_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    progress = _coerce_int(first_present(payload, "progress"))
    job_id = first_present(payload, "jobId", "id", "job_id")
    status = first_present(payload, "status")
    if not job_id or status is None or progress is None:
        return None
    return {
        "jobId": str(job_id),
        "status": str(status),
        "progress": progress,
        "formatType": first_present(payload, "formatType", "format_type"),
        "outputPath": first_present(payload, "outputPath", "output_path", default=""),
        "errorMessage": first_present(payload, "errorMessage", "error_message", default=""),
    }


def serialize_invoice_import_job_payload(job) -> dict[str, Any]:
    return {
        "jobId": str(job.id),
        "status": job.status,
        "progress": int(job.progress or 0),
        "totalFiles": int(job.total_files or 0),
        "processedFiles": int(job.processed_files or 0),
        "importedCount": int(job.imported_count or 0),
        "duplicateCount": int(job.duplicate_count or 0),
        "errorCount": int(job.error_count or 0),
        "result": camelize_payload(job.result) if isinstance(job.result, dict) else job.result,
        "errorMessage": job.error_message,
    }


def normalize_invoice_import_job_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    progress = _coerce_int(first_present(payload, "progress"))
    total_files = _coerce_int(first_present(payload, "totalFiles", "total_files"))
    processed_files = _coerce_int(first_present(payload, "processedFiles", "processed_files"))
    imported_count = _coerce_int(first_present(payload, "importedCount", "imported_count"))
    duplicate_count = _coerce_int(first_present(payload, "duplicateCount", "duplicate_count"))
    error_count = _coerce_int(first_present(payload, "errorCount", "error_count"))
    job_id = first_present(payload, "jobId", "id", "job_id")
    status = first_present(payload, "status")
    if (
        not job_id
        or status is None
        or None
        in {
            progress,
            total_files,
            processed_files,
            imported_count,
            duplicate_count,
            error_count,
        }
    ):
        return None
    return {
        "jobId": str(job_id),
        "status": str(status),
        "progress": progress,
        "totalFiles": total_files,
        "processedFiles": processed_files,
        "importedCount": imported_count,
        "duplicateCount": duplicate_count,
        "errorCount": error_count,
        "result": camelize_payload(first_present(payload, "result")),
        "errorMessage": first_present(payload, "errorMessage", "error_message", default=""),
    }


def serialize_invoice_import_item_payload(item) -> dict[str, Any]:
    return {
        "itemId": str(item.id),
        "jobId": str(item.job_id),
        "index": int(item.sort_index or 0),
        "filename": item.filename,
        "status": item.status,
        "result": camelize_payload(item.result) if isinstance(item.result, dict) else item.result,
        "errorMessage": item.error_message,
    }


def normalize_invoice_import_item_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    item_id = first_present(payload, "itemId", "id", "item_id")
    job_id = first_present(payload, "jobId", "job_id")
    index = _coerce_int(first_present(payload, "index", "sort_index"))
    filename = first_present(payload, "filename")
    status = first_present(payload, "status")
    if not item_id or not job_id or index is None or not filename or status is None:
        return None
    return {
        "itemId": str(item_id),
        "jobId": str(job_id),
        "index": index,
        "filename": str(filename),
        "status": str(status),
        "result": camelize_payload(first_present(payload, "result")),
        "errorMessage": first_present(payload, "errorMessage", "error_message", default=""),
    }
