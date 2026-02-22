from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import OCRViewSet
from core.models import OCRJob


class OCRStatusPreviewUrlTests(TestCase):
    def test_completed_status_adds_preview_url_from_storage_path(self):
        user = get_user_model().objects.create_user(username="ocr-user", password="pw")
        job = OCRJob.objects.create(
            status=OCRJob.STATUS_COMPLETED,
            progress=100,
            file_path="tmpfiles/in.png",
            file_url="https://example.com/in.png",
            created_by=user,
            result={
                "mrz_data": {"number": "ABC123"},
                "preview_storage_path": "ocr_previews/job-1.png",
            },
        )

        factory = APIRequestFactory()
        request = factory.get(f"/api/ocr/status/{job.id}/")
        force_authenticate(request, user=user)
        view = OCRViewSet.as_view({"get": "status"})

        with patch("api.views.get_ocr_preview_url", return_value="https://signed.example.com/ocr_previews/job-1.png"):
            response = view(request, job_id=str(job.id))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get("preview_url"), "https://signed.example.com/ocr_previews/job-1.png")
        self.assertEqual(response.data.get("previewUrl"), "https://signed.example.com/ocr_previews/job-1.png")
        self.assertEqual(response.data.get("mrz_data"), {"number": "ABC123"})
