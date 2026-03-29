"""Regression tests for passport check API endpoints."""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

User = get_user_model()


class PassportCheckApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="passport-user",
            email="passport-user@example.com",
            password="password123",
        )
        self.client.force_authenticate(user=self.user)

    @patch("api.view_auth_catalog.AsyncJob.objects.create")
    @patch("api.view_auth_catalog.default_storage.save", return_value="tmp/passport_checks/passport.jpg")
    @patch("api.view_auth_catalog.check_passport_uploadability_task.delay")
    def test_check_passport_returns_canonical_job_id(self, mock_delay, _mock_save, mock_create):
        uploaded_file = SimpleUploadedFile("passport.jpg", b"fake-image-bytes", content_type="image/jpeg")
        mock_create.return_value = type("Job", (), {"id": "job-123"})()

        response = self.client.post(
            "/api/customers/check-passport/",
            {"file": uploaded_file, "method": "hybrid"},
            format="multipart",
        )

        self.assertEqual(response.status_code, 202, response.content)
        body = response.json()
        self.assertIn("jobId", body)
        self.assertNotIn("job_id", body)
        self.assertTrue(body["jobId"])
        self.assertEqual(body["jobId"], "job-123")
        mock_create.assert_called_once()
        mock_delay.assert_called_once()
        called_job_id, called_path, called_method = mock_delay.call_args.args
        self.assertEqual(called_job_id, "job-123")
        self.assertEqual(called_path, "tmp/passport_checks/passport.jpg")
        self.assertEqual(called_method, "hybrid")

    def test_check_passport_cors_preflight_allows_request_metadata_headers(self):
        response = self.client.options(
            "/api/customers/check-passport/",
            HTTP_ORIGIN="http://localhost:4200",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="x-request-id,idempotency-key,content-type",
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), "http://localhost:4200")
        allowed_headers = {
            header.strip().lower()
            for header in (response.headers.get("Access-Control-Allow-Headers") or "").split(",")
            if header.strip()
        }
        self.assertIn("x-request-id", allowed_headers)
        self.assertIn("idempotency-key", allowed_headers)
