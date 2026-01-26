import logging
import mimetypes
import os
import traceback

from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from huey.contrib.djhuey import db_task

from core.models import OCRJob
from core.services.ai_client import AIConnectionError
from core.utils.imgutils import convert_and_resize_image
from core.utils.passport_ocr import extract_mrz_data, extract_passport_with_ai

logger = logging.getLogger(__name__)


@db_task(retries=2, retry_delay=10, context=True)
def run_ocr_job(job_id: str, task=None) -> None:
    logger.info(f"Starting OCR job {job_id} (retries remaining: {task.retries if task else 'N/A'})")
    try:
        job = OCRJob.objects.get(id=job_id)
    except OCRJob.DoesNotExist:
        logger.error(f"OCRJob {job_id} not found")
        return

    job.status = OCRJob.STATUS_PROCESSING
    job.progress = 5
    job.save(update_fields=["status", "progress", "updated_at"])

    abs_path = default_storage.path(job.file_path)
    logger.info(f"Processing file: {job.file_path}")

    try:
        file_name = os.path.basename(abs_path)
        file_type = mimetypes.guess_type(file_name)[0]

        with open(abs_path, "rb") as handle:
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

        img_str = None
        if img_preview or resize:
            logger.info("Generating image preview/resized version")
            with open(abs_path, "rb") as handle:
                _, img_bytes = convert_and_resize_image(
                    handle,
                    file_type,
                    return_encoded=img_preview,
                    resize=resize,
                    base_width=width,
                )
                if img_preview:
                    img_str = img_bytes.decode("utf-8") if isinstance(img_bytes, bytes) else img_bytes

        response_data = {"b64_resized_image": img_str, "mrz_data": mrz_data}
        if isinstance(mrz_data, dict) and "ai_error" in mrz_data:
            response_data["ai_warning"] = mrz_data.pop("ai_error")

        job.result = response_data
        job.status = OCRJob.STATUS_COMPLETED
        job.progress = 100
        job.save(update_fields=["status", "progress", "result", "updated_at"])
        logger.info(f"OCR job {job_id} completed successfully")

    except AIConnectionError as exc:
        if task and task.retries > 0:
            logger.warning(
                f"OCR job {job_id} encountered AI connection error. Retrying in 10s... ({task.retries} left)"
            )
            job.error_message = f"AI connection error, retrying... ({task.retries} left)"
            job.save(update_fields=["error_message", "updated_at"])
            raise exc  # Re-raise to trigger Huey retry

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
