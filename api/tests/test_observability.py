from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient


class ObservabilityProxyTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="loguser", password="secret")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_proxy_accepts_log_and_forwards_to_logger(self):
        payload = {"level": "ERROR", "message": "Test frontend error", "metadata": {"route": "/home"}}

        with patch("logging.Logger.info") as mock_info:
            resp = self.client.post("/api/v1/observability/log/", data=payload, format="json")
            self.assertEqual(resp.status_code, 202)
            self.assertTrue(mock_info.called)
