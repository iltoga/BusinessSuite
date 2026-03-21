from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db.utils import ProgrammingError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import AppSetting
from core.models.ai_request_usage import AIRequestUsage
from core.services.app_setting_service import AppSettingService
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
        AppSetting.objects.all().delete()
        AppSettingService.invalidate_cache()
        cache.clear()
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


    @override_settings(OPENROUTER_API_KEY="")
    def test_openrouter_status_handles_missing_usage_table(self):
        with patch("api.views_admin.AIRequestUsage.objects.filter", side_effect=ProgrammingError("missing table")):
            response = self.client.get("/api/server-management/openrouter-status/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
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
        payload = response.json()["data"]
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
        payload = response.json()["data"]
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
        OPENROUTER_API_KEY="test-key",
        LLM_PROVIDER="openrouter",
        LLM_DEFAULT_MODEL="qwen/qwen3.5-flash-02-23",
        OPENROUTER_DEFAULT_MODEL="google/gemini-3-flash-preview",
        LLM_AUTO_FALLBACK_ENABLED=True,
        LLM_FALLBACK_MODEL_CHAIN=[
            {"model": "google/gemini-3-flash-preview", "timeoutSeconds": 45},
            {"model": "google/gemini-2.5-flash-lite", "timeoutSeconds": 120},
        ],
    )
    def test_openrouter_status_reports_full_failover_model_chain_per_feature(self):
        response = self.client.get("/api/server-management/openrouter-status/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]

        invoice_feature = next(
            feature
            for feature in payload["aiModels"]["features"]
            if feature["feature"] == AIUsageFeature.INVOICE_IMPORT_AI_PARSER
        )

        self.assertEqual(
            invoice_feature["failoverProviders"],
            [
                {
                    "provider": "openrouter",
                    "providerName": "OpenRouter",
                    "model": "google/gemini-3-flash-preview",
                    "timeoutSeconds": 45.0,
                    "available": True,
                    "active": True,
                },
                {
                    "provider": "openrouter",
                    "providerName": "OpenRouter",
                    "model": "google/gemini-2.5-flash-lite",
                    "timeoutSeconds": 120.0,
                    "available": True,
                    "active": True,
                },
            ],
        )


    @override_settings(
        OPENROUTER_API_KEY="",
        LLM_PROVIDER="groq",
        GROQ_DEFAULT_MODEL="meta-llama/llama-4-scout-17b-16e-instruct",
        CHECK_PASSPORT_MODEL="openai/gpt-5-mini",
    )
    def test_openrouter_status_feature_provider_follows_model_provider(self):
        response = self.client.get("/api/server-management/openrouter-status/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
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
                    "LLM_FALLBACK_MODEL_CHAIN": [
                        {"model": "google/gemini-3-flash-preview", "timeoutSeconds": 45}
                    ],
                    "DOCUMENT_VALIDATION_TIMEOUT": 15,
                }
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(payload["aiModels"]["provider"], "openai")
        self.assertEqual(payload["aiModels"]["settingsMap"]["LLM_PROVIDER"], "openai")
        self.assertEqual(payload["aiModels"]["settingsMap"]["LLM_DEFAULT_MODEL"], "gpt-5-mini")
        self.assertEqual(payload["aiModels"]["settingsMap"]["LLM_FALLBACK_PROVIDER_ORDER"], ["openrouter"])
        self.assertEqual(payload["aiModels"]["settingsMap"]["DOCUMENT_VALIDATION_TIMEOUT"], 15.0)
        self.assertEqual(
            payload["aiModels"]["settingsMap"]["LLM_FALLBACK_MODEL_CHAIN"],
            [{"model": "google/gemini-3-flash-preview", "timeoutSeconds": 45.0}],
        )

        provider_setting = AppSetting.objects.get(name="LLM_PROVIDER")
        self.assertEqual(provider_setting.value, "openai")
        self.assertEqual(provider_setting.updated_by_id, self.user.id)

    @override_settings(
        OPENROUTER_API_KEY="",
        LLM_PROVIDER="openrouter",
        LLM_DEFAULT_MODEL="qwen/qwen3.5-flash-02-23",
        OPENROUTER_DEFAULT_MODEL="google/gemini-2.5-flash-lite",
    )
    def test_openrouter_status_patch_updates_fallback_model_order_with_unlisted_primary_model(self):
        response = self.client.patch(
            "/api/server-management/openrouter-status/",
            data={
                "settings": {
                    "LLM_FALLBACK_MODEL_CHAIN": [
                        {"model": "google/gemini-3-flash-preview", "timeoutSeconds": 45}
                    ],
                }
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(
            payload["aiModels"]["settingsMap"]["LLM_FALLBACK_MODEL_CHAIN"],
            [{"model": "google/gemini-3-flash-preview", "timeoutSeconds": 45.0}],
        )
        self.assertEqual(
            payload["aiModels"]["failover"]["configuredModelChain"],
            [
                {
                    "provider": "openrouter",
                    "providerName": "OpenRouter",
                    "model": "google/gemini-3-flash-preview",
                    "timeoutSeconds": 45.0,
                }
            ],
        )

        chain_setting = AppSetting.objects.get(name="LLM_FALLBACK_MODEL_CHAIN")
        setting = AppSetting.objects.get(name="LLM_FALLBACK_MODEL_ORDER")
        self.assertEqual(chain_setting.updated_by_id, self.user.id)
        self.assertEqual(setting.value, "google/gemini-3-flash-preview")
        self.assertEqual(setting.updated_by_id, self.user.id)

    @override_settings(
        OPENROUTER_API_KEY="",
        LLM_PROVIDER="openrouter",
        LLM_DEFAULT_MODEL="qwen/qwen3.5-flash-02-23",
    )
    def test_openrouter_status_patch_updates_workflow_model_with_unlisted_primary_model(self):
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
        payload = response.json()["data"]
        self.assertEqual(payload["aiModels"]["settingsMap"]["INVOICE_IMPORT_MODEL"], "gpt-5-mini")
        invoice_feature = next(
            feature for feature in payload["aiModels"]["features"] if feature["feature"] == AIUsageFeature.INVOICE_IMPORT_AI_PARSER
        )
        self.assertEqual(invoice_feature["primaryProvider"], "openai")
        self.assertEqual(invoice_feature["primaryModel"], "gpt-5-mini")

    @override_settings(
        OPENROUTER_API_KEY="",
        LLM_PROVIDER="openrouter",
        LLM_DEFAULT_MODEL="google/gemini-3-flash-preview",
        GROQ_DEFAULT_MODEL="meta-llama/llama-4-maverick-17b-128e-instruct",
    )
    def test_openrouter_status_patch_updates_active_groq_primary_model(self):
        response = self.client.patch(
            "/api/server-management/openrouter-status/",
            data={
                "settings": {
                    "LLM_PROVIDER": "groq",
                    "GROQ_DEFAULT_MODEL": "qwen/qwen3-32b",
                }
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(payload["aiModels"]["provider"], "groq")
        self.assertEqual(payload["aiModels"]["defaultModel"], "qwen/qwen3-32b")
        self.assertEqual(payload["aiModels"]["settingsMap"]["LLM_PROVIDER"], "groq")
        self.assertEqual(payload["aiModels"]["settingsMap"]["GROQ_DEFAULT_MODEL"], "qwen/qwen3-32b")
        self.assertEqual(payload["aiModels"]["settingsMap"]["LLM_DEFAULT_MODEL"], "google/gemini-3-flash-preview")

        provider_setting = AppSetting.objects.get(name="LLM_PROVIDER")
        groq_setting = AppSetting.objects.get(name="GROQ_DEFAULT_MODEL")
        self.assertEqual(provider_setting.value, "groq")
        self.assertEqual(groq_setting.value, "qwen/qwen3-32b")
        self.assertEqual(provider_setting.updated_by_id, self.user.id)
        self.assertEqual(groq_setting.updated_by_id, self.user.id)

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
        payload = response.json()["data"]
        self.assertEqual(payload["aiModels"]["settingsMap"]["INVOICE_IMPORT_MODEL"], "gpt-5-mini")

        invoice_feature = next(
            feature for feature in payload["aiModels"]["features"] if feature["feature"] == AIUsageFeature.INVOICE_IMPORT_AI_PARSER
        )
        self.assertEqual(invoice_feature["primaryProvider"], "openai")
        self.assertEqual(invoice_feature["primaryModel"], "gpt-5-mini")




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
        payload = response.json()["data"]
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
        self.assertIn("LLM_PROVIDER must be one of", response.json()["error"]["message"])

    @override_settings(
        OPENROUTER_API_KEY="",
        LLM_PROVIDER="openrouter",
        LLM_DEFAULT_MODEL="openai/gpt-5-mini",
    )
    def test_openrouter_status_patch_rejects_provider_switch_with_incompatible_primary_model(self):
        response = self.client.patch(
            "/api/server-management/openrouter-status/",
            data={"settings": {"LLM_PROVIDER": "openai"}},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "LLM_DEFAULT_MODEL must be a model listed under provider 'openai'",
            response.json()["error"]["message"],
        )
