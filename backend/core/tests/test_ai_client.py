import json
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from core.services.ai_client import AIClient

OPENAI_PATCH_TARGET = "core.services.ai_client.OpenAI"


def _build_mock_response(content: str):
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    return response


class AIClientJsonParsingTests(TestCase):
    @override_settings(
        OPENROUTER_API_KEY="test-key",
        LLM_PROVIDER="openrouter",
    )
    @patch(OPENAI_PATCH_TARGET)
    def test_chat_completion_json_repairs_unescaped_quote(self, mock_openai):
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

    @override_settings(
        OPENROUTER_API_KEY="test-key",
        LLM_PROVIDER="openrouter",
    )
    @patch(OPENAI_PATCH_TARGET)
    def test_chat_completion_json_retries_after_invalid_json(self, mock_openai):
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
