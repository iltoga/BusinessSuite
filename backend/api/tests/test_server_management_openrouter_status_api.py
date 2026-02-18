from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from rest_framework.test import APIClient


class ServerManagementOpenRouterStatusApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser(
            username="servermgmt-admin",
            email="servermgmt-admin@example.com",
            password="password",
        )
        admin_group, _ = Group.objects.get_or_create(name="admin")
        self.user.groups.add(admin_group)
        self.client.force_authenticate(user=self.user)

    @override_settings(
        OPENROUTER_API_KEY="test-key",
        OPENROUTER_API_BASE_URL="https://openrouter.ai/api/v1",
        LLM_PROVIDER="openrouter",
        LLM_DEFAULT_MODEL="google/gemini-2.5-flash-lite",
    )
    def test_openrouter_status_returns_credit_and_ai_model_data(self):
        key_response = MagicMock()
        key_response.status_code = 200
        key_response.json.return_value = {
            "data": {
                "limit_remaining": 12.5,
                "usage_monthly": 5.0,
                "limit": 20.0,
            }
        }

        credits_response = MagicMock()
        credits_response.status_code = 403
        credits_response.text = "Forbidden"

        with patch("api.views_admin.requests.get", side_effect=[key_response, credits_response]):
            response = self.client.get("/api/server-management/openrouter-status/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["openrouter"]["configured"])
        self.assertTrue(payload["openrouter"]["keyStatus"]["ok"])
        self.assertEqual(payload["openrouter"]["keyStatus"]["limitRemaining"], 12.5)
        self.assertEqual(payload["openrouter"]["effectiveCreditRemaining"], 12.5)
        self.assertEqual(payload["aiModels"]["provider"], "openrouter")
        self.assertGreaterEqual(len(payload["aiModels"]["features"]), 2)
