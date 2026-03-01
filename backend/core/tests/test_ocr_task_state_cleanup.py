from contextlib import contextmanager
from io import BytesIO
from unittest.mock import patch

from core.models import DocumentOCRJob, OCRJob
from core.tasks.document_ocr import run_document_ocr_job
from core.tasks.ocr import run_ocr_job
from django.test import TestCase


def _run_huey_task(task, **kwargs):
    if hasattr(task, "call_local"):
        return task.call_local(**kwargs)
    if hasattr(task, "func"):
        return task.func(**kwargs)
    return task(**kwargs)


@contextmanager
def _fake_local_path(path: str):
    yield path


class OcrTaskStateCleanupTests(TestCase):
    @patch("core.tasks.ocr.acquire_task_lock", return_value="token-ocr-ok")
    @patch("core.tasks.ocr.release_task_lock")
    @patch("core.tasks.ocr.default_storage.open")
    @patch("core.tasks.ocr.extract_mrz_data")
    def test_run_ocr_job_success_clears_stale_error_fields(
        self,
        extract_mrz_data_mock,
        storage_open_mock,
        _release_lock_mock,
        _acquire_lock_mock,
    ):
        job = OCRJob.objects.create(
            status=OCRJob.STATUS_QUEUED,
            file_path="tmp/passport.jpg",
            request_params={"use_ai": False, "img_preview": False, "resize": False},
            error_message="old ocr error",
            traceback="old ocr traceback",
        )

        @contextmanager
        def _fake_open(*args, **kwargs):
            yield BytesIO(b"fake-image-bytes")

        storage_open_mock.side_effect = _fake_open
        extract_mrz_data_mock.return_value = {"passport_no": "A1234567"}

        _run_huey_task(run_ocr_job, job_id=str(job.id))

        job.refresh_from_db()
        self.assertEqual(job.status, OCRJob.STATUS_COMPLETED)
        self.assertEqual(job.progress, 100)
        self.assertEqual(job.error_message, "")
        self.assertEqual(job.traceback, "")
        self.assertEqual(job.result.get("mrz_data", {}).get("passport_no"), "A1234567")

    @patch("core.tasks.document_ocr.acquire_task_lock", return_value="token-doc-ocr-ok")
    @patch("core.tasks.document_ocr.release_task_lock")
    @patch("core.tasks.document_ocr.get_local_file_path")
    @patch("core.tasks.document_ocr.os.path.exists", return_value=True)
    @patch("core.tasks.document_ocr.DocumentParser.extract_text_from_file")
    def test_run_document_ocr_job_success_clears_stale_error_fields(
        self,
        extract_text_mock,
        _exists_mock,
        get_local_path_mock,
        _release_lock_mock,
        _acquire_lock_mock,
    ):
        job = DocumentOCRJob.objects.create(
            status=DocumentOCRJob.STATUS_QUEUED,
            file_path="tmp/document.pdf",
            file_url="/uploads/tmp/document.pdf",
            error_message="old doc ocr error",
            traceback="old doc ocr traceback",
        )

        extract_text_mock.return_value = "Extracted text"
        get_local_path_mock.side_effect = lambda _path: _fake_local_path("/tmp/document.pdf")

        _run_huey_task(run_document_ocr_job, job_id=str(job.id))

        job.refresh_from_db()
        self.assertEqual(job.status, DocumentOCRJob.STATUS_COMPLETED)
        self.assertEqual(job.progress, 100)
        self.assertEqual(job.error_message, "")
        self.assertEqual(job.traceback, "")
        self.assertEqual(job.result_text, "Extracted text")
