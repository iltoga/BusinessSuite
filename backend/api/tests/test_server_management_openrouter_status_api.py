from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.utils import ProgrammingError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import AppSetting
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
        OPENAI_API_KEY="openai-test-key",
        OPENROUTER_API_BASE_URL="https://openrouter.ai/api/v1",
        LLM_PROVIDER="openrouter",
        LLM_DEFAULT_MODEL="google/gemini-2.5-flash-lite",
        OPENAI_DEFAULT_MODEL="gpt-5-mini",
        LLM_AUTO_FALLBACK_ENABLED=True,
        LLM_FALLBACK_PROVIDER_ORDER=["openai", "groq"],
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
        self.assertTrue(payload["aiModels"]["failover"]["enabled"])
        self.assertEqual(payload["aiModels"]["failover"]["configuredProviderOrder"], ["openai", "groq"])
        self.assertEqual(payload["aiModels"]["failover"]["effectiveProviderOrder"], ["openai"])
        self.assertEqual(payload["aiModels"]["usageCurrentMonth"]["requestCount"], 5)
        self.assertEqual(payload["aiModels"]["usageCurrentMonth"]["totalTokens"], 3450)
        self.assertAlmostEqual(payload["aiModels"]["usageCurrentMonth"]["totalCost"], 0.215)
        self.assertGreaterEqual(len(payload["aiModels"]["features"]), 6)
        invoice_feature = next(
            feature for feature in payload["aiModels"]["features"] if feature["feature"] == AIUsageFeature.INVOICE_IMPORT_AI_PARSER
        )
        self.assertEqual(invoice_feature["modelSettingName"], "INVOICE_IMPORT_MODEL")
        self.assertEqual(invoice_feature["primaryProvider"], "openrouter")
        self.assertEqual(invoice_feature["primaryModel"], "google/gemini-2.5-flash-lite")
        self.assertEqual(len(invoice_feature["failoverProviders"]), 2)
        self.assertEqual(invoice_feature["failoverProviders"][0]["provider"], "openai")
        self.assertEqual(invoice_feature["failoverProviders"][0]["model"], "gpt-5-mini")
        self.assertTrue(invoice_feature["failoverProviders"][0]["active"])
        self.assertEqual(invoice_feature["failoverProviders"][1]["provider"], "groq")
        self.assertFalse(invoice_feature["failoverProviders"][1]["active"])
        self.assertEqual(invoice_feature["usageCurrentMonth"]["requestCount"], 1)
        self.assertEqual(invoice_feature["usageCurrentMonth"]["totalTokens"], 240)
        self.assertEqual(invoice_feature["usageCurrentYear"]["requestCount"], 1)

        passport_feature = next(
            feature for feature in payload["aiModels"]["features"] if feature["feature"] == AIUsageFeature.PASSPORT_OCR_AI_EXTRACTOR
        )
        self.assertEqual(passport_feature["modelSettingName"], "PASSPORT_OCR_MODEL")
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
        self.assertFalse(document_feature["modelFailover"]["enabled"])
        self.assertEqual(document_feature["usageCurrentMonth"]["requestCount"], 2)
        self.assertEqual(document_feature["usageCurrentMonth"]["totalTokens"], 3000)
        self.assertAlmostEqual(document_feature["usageCurrentMonth"]["totalCost"], 0.025)
        self.assertEqual(len(document_feature["modelBreakdownCurrentMonth"]), 2)
        self.assertEqual(document_feature["modelBreakdownCurrentMonth"][0]["model"], "google/gemini-3-flash-preview")
        self.assertAlmostEqual(document_feature["modelBreakdownCurrentMonth"][0]["totalCost"], 0.02)
        self.assertEqual(document_feature["modelBreakdownCurrentMonth"][1]["model"], "google/gemini-2.5-flash-lite")
        self.assertAlmostEqual(document_feature["modelBreakdownCurrentMonth"][1]["totalCost"], 0.005)
        self.assertIn("runtimeSettings", payload["aiModels"])
        self.assertIn("settingsMap", payload["aiModels"])
        self.assertIn("workflowBindings", payload["aiModels"])
        self.assertIn("modelCatalog", payload["aiModels"])
        self.assertIn("providers", payload["aiModels"]["modelCatalog"])

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
    def test_openrouter_status_includes_passport_check_feature_when_model_matches_default(self):
        response = self.client.get("/api/server-management/openrouter-status/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        feature_names = [feature["feature"] for feature in payload["aiModels"]["features"]]
        self.assertIn(AIUsageFeature.PASSPORT_CHECK_API, feature_names)

    @override_settings(
        OPENROUTER_API_KEY="test-key",
        OPENAI_API_KEY="openai-test-key",
        LLM_PROVIDER="openrouter",
        LLM_DEFAULT_MODEL="google/gemini-3-flash-preview",
        OPENROUTER_DEFAULT_MODEL="openai/gpt-4.1-mini",
        LLM_AUTO_FALLBACK_ENABLED=True,
        LLM_FALLBACK_PROVIDER_ORDER=["openrouter", "openai"],
    )
    def test_openrouter_status_allows_openrouter_in_failover_order_when_primary_is_openrouter(self):
        response = self.client.get("/api/server-management/openrouter-status/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["aiModels"]["failover"]["configuredProviderOrder"],
            ["openrouter", "openai"],
        )
        self.assertEqual(
            payload["aiModels"]["failover"]["effectiveProviderOrder"],
            ["openrouter", "openai"],
        )

        invoice_feature = next(
            feature
            for feature in payload["aiModels"]["features"]
            if feature["feature"] == AIUsageFeature.INVOICE_IMPORT_AI_PARSER
        )
        self.assertEqual(invoice_feature["failoverProviders"][0]["provider"], "openrouter")
        self.assertEqual(invoice_feature["failoverProviders"][0]["model"], "openai/gpt-4.1-mini")
        self.assertTrue(invoice_feature["failoverProviders"][0]["active"])

    @override_settings(
        OPENROUTER_API_KEY="",
        LLM_PROVIDER="openrouter",
        LLM_DEFAULT_MODEL="openai/gpt-5-mini",
        OPENROUTER_DEFAULT_MODEL="google/gemini-3-flash-preview",
    )
    def test_openrouter_status_workflow_models_inherit_primary_when_unset(self):
        response = self.client.get("/api/server-management/openrouter-status/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        invoice_feature = next(
            feature for feature in payload["aiModels"]["features"] if feature["feature"] == AIUsageFeature.INVOICE_IMPORT_AI_PARSER
        )
        passport_feature = next(
            feature for feature in payload["aiModels"]["features"] if feature["feature"] == AIUsageFeature.PASSPORT_OCR_AI_EXTRACTOR
        )

        self.assertEqual(invoice_feature["modelSettingName"], "INVOICE_IMPORT_MODEL")
        self.assertEqual(passport_feature["modelSettingName"], "PASSPORT_OCR_MODEL")
        self.assertEqual(invoice_feature["primaryModel"], "openai/gpt-5-mini")
        self.assertEqual(passport_feature["primaryModel"], "openai/gpt-5-mini")

    @override_settings(
        OPENROUTER_API_KEY="",
        LLM_PROVIDER="groq",
        GROQ_DEFAULT_MODEL="meta-llama/llama-4-scout-17b-16e-instruct",
        CHECK_PASSPORT_MODEL="openai/gpt-5-mini",
    )
    def test_openrouter_status_feature_provider_follows_model_provider(self):
        response = self.client.get("/api/server-management/openrouter-status/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        passport_check_feature = next(
            feature for feature in payload["aiModels"]["features"] if feature["feature"] == AIUsageFeature.PASSPORT_CHECK_API
        )
        self.assertEqual(passport_check_feature["provider"], "openrouter")
        self.assertEqual(passport_check_feature["primaryProvider"], "openrouter")
        self.assertEqual(passport_check_feature["primaryModel"], "openai/gpt-5-mini")

    @override_settings(
        OPENROUTER_API_KEY="",
        LLM_PROVIDER="openrouter",
        LLM_DEFAULT_MODEL="google/gemini-3-flash-preview",
    )
    def test_openrouter_status_patch_updates_runtime_settings_in_db(self):
        response = self.client.patch(
            "/api/server-management/openrouter-status/",
            data={
                "settings": {
                    "LLM_PROVIDER": "openai",
                    "LLM_DEFAULT_MODEL": "gpt-5-mini",
                    "LLM_FALLBACK_PROVIDER_ORDER": ["openrouter"],
                    "LLM_FALLBACK_MODEL_ORDER": ["google/gemini-3-flash-preview"],
                }
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["aiModels"]["provider"], "openai")
        self.assertEqual(payload["aiModels"]["settingsMap"]["LLM_PROVIDER"], "openai")
        self.assertEqual(payload["aiModels"]["settingsMap"]["LLM_DEFAULT_MODEL"], "gpt-5-mini")
        self.assertEqual(payload["aiModels"]["settingsMap"]["LLM_FALLBACK_PROVIDER_ORDER"], ["openrouter"])
        self.assertEqual(
            payload["aiModels"]["settingsMap"]["LLM_FALLBACK_MODEL_ORDER"],
            ["google/gemini-3-flash-preview"],
        )

        provider_setting = AppSetting.objects.get(name="LLM_PROVIDER")
        self.assertEqual(provider_setting.value, "openai")
        self.assertEqual(provider_setting.updated_by_id, self.user.id)

    @override_settings(
        OPENROUTER_API_KEY="",
        LLM_PROVIDER="openrouter",
        LLM_DEFAULT_MODEL="google/gemini-3-flash-preview",
    )
    def test_openrouter_status_patch_updates_invoice_workflow_model_setting(self):
        response = self.client.patch(
            "/api/server-management/openrouter-status/",
            data={
                "settings": {
                    "INVOICE_IMPORT_MODEL": "gpt-5-mini",
                }
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["aiModels"]["settingsMap"]["INVOICE_IMPORT_MODEL"], "gpt-5-mini")

        invoice_feature = next(
            feature for feature in payload["aiModels"]["features"] if feature["feature"] == AIUsageFeature.INVOICE_IMPORT_AI_PARSER
        )
        self.assertEqual(invoice_feature["primaryProvider"], "openai")
        self.assertEqual(invoice_feature["primaryModel"], "gpt-5-mini")

    @override_settings(
        OPENROUTER_API_KEY="",
        LLM_PROVIDER="openrouter",
        LLM_DEFAULT_MODEL="qwen/qwen3.5-flash",
        OPENROUTER_DEFAULT_MODEL="google/gemini-2.5-flash-lite",
    )
    def test_openrouter_status_patch_reset_workflow_model_deletes_db_override(self):
        self.client.patch(
            "/api/server-management/openrouter-status/",
            data={"settings": {"INVOICE_IMPORT_MODEL": "gpt-5-mini"}},
            format="json",
        )
        self.assertTrue(AppSetting.objects.filter(name="INVOICE_IMPORT_MODEL").exists())

        response = self.client.patch(
            "/api/server-management/openrouter-status/",
            data={"settings": {"INVOICE_IMPORT_MODEL": None}},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(AppSetting.objects.filter(name="INVOICE_IMPORT_MODEL").exists())
        self.assertEqual(payload["aiModels"]["settingsMap"]["INVOICE_IMPORT_MODEL"], "")

        invoice_feature = next(
            feature for feature in payload["aiModels"]["features"] if feature["feature"] == AIUsageFeature.INVOICE_IMPORT_AI_PARSER
        )
        self.assertEqual(invoice_feature["primaryProvider"], "openrouter")
        self.assertEqual(invoice_feature["primaryModel"], "qwen/qwen3.5-flash")

    @override_settings(
        OPENROUTER_API_KEY="",
        LLM_PROVIDER="openrouter",
        LLM_DEFAULT_MODEL="google/gemini-3-flash-preview",
    )
    def test_openrouter_status_patch_accepts_snake_case_setting_names(self):
        response = self.client.patch(
            "/api/server-management/openrouter-status/",
            data={
                "settings": {
                    "llm_provider": "openai",
                    "llm_default_model": "gpt-5-mini",
                }
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["aiModels"]["settingsMap"]["LLM_PROVIDER"], "openai")
        self.assertEqual(payload["aiModels"]["settingsMap"]["LLM_DEFAULT_MODEL"], "gpt-5-mini")

        provider_setting = AppSetting.objects.get(name="LLM_PROVIDER")
        self.assertEqual(provider_setting.value, "openai")
        self.assertEqual(provider_setting.updated_by_id, self.user.id)

    @override_settings(OPENROUTER_API_KEY="")
    def test_openrouter_status_patch_rejects_invalid_provider(self):
        response = self.client.patch(
            "/api/server-management/openrouter-status/",
            data={"settings": {"LLM_PROVIDER": "invalid-provider"}},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("LLM_PROVIDER must be one of", response.json().get("detail", ""))

    @override_settings(
        OPENROUTER_API_KEY="",
        LLM_PROVIDER="openrouter",
        LLM_DEFAULT_MODEL="openai/gpt-5-mini",
    )
    def test_openrouter_status_patch_allows_provider_switch_with_independent_primary_model(self):
        response = self.client.patch(
            "/api/server-management/openrouter-status/",
            data={"settings": {"LLM_PROVIDER": "openai"}},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["aiModels"]["settingsMap"]["LLM_PROVIDER"], "openai")
        self.assertEqual(payload["aiModels"]["settingsMap"]["LLM_DEFAULT_MODEL"], "openai/gpt-5-mini")

    @override_settings(DJANGO_LOG_LEVEL="WARNING")
    def test_app_settings_list_and_create(self):
        response = self.client.get("/api/server-management/app-settings/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        item = next((row for row in payload["items"] if row["name"] == "DJANGO_LOG_LEVEL"), None)
        if item is None:
            self.fail("Expected DJANGO_LOG_LEVEL item in settings payload")
        self.assertEqual(item["effectiveValue"], "WARNING")

        create_response = self.client.post(
            "/api/server-management/app-settings/",
            data={
                "name": "DJANGO_LOG_LEVEL",
                "value": "ERROR",
                "scope": "backend",
                "description": "override",
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 200)
        setting = AppSetting.objects.get(name="DJANGO_LOG_LEVEL")
        self.assertEqual(setting.value, "ERROR")
        self.assertEqual(setting.updated_by_id, self.user.id)

    @override_settings(DJANGO_LOG_LEVEL="WARNING")
    def test_app_settings_delete_falls_back_to_previous_precedence(self):
        AppSetting.objects.update_or_create(
            name="DJANGO_LOG_LEVEL",
            defaults={
                "value": "ERROR",
                "scope": AppSetting.SCOPE_BACKEND,
                "description": "override",
                "updated_by": self.user,
            },
        )

        response = self.client.delete("/api/server-management/app-settings/DJANGO_LOG_LEVEL/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(AppSetting.objects.filter(name="DJANGO_LOG_LEVEL").exists())
        self.assertEqual(response.json().get("effectiveValue"), "WARNING")
