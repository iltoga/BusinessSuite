from contextlib import contextmanager
from unittest.mock import patch

from django.test import TestCase

from core.models import DocumentOCRJob
from core.tasks.document_ocr import run_document_ocr_job


def _run_huey_task(task, **kwargs):
    if hasattr(task, "call_local"):
        return task.call_local(**kwargs)
    if hasattr(task, "func"):
        return task.func(**kwargs)
    return task(**kwargs)


@contextmanager
def _fake_local_path(path: str):
    yield path


class DocumentOcrTaskTests(TestCase):
    @patch("core.tasks.document_ocr.acquire_task_lock", return_value="token-1")
    @patch("core.tasks.document_ocr.release_task_lock")
    @patch("core.tasks.document_ocr.get_local_file_path")
    @patch("core.tasks.document_ocr.os.path.exists", return_value=True)
    @patch("core.tasks.document_ocr.DocumentParser.extract_text_from_file")
    def test_document_ocr_updates_progress_during_extraction(
        self,
        extract_text_mock,
        _exists_mock,
        get_local_path_mock,
        release_lock_mock,
        _acquire_lock_mock,
    ):
        progress_updates: list[int] = []

        def _fake_extract(file_path: str, progress_callback=None):
            self.assertEqual(file_path, "/tmp/fake.pdf")
            self.assertIsNotNone(progress_callback)
            for value in (45, 58, 73, 90):
                if progress_callback is not None:
                    progress_callback(value)
                progress_updates.append(value)
            return "Extracted OCR text"

        extract_text_mock.side_effect = _fake_extract
        get_local_path_mock.side_effect = lambda _path: _fake_local_path("/tmp/fake.pdf")

        job = DocumentOCRJob.objects.create(
            status=DocumentOCRJob.STATUS_QUEUED,
            progress=0,
            file_path="tmp/document-ocr.pdf",
            file_url="/uploads/tmp/document-ocr.pdf",
        )

        _run_huey_task(run_document_ocr_job, job_id=str(job.id))

        job.refresh_from_db()
        self.assertEqual(job.status, DocumentOCRJob.STATUS_COMPLETED)
        self.assertEqual(job.progress, 100)
        self.assertEqual(job.result_text, "Extracted OCR text")
        self.assertEqual(progress_updates, [45, 58, 73, 90])
        release_lock_mock.assert_called_once()
