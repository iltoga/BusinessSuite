from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from core.models import AiModel, AppSetting
from core.services.app_setting_service import AppSettingService
from core.services.ai_runtime_settings_service import AIRuntimeSettingsService
from core.services.ai_usage_service import AIUsageFeature


class AIRuntimeSettingsServiceTests(TestCase):
    def setUp(self):
        AppSetting.objects.all().delete()
        AppSettingService.invalidate_cache()


    @override_settings(
        LLM_PROVIDER="openrouter",
        LLM_DEFAULT_MODEL="google/gemini-3-flash-preview",
    )
    def test_updated_db_row_overrides_settings(self):
        user = get_user_model().objects.create_user(username="ai-runtime-updater")
        AppSetting.objects.update_or_create(
            name="LLM_PROVIDER",
            defaults={
                "value": "openrouter",
                "scope": AppSetting.SCOPE_BACKEND,
                "description": "seeded value",
                "updated_by": None,
            },
        )

        AIRuntimeSettingsService.update_runtime_settings(
            {
                "LLM_PROVIDER": "openai",
                "LLM_DEFAULT_MODEL": "gpt-5-mini",
            },
            updated_by=user,
        )

        self.assertEqual(AIRuntimeSettingsService.get_llm_provider(), "openai")
        setting = AppSetting.objects.get(name="LLM_PROVIDER")
        self.assertEqual(setting.updated_by_id, user.id)

    @override_settings(LLM_PROVIDER="openrouter")
    def test_update_runtime_settings_accepts_token_like_user_for_updated_by(self):
        user = get_user_model().objects.create_user(username="token-like-updater")

        class TokenLikeUser:
            def __init__(self, user_id):
                self.id = user_id

        AIRuntimeSettingsService.update_runtime_settings(
            {"INVOICE_IMPORT_MODEL": "gpt-5-mini"},
            updated_by=TokenLikeUser(user.id),
        )

        self.assertEqual(AIRuntimeSettingsService.get("INVOICE_IMPORT_MODEL"), "gpt-5-mini")
        setting = AppSetting.objects.get(name="INVOICE_IMPORT_MODEL")
        self.assertEqual(setting.updated_by_id, user.id)

    @override_settings(
        LLM_PROVIDER="openrouter",
        LLM_DEFAULT_MODEL="openai/gpt-5-mini",
        OPENROUTER_DEFAULT_MODEL="google/gemini-2.5-flash-lite",
    )
    def test_update_runtime_settings_rejects_provider_switch_with_incompatible_primary_model(self):
        with self.assertRaises(ValueError) as raised:
            AIRuntimeSettingsService.update_runtime_settings({"LLM_PROVIDER": "openai"})

        self.assertIn("LLM_DEFAULT_MODEL must be a model listed under provider 'openai'", str(raised.exception))

    @override_settings(
        OPENROUTER_TIMEOUT=60.0,
    )
    def test_env_defaults_override_django_settings_when_no_db_override(self):
        import os

        previous = os.environ.get("OPENROUTER_TIMEOUT")
        os.environ["OPENROUTER_TIMEOUT"] = "75.5"
        try:
            self.assertEqual(AIRuntimeSettingsService.get_openrouter_timeout(), 75.5)
        finally:
            if previous is None:
                os.environ.pop("OPENROUTER_TIMEOUT", None)
            else:
                os.environ["OPENROUTER_TIMEOUT"] = previous

    def test_get_provider_for_model_returns_expected_provider(self):
        self.assertEqual(
            AIRuntimeSettingsService.get_provider_for_model("meta-llama/llama-4-scout-17b-16e-instruct"),
            "groq",
        )
        self.assertEqual(AIRuntimeSettingsService.get_provider_for_model("gpt-5"), "openai")
        self.assertEqual(
            AIRuntimeSettingsService.get_provider_for_model(
                "missing-model",
                fallback="openrouter",
            ),
            "openrouter",
        )

    def test_update_runtime_settings_validates_fallback_model_order(self):
        AIRuntimeSettingsService.update_runtime_settings(
            {"LLM_FALLBACK_MODEL_ORDER": ["google/gemini-3-flash-preview", "gpt-5-mini"]}
        )
        self.assertEqual(
            AIRuntimeSettingsService.get_fallback_model_order(),
            ["google/gemini-3-flash-preview", "gpt-5-mini"],
        )
        self.assertEqual(
            [
                (step.provider, step.model, step.timeout_seconds)
                for step in AIRuntimeSettingsService.get_fallback_model_chain()
            ],
            [
                ("openrouter", "google/gemini-3-flash-preview", 120.0),
                ("openai", "gpt-5-mini", 120.0),
            ],
        )

        with self.assertRaises(ValueError):
            AIRuntimeSettingsService.update_runtime_settings(
                {"LLM_FALLBACK_MODEL_ORDER": ["missing/not-real-model"]}
            )

    def test_update_runtime_settings_persists_fallback_model_chain_with_per_step_timeout(self):
        AIRuntimeSettingsService.update_runtime_settings(
            {
                "LLM_FALLBACK_MODEL_CHAIN": [
                    {"model": "google/gemini-3-flash-preview", "timeoutSeconds": 45},
                    {"model": "gpt-5-mini", "timeoutSeconds": 25},
                ]
            }
        )

        chain = AIRuntimeSettingsService.get_fallback_model_chain()
        self.assertEqual(
            [(step.provider, step.model, step.timeout_seconds) for step in chain],
            [
                ("openrouter", "google/gemini-3-flash-preview", 45.0),
                ("openai", "gpt-5-mini", 25.0),
            ],
        )

        chain_setting = AppSetting.objects.get(name="LLM_FALLBACK_MODEL_CHAIN")
        self.assertTrue(chain_setting.is_runtime_override)
        self.assertEqual(
            AIRuntimeSettingsService.get("LLM_FALLBACK_MODEL_ORDER"),
            ["google/gemini-3-flash-preview", "gpt-5-mini"],
        )

    def test_get_timeout_for_feature_reads_runtime_timeout_settings(self):
        AIRuntimeSettingsService.update_runtime_settings(
            {
                "DOCUMENT_VALIDATION_TIMEOUT": 15,
                "PASSPORT_CHECK_TIMEOUT": 22,
            }
        )

        self.assertEqual(
            AIRuntimeSettingsService.get_timeout_for_feature(AIUsageFeature.DOCUMENT_AI_VALIDATOR),
            15.0,
        )
        self.assertEqual(
            AIRuntimeSettingsService.get_timeout_for_feature(AIUsageFeature.PASSPORT_CHECK_API),
            22.0,
        )

    def test_update_runtime_settings_rejects_non_positive_feature_timeout(self):
        with self.assertRaises(ValueError) as raised:
            AIRuntimeSettingsService.update_runtime_settings({"DOCUMENT_VALIDATION_TIMEOUT": 0})

        self.assertIn("DOCUMENT_VALIDATION_TIMEOUT must be greater than zero.", str(raised.exception))

    @override_settings(
        LLM_PROVIDER="openrouter",
        LLM_DEFAULT_MODEL="qwen/qwen3.5-flash-02-23",
        OPENROUTER_DEFAULT_MODEL="google/gemini-2.5-flash-lite",
    )
    def test_update_runtime_settings_allows_unrelated_updates_with_unlisted_primary_model(self):
        AIRuntimeSettingsService.update_runtime_settings(
            {"LLM_FALLBACK_MODEL_ORDER": ["google/gemini-3-flash-preview"]}
        )
        self.assertEqual(
            AIRuntimeSettingsService.get_fallback_model_order(),
            ["google/gemini-3-flash-preview"],
        )

        AIRuntimeSettingsService.update_runtime_settings({"INVOICE_IMPORT_MODEL": "gpt-5-mini"})
        self.assertEqual(AIRuntimeSettingsService.get_invoice_import_model(), "gpt-5-mini")



