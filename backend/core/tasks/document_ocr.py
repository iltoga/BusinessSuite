import os
import traceback
import json

from core.models import DocumentOCRJob
from core.services.ai_document_ocr_service import extract_document_structured_output
from core.services.logger_service import Logger
from core.tasks.idempotency import acquire_task_lock, build_task_lock_key, release_task_lock
from core.tasks.runtime import QUEUE_REALTIME, db_task
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
        if bounded - last_progress < 2 and bounded < 94:
            return
        last_progress = bounded
        job.progress = bounded
        job.save(update_fields=["progress", "updated_at"])

    return DocumentParser.extract_text_from_file(
        abs_path,
        progress_callback=_on_progress,
    ) or ""


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


@db_task(queue=QUEUE_REALTIME)
def run_document_ocr_job(job_id: str) -> None:
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

        job.status = DocumentOCRJob.STATUS_PROCESSING
        job.progress = 5
        job.error_message = ""
        job.traceback = ""
        job.save(update_fields=["status", "progress", "error_message", "traceback", "updated_at"])

        try:
            with get_local_file_path(job.file_path) as abs_path:
                if not os.path.exists(abs_path):
                    raise FileNotFoundError(f"File not found: {abs_path}")

                job.progress = 35
                job.save(update_fields=["progress", "updated_at"])

                extracted_text = ""
                structured_fields, doc_type_name = _resolve_structured_fields_for_job(job)
                if structured_fields and doc_type_name:
                    try:
                        with open(abs_path, "rb") as source:
                            file_bytes = source.read()

                        job.progress = 60
                        job.save(update_fields=["progress", "updated_at"])
                        structured_data = extract_document_structured_output(
                            file_bytes=file_bytes,
                            filename=os.path.basename(job.file_path),
                            doc_type_name=doc_type_name,
                            fields=structured_fields,
                        )
                        extracted_text = json.dumps(structured_data, indent=2, ensure_ascii=False)
                    except Exception as extraction_error:
                        logger.warning(
                            "Structured document OCR failed for job %s; falling back to parser OCR. error=%s",
                            job_id,
                            extraction_error,
                        )
                        extracted_text = _extract_plain_text_with_progress(job, abs_path)
                else:
                    extracted_text = _extract_plain_text_with_progress(job, abs_path)

                if job.progress < 95:
                    job.progress = 95
                    job.save(update_fields=["progress", "updated_at"])

                job.result_text = extracted_text
                job.status = DocumentOCRJob.STATUS_COMPLETED
                job.progress = 100
                job.error_message = ""
                job.traceback = ""
                job.save(
                    update_fields=["status", "progress", "result_text", "error_message", "traceback", "updated_at"]
                )
                logger.info(f"Document OCR job {job_id} completed")

        except Exception as exc:
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
