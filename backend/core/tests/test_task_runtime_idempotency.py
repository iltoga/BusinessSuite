from unittest.mock import patch

from django.test import SimpleTestCase

from core.models import DocumentOCRJob, OCRJob
from core.tasks.document_ocr import run_document_ocr_job
from core.tasks.ocr import run_ocr_job


def _run_huey_task(task, **kwargs):
    if hasattr(task, "call_local"):
        return task.call_local(**kwargs)
    if hasattr(task, "func"):
        return task.func(**kwargs)
    return task(**kwargs)


class CoreTaskRuntimeIdempotencyTests(SimpleTestCase):
    def test_run_ocr_job_skips_when_lock_is_contended(self):
        with (
            patch("core.tasks.ocr.acquire_task_lock", return_value=None),
            patch("core.tasks.ocr.OCRJob.objects.get") as get_job_mock,
        ):
            _run_huey_task(run_ocr_job, job_id="job-123")

        get_job_mock.assert_not_called()

    def test_run_ocr_job_releases_lock_on_early_return(self):
        with (
            patch("core.tasks.ocr.acquire_task_lock", return_value="token-1"),
            patch("core.tasks.ocr.release_task_lock") as release_lock_mock,
            patch("core.tasks.ocr.OCRJob.objects.get", side_effect=OCRJob.DoesNotExist),
        ):
            _run_huey_task(run_ocr_job, job_id="job-123")

        release_lock_mock.assert_called_once_with("tasks:idempotency:ocr_job:job-123", "token-1")

    def test_run_document_ocr_job_skips_when_lock_is_contended(self):
        with (
            patch("core.tasks.document_ocr.acquire_task_lock", return_value=None),
            patch("core.tasks.document_ocr.DocumentOCRJob.objects.get") as get_job_mock,
        ):
            _run_huey_task(run_document_ocr_job, job_id="job-456")

        get_job_mock.assert_not_called()

    def test_run_document_ocr_job_releases_lock_on_early_return(self):
        with (
            patch("core.tasks.document_ocr.acquire_task_lock", return_value="token-2"),
            patch("core.tasks.document_ocr.release_task_lock") as release_lock_mock,
            patch("core.tasks.document_ocr.DocumentOCRJob.objects.get", side_effect=DocumentOCRJob.DoesNotExist),
        ):
            _run_huey_task(run_document_ocr_job, job_id="job-456")

        release_lock_mock.assert_called_once_with("tasks:idempotency:document_ocr_job:job-456", "token-2")
