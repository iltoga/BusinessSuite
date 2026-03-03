from contextlib import contextmanager
from unittest.mock import patch

from django.test import TestCase

from core.models import DocumentOCRJob
from core.tasks.document_ocr import run_document_ocr_job
from products.models.document_type import DocumentType


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

    @patch("core.tasks.document_ocr.acquire_task_lock", return_value="token-2")
    @patch("core.tasks.document_ocr.release_task_lock")
    @patch("core.tasks.document_ocr.get_local_file_path")
    @patch("core.tasks.document_ocr.os.path.exists", return_value=True)
    @patch("core.tasks.document_ocr.DocumentParser.extract_text_from_file")
    @patch("core.tasks.document_ocr.extract_document_structured_output")
    @patch("core.tasks.document_ocr.open")
    def test_document_ocr_uses_structured_output_when_document_type_configured(
        self,
        open_mock,
        structured_output_mock,
        extract_text_mock,
        _exists_mock,
        get_local_path_mock,
        release_lock_mock,
        _acquire_lock_mock,
    ):
        doc_type = DocumentType.objects.create(
            name="ITK OCR",
            ai_structured_output=(
                '[{"field_name":"permit_number","description":"Main ITK permit code"},'
                '{"field_name":"holder_name","description":"Person full name"}]'
            ),
        )
        job = DocumentOCRJob.objects.create(
            status=DocumentOCRJob.STATUS_QUEUED,
            progress=0,
            file_path="tmp/document-ocr.pdf",
            file_url="/uploads/tmp/document-ocr.pdf",
            request_params={"doc_type_id": doc_type.id},
        )

        get_local_path_mock.side_effect = lambda _path: _fake_local_path("/tmp/fake.pdf")
        open_mock.return_value.__enter__.return_value.read.return_value = b"fake-pdf-bytes"
        structured_output_mock.return_value = {"permit_number": "ITK-001", "holder_name": "John Doe"}

        _run_huey_task(run_document_ocr_job, job_id=str(job.id))

        job.refresh_from_db()
        self.assertEqual(job.status, DocumentOCRJob.STATUS_COMPLETED)
        self.assertEqual(job.progress, 100)
        self.assertIn('"permit_number": "ITK-001"', job.result_text)
        self.assertIn('"holder_name": "John Doe"', job.result_text)
        extract_text_mock.assert_not_called()
        structured_output_mock.assert_called_once()
        release_lock_mock.assert_called_once()
