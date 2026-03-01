import os
import traceback

from core.models import DocumentOCRJob
from core.queue import enqueue_job
from core.services.logger_service import Logger
from core.tasks.idempotency import acquire_task_lock, build_task_lock_key, release_task_lock
from core.utils.storage_helpers import get_local_file_path
from invoices.services.document_parser import DocumentParser

logger = Logger.get_logger(__name__)

ENTRYPOINT_RUN_DOCUMENT_OCR_JOB = "core.run_document_ocr_job"

def enqueue_run_document_ocr_job(*, job_id: str) -> str | None:
    return enqueue_job(
        entrypoint=ENTRYPOINT_RUN_DOCUMENT_OCR_JOB,
        payload={"job_id": str(job_id)},
        run_local=run_document_ocr_job,
    )


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

                last_progress = 35

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

                extracted_text = DocumentParser.extract_text_from_file(
                    abs_path,
                    progress_callback=_on_progress,
                )
                if job.progress < 95:
                    job.progress = 95
                    job.save(update_fields=["progress", "updated_at"])

                job.result_text = extracted_text or ""
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
