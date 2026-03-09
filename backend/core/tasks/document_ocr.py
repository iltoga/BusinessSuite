import json
import os
import traceback

from core.models import DocumentOCRJob
from core.services.ai_client import get_ai_user_message
from core.services.ai_document_ocr_service import extract_document_structured_output
from core.services.logger_service import Logger
from core.tasks.idempotency import acquire_task_lock, build_task_lock_key, release_task_lock
from core.tasks.progress import persist_progress
from core.tasks.runtime import QUEUE_DOC_CONVERSION, db_task, retry_on_transient_external_failure
from core.utils.document_type_ai_fields import parse_structured_output_fields
from core.utils.storage_helpers import get_local_file_path
from invoices.services.document_parser import DocumentParser
from products.models.document_type import DocumentType

logger = Logger.get_logger(__name__)


def _extract_plain_text_with_progress(job: DocumentOCRJob, abs_path: str) -> str:
    last_progress = max(35, int(job.progress or 35))

    def _on_progress(progress: int) -> None:
        nonlocal last_progress
        bounded = max(36, min(94, int(progress)))
        if bounded <= last_progress:
            return
        # Avoid excessive writes while still keeping UI visibly alive.
        if bounded - last_progress < 5 and bounded < 94:
            return
        last_progress = bounded
        persist_progress(job, progress=bounded, min_delta=5)

    return (
        DocumentParser.extract_text_from_file(
            abs_path,
            progress_callback=_on_progress,
        )
        or ""
    )


def _resolve_structured_fields_for_job(job: DocumentOCRJob) -> tuple[list, str | None]:
    params = job.request_params if isinstance(job.request_params, dict) else {}
    raw_doc_type_id = params.get("doc_type_id")
    if not raw_doc_type_id:
        return [], None

    try:
        doc_type_id = int(raw_doc_type_id)
    except (TypeError, ValueError):
        return [], None

    doc_type = (
        DocumentType.objects.filter(id=doc_type_id)
        .only("id", "name", "ai_structured_output", "validation_rule_ai_negative")
        .first()
    )
    if not doc_type:
        return [], None

    fields = parse_structured_output_fields(doc_type.ai_structured_output)
    if fields:
        return fields, doc_type.name

    # Backward compatibility: if old data lived in validation_rule_ai_negative as JSON array.
    fallback_fields = parse_structured_output_fields(doc_type.validation_rule_ai_negative)
    return fallback_fields, doc_type.name


@db_task(
    context=True,
    queue=QUEUE_DOC_CONVERSION,
    queue_defaults=True,
    retry_when=retry_on_transient_external_failure,
)
def run_document_ocr_job(job_id: str, task=None) -> None:
    lock_key = build_task_lock_key(namespace="document_ocr_job", item_id=str(job_id))
    lock_token = acquire_task_lock(lock_key)
    if not lock_token:
        logger.warning("Document OCR task skipped due to lock contention: job_id=%s", job_id)
        return

    try:
        logger.info(f"Starting document OCR job {job_id}")
        try:
            job = DocumentOCRJob.objects.get(id=job_id)
        except DocumentOCRJob.DoesNotExist:
            logger.error(f"DocumentOCRJob {job_id} not found")
            return

        terminal_statuses = {DocumentOCRJob.STATUS_COMPLETED, DocumentOCRJob.STATUS_FAILED}
        if job.status in terminal_statuses:
            logger.info("Skipping document OCR job already in terminal state: job_id=%s status=%s", job_id, job.status)
            return

        job.error_message = ""
        job.traceback = ""
        persist_progress(
            job,
            status=DocumentOCRJob.STATUS_PROCESSING,
            progress=5,
            force=True,
            extra_fields={"error_message": "", "traceback": ""},
        )

        try:
            with get_local_file_path(job.file_path) as abs_path:
                if not os.path.exists(abs_path):
                    raise FileNotFoundError(f"File not found: {abs_path}")

                persist_progress(job, progress=35, force=True)

                extracted_text = ""
                structured_fields, doc_type_name = _resolve_structured_fields_for_job(job)
                if structured_fields and doc_type_name:
                    try:
                        with open(abs_path, "rb") as source:
                            file_bytes = source.read()

                        persist_progress(job, progress=60, force=True)
                        structured_data = extract_document_structured_output(
                            file_bytes=file_bytes,
                            filename=os.path.basename(job.file_path),
                            doc_type_name=doc_type_name,
                            fields=structured_fields,
                        )
                        extracted_text = json.dumps(structured_data, indent=2, ensure_ascii=False)
                    except Exception as extraction_error:
                        if retry_on_transient_external_failure(0, extraction_error):
                            if task and task.retries > 0:
                                logger.warning(
                                    "Structured document OCR transient failure for job %s on attempt %s/%s. retries_remaining=%s queue=%s time_limit_ms=%s error=%s",
                                    job_id,
                                    getattr(task, "attempt", "?"),
                                    getattr(task, "max_retries", 0) + 1 if task else "?",
                                    task.retries,
                                    getattr(task, "queue_name", QUEUE_DOC_CONVERSION),
                                    getattr(task, "time_limit_ms", None),
                                    extraction_error,
                                )
                                job.error_message = f"Structured AI extraction temporarily unavailable. Retrying... ({task.retries} left)"
                                job.save(update_fields=["error_message", "updated_at"])
                                raise

                            logger.warning(
                                "Structured document OCR retries exhausted for job %s; falling back to parser OCR. error=%s",
                                job_id,
                                extraction_error,
                            )
                            extracted_text = _extract_plain_text_with_progress(job, abs_path)
                            job.error_message = get_ai_user_message(extraction_error)
                            job.save(update_fields=["error_message", "updated_at"])
                        else:
                            logger.warning(
                                "Structured document OCR failed for job %s due to a non-retryable parsing/validation issue; falling back to parser OCR. error=%s",
                                job_id,
                                extraction_error,
                            )
                            extracted_text = _extract_plain_text_with_progress(job, abs_path)
                            job.error_message = get_ai_user_message(extraction_error)
                            job.save(update_fields=["error_message", "updated_at"])
                else:
                    extracted_text = _extract_plain_text_with_progress(job, abs_path)

                if job.progress < 95:
                    persist_progress(job, progress=95, force=True)

                job.result_text = extracted_text
                job.status = DocumentOCRJob.STATUS_COMPLETED
                job.progress = 100
                if not extracted_text or not job.error_message:
                    job.error_message = ""
                job.traceback = ""
                job.save(
                    update_fields=["status", "progress", "result_text", "error_message", "traceback", "updated_at"]
                )
                logger.info(f"Document OCR job {job_id} completed")

        except Exception as exc:
            if task and task.retries > 0 and retry_on_transient_external_failure(task.retries_used, exc):
                logger.warning(
                    "Document OCR retry scheduled for job %s on attempt %s/%s. retries_remaining=%s queue=%s time_limit_ms=%s error=%s",
                    job_id,
                    getattr(task, "attempt", "?"),
                    getattr(task, "max_retries", 0) + 1 if task else "?",
                    task.retries,
                    getattr(task, "queue_name", QUEUE_DOC_CONVERSION),
                    getattr(task, "time_limit_ms", None),
                    exc,
                )
                job.status = DocumentOCRJob.STATUS_PROCESSING
                job.progress = min(95, max(5, int(job.progress or 5)))
                job.error_message = get_ai_user_message(exc)
                job.traceback = ""
                job.save(update_fields=["status", "progress", "error_message", "traceback", "updated_at"])
                raise

            full_traceback = traceback.format_exc()
            logger.error(f"Document OCR job {job_id} failed: {str(exc)}\n{full_traceback}")
            job.status = DocumentOCRJob.STATUS_FAILED
            job.error_message = str(exc)
            job.traceback = full_traceback
            job.progress = 100
            job.save(update_fields=["status", "progress", "error_message", "traceback", "updated_at"])
            return
    finally:
        release_task_lock(lock_key, lock_token)
