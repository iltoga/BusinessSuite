import mimetypes
import os
import traceback
from io import BytesIO

from core.models import OCRJob
from core.queue import enqueue_job
from core.services.ai_client import AIConnectionError
from core.services.logger_service import Logger
from core.services.ocr_preview_storage import upload_ocr_preview_bytes
from core.tasks.idempotency import acquire_task_lock, build_task_lock_key, release_task_lock
from core.utils.imgutils import convert_and_resize_image
from core.utils.passport_ocr import extract_mrz_data, extract_passport_with_ai
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile

logger = Logger.get_logger(__name__)

OCR_MAX_RETRIES = 2
OCR_RETRY_DELAY_SECONDS = 10
ENTRYPOINT_RUN_OCR_JOB = "core.run_ocr_job"

def enqueue_run_ocr_job(*, job_id: str, retry_attempt: int = 0, delay_seconds: int | float | None = None) -> str | None:
    return enqueue_job(
        entrypoint=ENTRYPOINT_RUN_OCR_JOB,
        payload={"job_id": str(job_id), "retry_attempt": int(retry_attempt)},
        delay_seconds=delay_seconds,
        run_local=run_ocr_job,
    )


def run_ocr_job(job_id: str, retry_attempt: int = 0) -> None:
    lock_key = build_task_lock_key(namespace="ocr_job", item_id=str(job_id))
    lock_token = acquire_task_lock(lock_key)
    if not lock_token:
        logger.warning("OCR task skipped due to lock contention: job_id=%s", job_id)
        return

    try:
        logger.info("Starting OCR job %s (retry_attempt=%s)", job_id, retry_attempt)
        try:
            job = OCRJob.objects.get(id=job_id)
        except OCRJob.DoesNotExist:
            logger.error(f"OCRJob {job_id} not found")
            return

        terminal_statuses = {OCRJob.STATUS_COMPLETED, OCRJob.STATUS_FAILED}
        if job.status in terminal_statuses:
            logger.info("Skipping OCR job already in terminal state: job_id=%s status=%s", job_id, job.status)
            return

        job.status = OCRJob.STATUS_PROCESSING
        job.progress = 5
        job.error_message = ""
        job.traceback = ""
        job.save(update_fields=["status", "progress", "error_message", "traceback", "updated_at"])

        logger.info(f"Processing file: {job.file_path}")

        try:
            file_name = os.path.basename(job.file_path)
            file_type = mimetypes.guess_type(file_name)[0]

            with default_storage.open(job.file_path, "rb") as handle:
                file_bytes = handle.read()

            uploaded_file = SimpleUploadedFile(
                name=file_name,
                content=file_bytes,
                content_type=file_type or "application/octet-stream",
            )

            if not file_type:
                file_type = uploaded_file.content_type

            job.progress = 35
            job.save(update_fields=["progress", "updated_at"])

            use_ai = bool(job.request_params.get("use_ai"))
            logger.info(f"Extracting data (use_ai={use_ai})")

            if use_ai:
                mrz_data = extract_passport_with_ai(uploaded_file, use_ai=True)
            else:
                mrz_data = extract_mrz_data(uploaded_file)

            job.progress = 75
            job.save(update_fields=["progress", "updated_at"])

            img_preview = bool(job.request_params.get("img_preview"))
            resize = bool(job.request_params.get("resize"))
            width = job.request_params.get("width")
            if width:
                width = int(width)

            preview_storage_path = None
            if img_preview or resize:
                logger.info("Generating image preview/resized version")
                with default_storage.open(job.file_path, "rb") as handle:
                    img, _ = convert_and_resize_image(
                        handle,
                        file_type,
                        return_encoded=False,
                        resize=resize,
                        base_width=width,
                    )
                    if img_preview:
                        preview_buffer = BytesIO()
                        img.save(preview_buffer, format="PNG", compress_level=1, optimize=False)
                        preview_storage_path = upload_ocr_preview_bytes(
                            job_id=str(job.id),
                            image_bytes=preview_buffer.getvalue(),
                            extension="png",
                            overwrite=True,
                        )

            response_data = {"mrz_data": mrz_data}
            if preview_storage_path:
                response_data["preview_storage_path"] = preview_storage_path
                response_data["preview_mime_type"] = "image/png"
            if isinstance(mrz_data, dict) and "ai_error" in mrz_data:
                response_data["ai_warning"] = mrz_data.pop("ai_error")

            job.result = response_data
            job.status = OCRJob.STATUS_COMPLETED
            job.progress = 100
            job.error_message = ""
            job.traceback = ""
            job.save(update_fields=["status", "progress", "result", "error_message", "traceback", "updated_at"])
            logger.info(f"OCR job {job_id} completed successfully")

        except AIConnectionError as exc:
            if retry_attempt < OCR_MAX_RETRIES:
                retries_left = OCR_MAX_RETRIES - retry_attempt
                logger.warning(
                    "OCR job %s encountered AI connection error. Retrying in %ss... (%s left)",
                    job_id,
                    OCR_RETRY_DELAY_SECONDS,
                    retries_left,
                )
                job.error_message = f"AI connection error, retrying... ({retries_left} left)"
                job.save(update_fields=["error_message", "updated_at"])
                enqueue_run_ocr_job(
                    job_id=job_id,
                    retry_attempt=retry_attempt + 1,
                    delay_seconds=OCR_RETRY_DELAY_SECONDS,
                )
                return

            logger.error(f"OCR job {job_id} failed after retries: {str(exc)}")
            job.status = OCRJob.STATUS_FAILED
            job.error_message = f"AI extraction failed after retries: {str(exc)}"
            job.progress = 100
            job.save(update_fields=["status", "progress", "error_message", "updated_at"])

        except Exception as exc:
            full_traceback = traceback.format_exc()
            logger.error(f"OCR job {job_id} failed: {str(exc)}\n{full_traceback}")

            job.status = OCRJob.STATUS_FAILED
            job.error_message = str(exc)
            job.traceback = full_traceback
            job.progress = 100
            job.save(update_fields=["status", "progress", "error_message", "traceback", "updated_at"])
            return
    finally:
        release_task_lock(lock_key, lock_token)
