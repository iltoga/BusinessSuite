from __future__ import annotations

from typing import Any


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


def serialize_async_job_payload(job) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "status": job.status,
        "progress": int(job.progress or 0),
        "message": job.message,
        "result": job.result,
        "errorMessage": job.error_message,
        "error_message": job.error_message,
    }


def normalize_async_job_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    progress = _coerce_int(first_present(payload, "progress"))
    job_id = first_present(payload, "id", "jobId", "job_id")
    status = first_present(payload, "status")
    if not job_id or status is None or progress is None:
        return None
    return {
        "id": str(job_id),
        "status": str(status),
        "progress": progress,
        "message": first_present(payload, "message"),
        "result": first_present(payload, "result"),
        "errorMessage": first_present(payload, "errorMessage", "error_message", default=""),
        "error_message": first_present(payload, "error_message", "errorMessage", default=""),
    }


def serialize_ocr_job_payload(job) -> dict[str, Any]:
    return {
        "jobId": str(job.id),
        "job_id": str(job.id),
        "status": job.status,
        "progress": int(job.progress or 0),
        "result": job.result,
        "error": job.error_message,
        "errorMessage": job.error_message,
        "error_message": job.error_message,
    }


def normalize_ocr_job_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    progress = _coerce_int(first_present(payload, "progress"))
    job_id = first_present(payload, "jobId", "job_id", "id")
    status = first_present(payload, "status")
    if not job_id or status is None or progress is None:
        return None
    return {
        "jobId": str(job_id),
        "job_id": str(job_id),
        "status": str(status),
        "progress": progress,
        "result": first_present(payload, "result"),
        "error": first_present(payload, "error", "errorMessage", "error_message", default=""),
        "errorMessage": first_present(payload, "errorMessage", "error_message", "error", default=""),
        "error_message": first_present(payload, "error_message", "errorMessage", "error", default=""),
    }


def serialize_document_ocr_job_payload(job) -> dict[str, Any]:
    return {
        "jobId": str(job.id),
        "job_id": str(job.id),
        "status": job.status,
        "progress": int(job.progress or 0),
        "text": job.result_text,
        "resultText": job.result_text,
        "result_text": job.result_text,
        "error": job.error_message,
        "errorMessage": job.error_message,
        "error_message": job.error_message,
    }


def normalize_document_ocr_job_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    progress = _coerce_int(first_present(payload, "progress"))
    job_id = first_present(payload, "jobId", "job_id", "id")
    status = first_present(payload, "status")
    if not job_id or status is None or progress is None:
        return None
    text = first_present(payload, "text", "resultText", "result_text", default="")
    return {
        "jobId": str(job_id),
        "job_id": str(job_id),
        "status": str(status),
        "progress": progress,
        "text": text,
        "resultText": text,
        "result_text": text,
        "error": first_present(payload, "error", "errorMessage", "error_message", default=""),
        "errorMessage": first_present(payload, "errorMessage", "error_message", "error", default=""),
        "error_message": first_present(payload, "error_message", "errorMessage", "error", default=""),
    }


def serialize_invoice_download_job_payload(job) -> dict[str, Any]:
    return {
        "jobId": str(job.id),
        "job_id": str(job.id),
        "status": job.status,
        "progress": int(job.progress or 0),
        "formatType": job.format_type,
        "format_type": job.format_type,
        "outputPath": job.output_path,
        "output_path": job.output_path,
        "errorMessage": job.error_message,
        "error_message": job.error_message,
    }


def normalize_invoice_download_job_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    progress = _coerce_int(first_present(payload, "progress"))
    job_id = first_present(payload, "jobId", "job_id", "id")
    status = first_present(payload, "status")
    if not job_id or status is None or progress is None:
        return None
    return {
        "jobId": str(job_id),
        "job_id": str(job_id),
        "status": str(status),
        "progress": progress,
        "formatType": first_present(payload, "formatType", "format_type"),
        "format_type": first_present(payload, "format_type", "formatType"),
        "outputPath": first_present(payload, "outputPath", "output_path", default=""),
        "output_path": first_present(payload, "output_path", "outputPath", default=""),
        "errorMessage": first_present(payload, "errorMessage", "error_message", default=""),
        "error_message": first_present(payload, "error_message", "errorMessage", default=""),
    }


def serialize_invoice_import_job_payload(job) -> dict[str, Any]:
    return {
        "jobId": str(job.id),
        "job_id": str(job.id),
        "status": job.status,
        "progress": int(job.progress or 0),
        "totalFiles": int(job.total_files or 0),
        "total_files": int(job.total_files or 0),
        "processedFiles": int(job.processed_files or 0),
        "processed_files": int(job.processed_files or 0),
        "importedCount": int(job.imported_count or 0),
        "imported_count": int(job.imported_count or 0),
        "duplicateCount": int(job.duplicate_count or 0),
        "duplicate_count": int(job.duplicate_count or 0),
        "errorCount": int(job.error_count or 0),
        "error_count": int(job.error_count or 0),
        "result": job.result,
        "errorMessage": job.error_message,
        "error_message": job.error_message,
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
    job_id = first_present(payload, "jobId", "job_id", "id")
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
        "job_id": str(job_id),
        "status": str(status),
        "progress": progress,
        "totalFiles": total_files,
        "total_files": total_files,
        "processedFiles": processed_files,
        "processed_files": processed_files,
        "importedCount": imported_count,
        "imported_count": imported_count,
        "duplicateCount": duplicate_count,
        "duplicate_count": duplicate_count,
        "errorCount": error_count,
        "error_count": error_count,
        "result": first_present(payload, "result"),
        "errorMessage": first_present(payload, "errorMessage", "error_message", default=""),
        "error_message": first_present(payload, "error_message", "errorMessage", default=""),
    }


def serialize_invoice_import_item_payload(item) -> dict[str, Any]:
    return {
        "itemId": str(item.id),
        "item_id": str(item.id),
        "jobId": str(item.job_id),
        "job_id": str(item.job_id),
        "index": int(item.sort_index or 0),
        "sort_index": int(item.sort_index or 0),
        "filename": item.filename,
        "status": item.status,
        "result": item.result,
        "errorMessage": item.error_message,
        "error_message": item.error_message,
    }


def normalize_invoice_import_item_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    item_id = first_present(payload, "itemId", "item_id", "id")
    job_id = first_present(payload, "jobId", "job_id")
    index = _coerce_int(first_present(payload, "index", "sort_index"))
    filename = first_present(payload, "filename")
    status = first_present(payload, "status")
    if not item_id or not job_id or index is None or not filename or status is None:
        return None
    return {
        "itemId": str(item_id),
        "item_id": str(item_id),
        "jobId": str(job_id),
        "job_id": str(job_id),
        "index": index,
        "sort_index": index,
        "filename": str(filename),
        "status": str(status),
        "result": first_present(payload, "result"),
        "errorMessage": first_present(payload, "errorMessage", "error_message", default=""),
        "error_message": first_present(payload, "error_message", "errorMessage", default=""),
    }
