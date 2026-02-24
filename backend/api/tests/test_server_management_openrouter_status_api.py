from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.utils import ProgrammingError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.models.ai_request_usage import AIRequestUsage
from core.services.ai_usage_service import AIUsageFeature


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "server-management-openrouter-status-tests",
        },
        "select2": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "server-management-openrouter-status-tests-select2",
        },
    }
)
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
        CHECK_PASSPORT_MODEL="google/gemini-3-flash-preview",
    )
    def test_openrouter_status_returns_credit_and_ai_model_data(self):
        now = timezone.now()

        invoice_usage = AIRequestUsage.objects.create(
            feature=AIUsageFeature.INVOICE_IMPORT_AI_PARSER,
            provider="openrouter",
            model="google/gemini-2.5-flash-lite",
            success=True,
            total_tokens=240,
            cost_usd="0.120000",
        )
        AIRequestUsage.objects.filter(pk=invoice_usage.pk).update(created_at=now)

        passport_usage = AIRequestUsage.objects.create(
            feature=AIUsageFeature.PASSPORT_OCR_AI_EXTRACTOR,
            provider="openrouter",
            model="google/gemini-2.5-flash-lite",
            success=False,
            total_tokens=120,
            cost_usd="0.040000",
        )
        AIRequestUsage.objects.filter(pk=passport_usage.pk).update(created_at=now)

        passport_check_usage = AIRequestUsage.objects.create(
            feature=AIUsageFeature.PASSPORT_CHECK_API,
            provider="openrouter",
            model="google/gemini-3-flash-preview",
            success=True,
            total_tokens=90,
            cost_usd="0.030000",
        )
        AIRequestUsage.objects.filter(pk=passport_check_usage.pk).update(created_at=now)

        document_usage_main = AIRequestUsage.objects.create(
            feature=AIUsageFeature.DOCUMENT_AI_CATEGORIZER,
            provider="openrouter",
            model="google/gemini-2.5-flash-lite",
            success=True,
            total_tokens=1000,
            cost_usd="0.005000",
        )
        AIRequestUsage.objects.filter(pk=document_usage_main.pk).update(created_at=now)

        document_usage_alt = AIRequestUsage.objects.create(
            feature=AIUsageFeature.DOCUMENT_AI_CATEGORIZER,
            provider="openrouter",
            model="google/gemini-3-flash-preview",
            success=True,
            total_tokens=2000,
            cost_usd="0.020000",
        )
        AIRequestUsage.objects.filter(pk=document_usage_alt.pk).update(created_at=now)

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
        self.assertEqual(payload["aiModels"]["usageCurrentMonth"]["requestCount"], 5)
        self.assertEqual(payload["aiModels"]["usageCurrentMonth"]["totalTokens"], 3450)
        self.assertAlmostEqual(payload["aiModels"]["usageCurrentMonth"]["totalCost"], 0.215)
        self.assertGreaterEqual(len(payload["aiModels"]["features"]), 3)
        invoice_feature = next(
            feature for feature in payload["aiModels"]["features"] if feature["feature"] == AIUsageFeature.INVOICE_IMPORT_AI_PARSER
        )
        self.assertEqual(invoice_feature["usageCurrentMonth"]["requestCount"], 1)
        self.assertEqual(invoice_feature["usageCurrentMonth"]["totalTokens"], 240)
        self.assertEqual(invoice_feature["usageCurrentYear"]["requestCount"], 1)

        passport_feature = next(
            feature for feature in payload["aiModels"]["features"] if feature["feature"] == AIUsageFeature.PASSPORT_OCR_AI_EXTRACTOR
        )
        self.assertEqual(passport_feature["usageCurrentMonth"]["failedCount"], 1)

        passport_check_feature = next(
            feature for feature in payload["aiModels"]["features"] if feature["feature"] == AIUsageFeature.PASSPORT_CHECK_API
        )
        self.assertEqual(passport_check_feature["effectiveModel"], "google/gemini-3-flash-preview")
        self.assertEqual(passport_check_feature["usageCurrentMonth"]["requestCount"], 1)
        self.assertEqual(passport_check_feature["usageCurrentMonth"]["totalTokens"], 90)

        document_feature = next(
            feature for feature in payload["aiModels"]["features"] if feature["feature"] == AIUsageFeature.DOCUMENT_AI_CATEGORIZER
        )
        self.assertEqual(document_feature["usageCurrentMonth"]["requestCount"], 2)
        self.assertEqual(document_feature["usageCurrentMonth"]["totalTokens"], 3000)
        self.assertAlmostEqual(document_feature["usageCurrentMonth"]["totalCost"], 0.025)
        self.assertEqual(len(document_feature["modelBreakdownCurrentMonth"]), 2)
        self.assertEqual(document_feature["modelBreakdownCurrentMonth"][0]["model"], "google/gemini-3-flash-preview")
        self.assertAlmostEqual(document_feature["modelBreakdownCurrentMonth"][0]["totalCost"], 0.02)
        self.assertEqual(document_feature["modelBreakdownCurrentMonth"][1]["model"], "google/gemini-2.5-flash-lite")
        self.assertAlmostEqual(document_feature["modelBreakdownCurrentMonth"][1]["totalCost"], 0.005)

    @override_settings(OPENROUTER_API_KEY="")
    def test_openrouter_status_handles_missing_usage_table(self):
        with patch("api.views_admin.AIRequestUsage.objects.filter", side_effect=ProgrammingError("missing table")):
            response = self.client.get("/api/server-management/openrouter-status/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["openrouter"]["configured"])
        self.assertEqual(payload["aiModels"]["usageCurrentMonth"]["requestCount"], 0)
        self.assertEqual(payload["aiModels"]["usageCurrentMonth"]["totalCost"], 0.0)
        self.assertEqual(payload["aiModels"]["usageCurrentYear"]["requestCount"], 0)

        invoice_feature = next(
            feature
            for feature in payload["aiModels"]["features"]
            if feature["feature"] == AIUsageFeature.INVOICE_IMPORT_AI_PARSER
        )
        self.assertEqual(invoice_feature["usageCurrentMonth"]["requestCount"], 0)
        self.assertEqual(invoice_feature["usageCurrentMonth"]["totalCost"], 0.0)
        self.assertEqual(invoice_feature["usageCurrentYear"]["requestCount"], 0)

    @override_settings(
        OPENROUTER_API_KEY="",
        LLM_PROVIDER="openrouter",
        LLM_DEFAULT_MODEL="google/gemini-2.5-flash-lite",
        CHECK_PASSPORT_MODEL="google/gemini-2.5-flash-lite",
    )
    def test_openrouter_status_omits_passport_check_feature_when_model_matches_default(self):
        response = self.client.get("/api/server-management/openrouter-status/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        feature_names = [feature["feature"] for feature in payload["aiModels"]["features"]]
        self.assertNotIn(AIUsageFeature.PASSPORT_CHECK_API, feature_names)
