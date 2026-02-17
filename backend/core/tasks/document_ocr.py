import os
import traceback

from huey.contrib.djhuey import db_task

from core.models import DocumentOCRJob
from core.services.logger_service import Logger
from core.utils.storage_helpers import get_local_file_path
from invoices.services.document_parser import DocumentParser

logger = Logger.get_logger(__name__)


@db_task()
def run_document_ocr_job(job_id: str) -> None:
    logger.info(f"Starting document OCR job {job_id}")
    try:
        job = DocumentOCRJob.objects.get(id=job_id)
    except DocumentOCRJob.DoesNotExist:
        logger.error(f"DocumentOCRJob {job_id} not found")
        return

    job.status = DocumentOCRJob.STATUS_PROCESSING
    job.progress = 5
    job.save(update_fields=["status", "progress", "updated_at"])

    try:
        with get_local_file_path(job.file_path) as abs_path:
            if not os.path.exists(abs_path):
                raise FileNotFoundError(f"File not found: {abs_path}")

            job.progress = 35
            job.save(update_fields=["progress", "updated_at"])

            extracted_text = DocumentParser.extract_text_from_file(abs_path)
            job.progress = 85
            job.save(update_fields=["progress", "updated_at"])

            job.result_text = extracted_text or ""
            job.status = DocumentOCRJob.STATUS_COMPLETED
            job.progress = 100
            job.save(update_fields=["status", "progress", "result_text", "updated_at"])
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
