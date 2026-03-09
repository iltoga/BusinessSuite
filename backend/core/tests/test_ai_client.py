import json
import httpx
from unittest.mock import MagicMock, patch

import core.services.ai_client as ai_client_module
from django.test import TestCase, override_settings
from django.core.cache import cache

from core.services.ai_client import AIClient, AIConnectionError
from core.services.app_setting_service import AppSettingService
from core.services.ai_usage_service import AIUsageFeature

OPENAI_PATCH_TARGET = "core.services.ai_client.OpenAI"
GROQ_PATCH_TARGET = "core.services.ai_client.Groq"
ENQUEUE_PATCH_TARGET = "core.services.ai_client.AIUsageService.enqueue_request_capture"


def _build_mock_response(content: str, usage: dict | None = None):
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    response.id = "gen-test-1"
    response.usage = usage
    return response


def _build_rate_limit_error(module):
    request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
    response = httpx.Response(status_code=429, request=request)
    return module.RateLimitError("rate limited", response=response, body={"error": "rate_limit"})


def _build_groq_json_validate_failed_error(module):
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(status_code=400, request=request)
    return module.BadRequestError(
        "json schema validation failed",
        response=response,
        body={"error": {"code": "json_validate_failed", "type": "invalid_request_error"}},
    )


def _build_groq_invalid_response_format_schema_error(module):
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(status_code=400, request=request)
    return module.BadRequestError(
        "invalid JSON schema for response_format",
        response=response,
        body={
            "error": {
                "message": (
                    "invalid JSON schema for response_format: 'document_validation': "
                    "/properties/reasoning: `additionalProperties:false` must be set on every object"
                ),
                "type": "invalid_request_error",
                "param": "response_format",
                "schema_kind": "additional_properties",
            }
        },
    )


class AIClientJsonParsingTests(TestCase):
    def setUp(self):
        AppSettingService.invalidate_cache()
        cache.clear()




    @override_settings(
        OPENROUTER_API_KEY="openrouter-test-key",
        OPENAI_API_KEY="openai-test-key",
        GROQ_API_KEY="groq-test-key",
        LLM_PROVIDER="groq",
    )
    @patch(OPENAI_PATCH_TARGET)
    @patch(GROQ_PATCH_TARGET)
    def test_model_override_infers_provider_when_provider_not_explicit(self, mock_groq, mock_openai):
        openrouter_client = MagicMock()
        mock_openai.return_value = openrouter_client

        client = AIClient(model="openai/gpt-5")

        self.assertEqual(client.provider_key, "openrouter")
        self.assertTrue(client.use_openrouter)
        mock_openai.assert_called_once()
        mock_groq.assert_not_called()

    @override_settings(
        GROQ_API_KEY="groq-test-key",
        OPENROUTER_API_KEY="openrouter-test-key",
        LLM_PROVIDER="openrouter",
        GROQ_DEFAULT_MODEL="meta-llama/llama-4-scout-17b-16e-instruct",
    )
    @patch(OPENAI_PATCH_TARGET)
    @patch(GROQ_PATCH_TARGET)
    def test_explicit_provider_still_wins_over_model_based_inference(self, mock_groq, mock_openai):
        if ai_client_module.groq is None:
            self.skipTest("groq SDK not installed in test environment")

        groq_client = MagicMock()
        mock_groq.return_value = groq_client

        client = AIClient(provider="groq", model="openai/gpt-5")

        self.assertEqual(client.provider_key, "groq")
        mock_groq.assert_called_once()
        mock_openai.assert_not_called()

    @override_settings(
        OPENROUTER_API_KEY="openrouter-test-key",
        LLM_PROVIDER="openrouter",
        LLM_DEFAULT_MODEL="qwen/qwen3.5-flash-02-23",
        OPENROUTER_DEFAULT_MODEL="google/gemini-3-flash-preview",
        LLM_AUTO_FALLBACK_ENABLED=True,
        LLM_FALLBACK_PROVIDER_ORDER=["openrouter"],
        LLM_FALLBACK_STICKY_CACHE_KEY="tests:ai_client:sticky:provider_model_preserved",
    )
    @patch(OPENAI_PATCH_TARGET)
    @patch(ENQUEUE_PATCH_TARGET)
    def test_provider_failover_can_retry_same_provider_with_provider_default_failover_model(
        self,
        mock_enqueue,
        mock_openai,
    ):
        cache.delete("tests:ai_client:sticky:provider_model_preserved")

        openrouter_client = MagicMock()
        openrouter_client.chat.completions.create.side_effect = [
            _build_rate_limit_error(ai_client_module.openai),
            _build_mock_response("ok"),
        ]
        mock_openai.return_value = openrouter_client

        client = AIClient(model="google/gemini-2.5-flash-lite")
        result = client.chat_completion(messages=[{"role": "user", "content": "test"}])

        self.assertEqual(result, "ok")
        self.assertEqual(client.provider_key, "openrouter")
        self.assertEqual(client.model, "google/gemini-3-flash-preview")

        first_model = openrouter_client.chat.completions.create.call_args_list[0].kwargs["model"]
        second_model = openrouter_client.chat.completions.create.call_args_list[1].kwargs["model"]
        self.assertEqual(first_model, "google/gemini-2.5-flash-lite")
        self.assertEqual(second_model, "google/gemini-3-flash-preview")

        providers = [call.kwargs["provider"] for call in mock_enqueue.call_args_list]
        self.assertEqual(providers, ["openrouter", "openrouter"])



    @override_settings(
        GROQ_API_KEY="",
        LLM_PROVIDER="groq",
    )
    def test_groq_provider_requires_api_key(self):
        with self.assertRaises(ValueError) as context:
            AIClient(provider="groq")
        self.assertIn("Groq API key not configured", str(context.exception))



    @override_settings(
        GROQ_API_KEY="groq-test-key",
        OPENROUTER_API_KEY="openrouter-test-key",
        LLM_PROVIDER="groq",
        LLM_AUTO_FALLBACK_ENABLED=True,
        LLM_FALLBACK_PROVIDER_ORDER=["openrouter"],
        LLM_FALLBACK_STICKY_CACHE_KEY="tests:ai_client:sticky:explicit",
    )
    @patch(OPENAI_PATCH_TARGET)
    @patch(GROQ_PATCH_TARGET)
    def test_explicit_provider_override_ignores_sticky_provider(self, mock_groq, mock_openai):
        sticky_key = "tests:ai_client:sticky:explicit"
        cache.set(sticky_key, "openrouter", timeout=3600)

        groq_client = MagicMock()
        groq_client.chat.completions.create.return_value = _build_mock_response("groq-ok")
        mock_groq.return_value = groq_client

        client = AIClient(provider="groq")
        result = client.chat_completion(messages=[{"role": "user", "content": "test"}])

        self.assertEqual(client.provider_key, "groq")
        self.assertEqual(result, "groq-ok")
        mock_groq.assert_called_once()
        mock_openai.assert_not_called()

