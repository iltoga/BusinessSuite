from unittest.mock import patch

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
    @patch("api.views.enqueue_run_document_ocr_job")
    def test_document_ocr_check_accepts_image_files(self, enqueue_mock, _storage_save_mock, _storage_url_mock):
        image_file = SimpleUploadedFile("document.png", b"png-bytes", content_type="image/png")

        response = self.client.post("/api/document-ocr/check/", {"file": image_file}, format="multipart")

        self.assertEqual(response.status_code, 202)
        self.assertTrue(response.data["queued"])
        self.assertEqual(response.data["status"], "queued")
        enqueue_mock.assert_called_once()
