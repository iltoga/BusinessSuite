from unittest.mock import patch

from core.models import DocumentOCRJob
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }
)
class DocumentOcrApiTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user("ocr-api-user", "ocr-api@example.com", "pass")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    @patch("api.views.default_storage.url", return_value="/uploads/tmpfiles/document.png")
    @patch("api.views.default_storage.save", return_value="tmpfiles/document.png")
    @patch("api.views.run_document_ocr_job")
    def test_document_ocr_check_accepts_image_files(self, enqueue_mock, _storage_save_mock, _storage_url_mock):
        image_file = SimpleUploadedFile("document.png", b"png-bytes", content_type="image/png")

        response = self.client.post("/api/document-ocr/check/", {"file": image_file}, format="multipart")

        self.assertEqual(response.status_code, 202)
        self.assertIn("jobId", response.data)
        self.assertNotIn("job_id", response.data)
        self.assertTrue(response.data["queued"])
        self.assertEqual(response.data["status"], "queued")
        self.assertTrue(response.data["streamUrl"].endswith(f"/api/document-ocr/stream/{response.data['jobId']}/"))
        enqueue_mock.assert_called_once()

    def test_document_ocr_status_returns_structured_payload_when_result_text_is_json(self):
        job = DocumentOCRJob.objects.create(
            status=DocumentOCRJob.STATUS_COMPLETED,
            progress=100,
            file_path="tmpfiles/document.png",
            file_url="/uploads/tmpfiles/document.png",
            result_text='{"permit_number":"ITK-77","holder_name":"John Doe"}',
            created_by=self.user,
        )

        response = self.client.get(f"/api/document-ocr/status/{job.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "completed")
        self.assertEqual(response.data["structuredData"]["holderName"], "John Doe")
        self.assertEqual(response.data["structuredData"]["permitNumber"], "ITK-77")
