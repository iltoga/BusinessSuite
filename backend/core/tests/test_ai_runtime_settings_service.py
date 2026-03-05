from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from core.models import AiModel, AppSetting
from core.services.ai_runtime_settings_service import AIRuntimeSettingsService


class AIRuntimeSettingsServiceTests(TestCase):
    @override_settings(LLM_PROVIDER="openrouter")
    def test_seed_like_db_row_does_not_override_settings_until_updated(self):
        AppSetting.objects.update_or_create(
            name="LLM_PROVIDER",
            defaults={
                "value": "openai",
                "scope": AppSetting.SCOPE_BACKEND,
                "description": "seeded value",
                "updated_by": None,
            },
        )

        self.assertEqual(AIRuntimeSettingsService.get_llm_provider(), "openrouter")

    @override_settings(LLM_PROVIDER="openrouter")
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

        AIRuntimeSettingsService.update_runtime_settings({"LLM_PROVIDER": "openai"}, updated_by=user)

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
        OPENROUTER_DEFAULT_MODEL="openai/gpt-5-mini",
    )
    def test_update_runtime_settings_rejects_incompatible_llm_default_for_openai_provider(self):
        with self.assertRaisesMessage(
            ValueError,
            "LLM_DEFAULT_MODEL must be listed under provider 'openai' when LLM_PROVIDER is openai.",
        ):
            AIRuntimeSettingsService.update_runtime_settings({"LLM_PROVIDER": "openai"})

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

    @override_settings(
        LLM_PROVIDER="openrouter",
        LLM_DEFAULT_MODEL="google/gemini-3-flash-preview",
        OPENROUTER_DEFAULT_MODEL="google/gemini-2.5-flash-lite",
        GROQ_DEFAULT_MODEL="meta-llama/llama-4-scout-17b-16e-instruct",
    )
    def test_invoice_import_model_inherits_primary_until_override(self):
        user = get_user_model().objects.create_user(username="invoice-model-updater")

        # No explicit workflow model set: inherit primary runtime model.
        self.assertEqual(AIRuntimeSettingsService.get_invoice_import_model(), "google/gemini-2.5-flash-lite")

        AIRuntimeSettingsService.update_runtime_settings(
            {"INVOICE_IMPORT_MODEL": "gpt-5-mini"},
            updated_by=user,
        )
        self.assertEqual(AIRuntimeSettingsService.get_invoice_import_model(), "gpt-5-mini")
        self.assertTrue(AppSetting.objects.filter(name="INVOICE_IMPORT_MODEL").exists())

        AIRuntimeSettingsService.update_runtime_settings({"LLM_PROVIDER": "groq"}, updated_by=user)
        self.assertEqual(AIRuntimeSettingsService.get_invoice_import_model(), "gpt-5-mini")

        AIRuntimeSettingsService.update_runtime_settings({"INVOICE_IMPORT_MODEL": None}, updated_by=user)
        self.assertFalse(AppSetting.objects.filter(name="INVOICE_IMPORT_MODEL").exists())
        self.assertEqual(
            AIRuntimeSettingsService.get_invoice_import_model(),
            "meta-llama/llama-4-scout-17b-16e-instruct",
        )


    @override_settings(
        LLM_DEFAULT_MODEL="google/gemini-3-flash-preview",
        OPENROUTER_DEFAULT_MODEL="google/gemini-2.5-flash-lite",
    )
    def test_deleted_model_references_are_replaced_with_defaults(self):
        AppSetting.objects.update_or_create(
            name="INVOICE_IMPORT_MODEL",
            defaults={
                "value": "openai/gpt-5",
                "scope": AppSetting.SCOPE_BACKEND,
                "description": "workflow model",
                "updated_by": None,
            },
        )

        model = AiModel.objects.get(provider="openrouter", model_id="openai/gpt-5")
        model.delete()

        self.assertEqual(
            AIRuntimeSettingsService.get("INVOICE_IMPORT_MODEL"),
            "google/gemini-3-flash-preview",
        )
