import json
import httpx
from unittest.mock import MagicMock, patch

import core.services.ai_client as ai_client_module
from django.test import TestCase, override_settings
from django.core.cache import cache

from core.services.ai_client import AIClient

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
    @override_settings(
        OPENROUTER_API_KEY="test-key",
        LLM_PROVIDER="openrouter",
    )
    @patch(OPENAI_PATCH_TARGET)
    @patch(ENQUEUE_PATCH_TARGET)
    def test_chat_completion_json_repairs_unescaped_quote(self, mock_enqueue, mock_openai):
        malformed_json = """
        {
          "first_name": "Anna "Maria",
          "passport_number": "YA1234567"
        }
        """

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _build_mock_response(malformed_json)
        mock_openai.return_value = mock_client

        client = AIClient()
        result = client.chat_completion_json(
            messages=[{"role": "user", "content": "extract"}],
            json_schema={
                "type": "object",
                "properties": {
                    "first_name": {"type": "string"},
                    "passport_number": {"type": "string"},
                },
                "required": ["first_name", "passport_number"],
                "additionalProperties": False,
            },
            schema_name="passport_data",
        )

        self.assertEqual(result["first_name"], 'Anna "Maria')
        self.assertEqual(result["passport_number"], "YA1234567")
        self.assertEqual(mock_client.chat.completions.create.call_count, 1)
        self.assertEqual(mock_enqueue.call_count, 1)
        self.assertEqual(mock_enqueue.call_args.kwargs["provider"], "openrouter")
        self.assertTrue(mock_enqueue.call_args.kwargs["success"])

    @override_settings(
        OPENROUTER_API_KEY="test-key",
        LLM_PROVIDER="openrouter",
    )
    @patch(OPENAI_PATCH_TARGET)
    @patch(ENQUEUE_PATCH_TARGET)
    def test_chat_completion_json_retries_after_invalid_json(self, mock_enqueue, mock_openai):
        invalid_response = _build_mock_response("this is not valid json")
        valid_response = _build_mock_response(json.dumps({"ok": True}))

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [invalid_response, valid_response]
        mock_openai.return_value = mock_client

        client = AIClient()
        result = client.chat_completion_json(
            messages=[{"role": "user", "content": "extract"}],
            json_schema={
                "type": "object",
                "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"],
                "additionalProperties": False,
            },
            schema_name="result",
        )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(mock_client.chat.completions.create.call_count, 2)
        self.assertEqual(mock_enqueue.call_count, 2)

    @override_settings(
        GROQ_API_KEY="groq-test-key",
        LLM_PROVIDER="groq",
        GROQ_DEFAULT_MODEL="meta-llama/llama-4-scout-17b-16e-instruct",
        LLM_FALLBACK_STICKY_CACHE_KEY="tests:ai_client:sticky:init",
    )
    @patch(GROQ_PATCH_TARGET)
    def test_groq_provider_initialization_uses_groq_client(self, mock_groq):
        cache.delete("tests:ai_client:sticky:init")
        groq_client = MagicMock()
        mock_groq.return_value = groq_client

        client = AIClient()

        self.assertEqual(client.provider_key, "groq")
        self.assertEqual(client.provider_name, "Groq")
        self.assertEqual(client.model, "meta-llama/llama-4-scout-17b-16e-instruct")
        self.assertFalse(client.use_openrouter)
        mock_groq.assert_called_once()

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
        GROQ_DEFAULT_MODEL="meta-llama/llama-4-scout-17b-16e-instruct",
        OPENROUTER_DEFAULT_MODEL="google/gemini-2.5-flash-lite",
        LLM_AUTO_FALLBACK_ENABLED=True,
        LLM_FALLBACK_PROVIDER_ORDER=["openrouter"],
        LLM_FALLBACK_STICKY_CACHE_KEY="tests:ai_client:sticky:fallback",
        LLM_FALLBACK_STICKY_SECONDS=3600,
    )
    @patch(OPENAI_PATCH_TARGET)
    @patch(GROQ_PATCH_TARGET)
    @patch(ENQUEUE_PATCH_TARGET)
    def test_chat_completion_falls_back_from_groq_to_openrouter_and_sets_sticky(
        self,
        mock_enqueue,
        mock_groq,
        mock_openai,
    ):
        if ai_client_module.groq is None:
            self.skipTest("groq SDK not installed in test environment")

        sticky_key = "tests:ai_client:sticky:fallback"
        cache.delete(sticky_key)

        groq_client = MagicMock()
        groq_client.chat.completions.create.side_effect = _build_rate_limit_error(ai_client_module.groq)
        mock_groq.return_value = groq_client

        openrouter_client = MagicMock()
        openrouter_client.chat.completions.create.return_value = _build_mock_response("fallback-ok")
        mock_openai.return_value = openrouter_client

        client = AIClient()
        result = client.chat_completion(messages=[{"role": "user", "content": "test"}])

        self.assertEqual(result, "fallback-ok")
        self.assertEqual(cache.get(sticky_key), "openrouter")
        self.assertEqual(mock_groq.call_count, 1)
        self.assertEqual(mock_openai.call_count, 1)
        providers = [call.kwargs["provider"] for call in mock_enqueue.call_args_list]
        self.assertEqual(providers, ["groq", "openrouter"])

    @override_settings(
        GROQ_API_KEY="groq-test-key",
        OPENROUTER_API_KEY="openrouter-test-key",
        LLM_PROVIDER="groq",
        LLM_AUTO_FALLBACK_ENABLED=True,
        LLM_FALLBACK_PROVIDER_ORDER=["openrouter"],
        LLM_FALLBACK_STICKY_CACHE_KEY="tests:ai_client:sticky:reuse",
    )
    @patch(OPENAI_PATCH_TARGET)
    @patch(GROQ_PATCH_TARGET)
    def test_sticky_provider_is_used_before_configured_provider(self, mock_groq, mock_openai):
        sticky_key = "tests:ai_client:sticky:reuse"
        cache.set(sticky_key, "openrouter", timeout=3600)

        openrouter_client = MagicMock()
        openrouter_client.chat.completions.create.return_value = _build_mock_response("sticky-ok")
        mock_openai.return_value = openrouter_client

        client = AIClient()
        result = client.chat_completion(messages=[{"role": "user", "content": "test"}])

        self.assertEqual(client.provider_key, "openrouter")
        self.assertEqual(result, "sticky-ok")
        mock_groq.assert_not_called()
        mock_openai.assert_called_once()

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

    @override_settings(
        GROQ_API_KEY="groq-test-key",
        OPENROUTER_API_KEY="openrouter-test-key",
        LLM_PROVIDER="groq",
        GROQ_DEFAULT_MODEL="meta-llama/llama-4-scout-17b-16e-instruct",
        OPENROUTER_DEFAULT_MODEL="google/gemini-2.5-flash-lite",
        LLM_AUTO_FALLBACK_ENABLED=True,
        LLM_FALLBACK_PROVIDER_ORDER=["openrouter"],
        LLM_FALLBACK_STICKY_CACHE_KEY="tests:ai_client:sticky:json-validate",
        LLM_FALLBACK_STICKY_SECONDS=3600,
    )
    @patch(OPENAI_PATCH_TARGET)
    @patch(GROQ_PATCH_TARGET)
    @patch(ENQUEUE_PATCH_TARGET)
    def test_chat_completion_falls_back_when_groq_json_schema_validation_fails(
        self,
        mock_enqueue,
        mock_groq,
        mock_openai,
    ):
        if ai_client_module.groq is None:
            self.skipTest("groq SDK not installed in test environment")

        sticky_key = "tests:ai_client:sticky:json-validate"
        cache.delete(sticky_key)

        groq_client = MagicMock()
        groq_client.chat.completions.create.side_effect = _build_groq_json_validate_failed_error(
            ai_client_module.groq
        )
        mock_groq.return_value = groq_client

        openrouter_client = MagicMock()
        openrouter_client.chat.completions.create.return_value = _build_mock_response("fallback-after-json-validate")
        mock_openai.return_value = openrouter_client

        client = AIClient()
        result = client.chat_completion(messages=[{"role": "user", "content": "test"}])

        self.assertEqual(result, "fallback-after-json-validate")
        self.assertEqual(cache.get(sticky_key), "openrouter")
        providers = [call.kwargs["provider"] for call in mock_enqueue.call_args_list]
        self.assertEqual(providers, ["groq", "openrouter"])
        success_states = [call.kwargs["success"] for call in mock_enqueue.call_args_list]
        self.assertEqual(success_states, [False, True])

    @override_settings(
        GROQ_API_KEY="groq-test-key",
        OPENROUTER_API_KEY="openrouter-test-key",
        LLM_PROVIDER="groq",
        GROQ_DEFAULT_MODEL="meta-llama/llama-4-scout-17b-16e-instruct",
        OPENROUTER_DEFAULT_MODEL="google/gemini-2.5-flash-lite",
        LLM_AUTO_FALLBACK_ENABLED=True,
        LLM_FALLBACK_PROVIDER_ORDER=["openrouter"],
        LLM_FALLBACK_STICKY_CACHE_KEY="tests:ai_client:sticky:invalid-response-schema",
        LLM_FALLBACK_STICKY_SECONDS=3600,
    )
    @patch(OPENAI_PATCH_TARGET)
    @patch(GROQ_PATCH_TARGET)
    @patch(ENQUEUE_PATCH_TARGET)
    def test_chat_completion_falls_back_when_groq_response_format_schema_is_invalid(
        self,
        mock_enqueue,
        mock_groq,
        mock_openai,
    ):
        if ai_client_module.groq is None:
            self.skipTest("groq SDK not installed in test environment")

        sticky_key = "tests:ai_client:sticky:invalid-response-schema"
        cache.delete(sticky_key)

        groq_client = MagicMock()
        groq_client.chat.completions.create.side_effect = _build_groq_invalid_response_format_schema_error(
            ai_client_module.groq
        )
        mock_groq.return_value = groq_client

        openrouter_client = MagicMock()
        openrouter_client.chat.completions.create.return_value = _build_mock_response("fallback-after-schema-error")
        mock_openai.return_value = openrouter_client

        client = AIClient()
        result = client.chat_completion(messages=[{"role": "user", "content": "test"}])

        self.assertEqual(result, "fallback-after-schema-error")
        self.assertEqual(cache.get(sticky_key), "openrouter")
        providers = [call.kwargs["provider"] for call in mock_enqueue.call_args_list]
        self.assertEqual(providers, ["groq", "openrouter"])
        success_states = [call.kwargs["success"] for call in mock_enqueue.call_args_list]
        self.assertEqual(success_states, [False, True])
