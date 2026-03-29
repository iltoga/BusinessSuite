"""Regression tests for the API health check endpoint."""

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

TEST_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "health-check-default-cache",
    }
}


@override_settings(CACHES=TEST_CACHES)
class HealthCheckViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_health_check_reports_healthy_with_test_db_and_cache(self):
        response = self.client.get("/api/health/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "healthy")
        self.assertTrue(payload["checks"]["db"])
        self.assertTrue(payload["checks"]["redis"])
        self.assertIn("elapsed_ms", payload)
