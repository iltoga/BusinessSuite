import logging

from core.models.async_job import AsyncJob
from core.queue import enqueue_job
from core.services.passport_uploadability_service import PassportUploadabilityService
from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)
ENTRYPOINT_CHECK_PASSPORT_UPLOADABILITY_TASK = "customers.check_passport_uploadability"


def check_passport_uploadability_task(job_id: str, file_path: str, method: str):
    """
    Task to check passport uploadability asynchronously.
    """
    try:
        job = AsyncJob.objects.get(id=job_id)
        job.update_progress(10, "Starting passport verification...", status=AsyncJob.STATUS_PROCESSING)

        # Read file from storage
        if not default_storage.exists(file_path):
            job.fail("Passport image file not found in storage.")
            return

        job.update_progress(20, f"Reading image for {method} verification...")

        with default_storage.open(file_path, "rb") as f:
            file_content = f.read()

        service = PassportUploadabilityService()

        def progress_callback(progress: int, message: str):
            job.update_progress(progress, message, status=AsyncJob.STATUS_PROCESSING)

        result = service.check_passport(file_content, method=method, progress_callback=progress_callback)

        job.update_progress(95, "Verification completed, preparing results...")

        # Clean up the temporary file
        try:
            default_storage.delete(file_path)
        except Exception as e:
            logger.warning(f"Failed to delete temporary passport file {file_path}: {e}")

        if result.is_valid:
            job.complete(
                result={
                    "is_valid": True,
                    "method_used": result.method_used,
                    "model_used": result.model_used,
                    "passport_data": result.passport_data,
                },
                message="Passport verified successfully.",
            )
        else:
            job.complete(
                result={
                    "is_valid": False,
                    "method_used": result.method_used,
                    "model_used": result.model_used,
                    "rejection_code": result.rejection_code,
                    "rejection_reason": result.rejection_reason,
                },
                message="Passport verification failed.",
            )

    except AsyncJob.DoesNotExist:
        logger.error(f"AsyncJob {job_id} not found for passport check.")
    except Exception as e:
        logger.exception(f"Error in check_passport_uploadability_task: {e}")
        try:
            job = AsyncJob.objects.get(id=job_id)
            job.fail(str(e))
        except:
            pass


def enqueue_check_passport_uploadability_task(
    *,
    job_id: str,
    file_path: str,
    method: str,
    delay_seconds: int | float | None = None,
) -> str | None:
    return enqueue_job(
        entrypoint=ENTRYPOINT_CHECK_PASSPORT_UPLOADABILITY_TASK,
        payload={"job_id": str(job_id), "file_path": file_path, "method": method},
        delay_seconds=delay_seconds,
        run_local=check_passport_uploadability_task,
    )
