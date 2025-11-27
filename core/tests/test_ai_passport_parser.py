"""
Tests for the AI Passport Parser service.
"""

import json
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from core.services.ai_passport_parser import AIPassportParser, AIPassportResult, PassportData

# Patch target for OpenAI client (in ai_client module)
OPENAI_PATCH_TARGET = "core.services.ai_client.OpenAI"


class AIPassportParserTestCase(TestCase):
    """Test cases for AIPassportParser class."""

    @override_settings(
        OPENROUTER_API_KEY="test-key",
        LLM_PROVIDER="openrouter",
        LLM_DEFAULT_MODEL="google/gemini-2.0-flash-001",
    )
    def test_parser_initialization_with_openrouter(self):
        """Test that parser initializes correctly with OpenRouter settings."""
        with patch(OPENAI_PATCH_TARGET) as mock_openai:
            parser = AIPassportParser()
            self.assertEqual(parser.ai_client.api_key, "test-key")
            self.assertEqual(parser.model, "google/gemini-2.0-flash-001")
            self.assertTrue(parser.use_openrouter)
            mock_openai.assert_called_once()

    @override_settings(
        OPENAI_API_KEY="openai-test-key",
        LLM_PROVIDER="openai",
        LLM_DEFAULT_MODEL="gpt-4o-mini",
    )
    def test_parser_initialization_with_openai(self):
        """Test that parser initializes correctly with OpenAI settings."""
        with patch(OPENAI_PATCH_TARGET) as mock_openai:
            parser = AIPassportParser()
            self.assertEqual(parser.ai_client.api_key, "openai-test-key")
            self.assertEqual(parser.model, "gpt-4o-mini")
            self.assertFalse(parser.use_openrouter)
            mock_openai.assert_called_once()

    def test_parser_initialization_without_api_key_raises_error(self):
        """Test that parser raises error when no API key is configured."""
        with override_settings(OPENROUTER_API_KEY=None, OPENAI_API_KEY=None, LLM_PROVIDER="openrouter"):
            with self.assertRaises(ValueError) as context:
                AIPassportParser()
            self.assertIn("API key not configured", str(context.exception))

    def test_passport_data_dataclass(self):
        """Test PassportData dataclass initialization."""
        data = PassportData(
            first_name="John",
            last_name="Doe",
            nationality="United States",
            nationality_code="USA",
            gender="M",
            date_of_birth="1990-01-15",
            birth_place="New York",
            passport_number="123456789",
            passport_issue_date="2020-05-01",
            passport_expiration_date="2030-05-01",
            confidence_score=0.95,
        )
        self.assertEqual(data.first_name, "John")
        self.assertEqual(data.last_name, "Doe")
        self.assertEqual(data.nationality_code, "USA")
        self.assertEqual(data.confidence_score, 0.95)

    def test_passport_data_defaults(self):
        """Test PassportData dataclass defaults."""
        data = PassportData()
        self.assertIsNone(data.first_name)
        self.assertIsNone(data.last_name)
        self.assertIsNone(data.birth_place)
        self.assertEqual(data.confidence_score, 0.0)

    @override_settings(
        OPENROUTER_API_KEY="test-key",
        LLM_PROVIDER="openrouter",
    )
    @patch(OPENAI_PATCH_TARGET)
    def test_parse_passport_image_unsupported_file_type(self, mock_openai):
        """Test that unsupported file types return an error."""
        parser = AIPassportParser()

        # Create a mock file with unsupported extension
        mock_file = MagicMock()
        mock_file.name = "test.pdf"  # PDF not supported for images

        result = parser.parse_passport_image(mock_file, filename="test.pdf")

        self.assertFalse(result.success)
        self.assertIn("Unsupported file type", result.error_message)

    @override_settings(
        OPENROUTER_API_KEY="test-key",
        LLM_PROVIDER="openrouter",
    )
    @patch(OPENAI_PATCH_TARGET)
    def test_parse_passport_image_success(self, mock_openai):
        """Test successful passport image parsing with mocked LLM response."""
        # Mock the LLM response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(
            {
                "first_name": "Mario",
                "last_name": "Rossi",
                "full_name": "Mario Rossi",
                "nationality": "Italy",
                "nationality_code": "ITA",
                "gender": "M",
                "date_of_birth": "1985-03-15",
                "birth_place": "Rome",
                "passport_number": "YA1234567",
                "passport_issue_date": "2020-01-10",
                "passport_expiration_date": "2030-01-09",
                "issuing_country": "Italy",
                "issuing_country_code": "ITA",
                "issuing_authority": "Ministry of Interior",
                "height_cm": 175,
                "eye_color": "Brown",
                "address_abroad": None,
                "document_type": "P",
                "confidence_score": 0.92,
            }
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        parser = AIPassportParser()

        # Create proper bytes for the mock file
        fake_image_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # Minimal PNG-like bytes

        result = parser.parse_passport_image(fake_image_bytes, filename="passport.jpeg")

        self.assertTrue(result.success)
        self.assertEqual(result.passport_data.first_name, "Mario")
        self.assertEqual(result.passport_data.last_name, "Rossi")
        self.assertEqual(result.passport_data.nationality_code, "ITA")
        self.assertEqual(result.passport_data.birth_place, "Rome")
        self.assertEqual(result.passport_data.height_cm, 175)
        self.assertEqual(result.passport_data.eye_color, "Brown")
        self.assertEqual(result.passport_data.confidence_score, 0.92)

    @override_settings(
        OPENROUTER_API_KEY="test-key",
        LLM_PROVIDER="openrouter",
    )
    @patch(OPENAI_PATCH_TARGET)
    def test_parse_passport_image_api_error(self, mock_openai):
        """Test handling of API errors during parsing."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API Error")
        mock_openai.return_value = mock_client

        parser = AIPassportParser()

        # Create proper bytes for the mock file
        fake_image_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        result = parser.parse_passport_image(fake_image_bytes, filename="passport.jpeg")

        self.assertFalse(result.success)
        self.assertIn("API Error", result.error_message)

    def test_passport_schema_structure(self):
        """Test that the passport schema has the correct structure."""
        schema = AIPassportParser.PASSPORT_SCHEMA

        self.assertEqual(schema["type"], "object")
        self.assertIn("first_name", schema["properties"])
        self.assertIn("last_name", schema["properties"])
        self.assertIn("birth_place", schema["properties"])
        self.assertIn("height_cm", schema["properties"])
        self.assertIn("eye_color", schema["properties"])
        self.assertIn("issuing_authority", schema["properties"])
        self.assertIn("confidence_score", schema["properties"])

        # Check required fields
        required = schema["required"]
        self.assertIn("first_name", required)
        self.assertIn("passport_number", required)
        self.assertIn("confidence_score", required)


class AIPassportResultTestCase(TestCase):
    """Test cases for AIPassportResult dataclass."""

    def test_result_success(self):
        """Test successful result creation."""
        passport_data = PassportData(first_name="John", last_name="Doe")
        result = AIPassportResult(
            passport_data=passport_data,
            raw_response={"test": "data"},
            success=True,
            error_message=None,
        )
        self.assertTrue(result.success)
        self.assertIsNone(result.error_message)
        self.assertEqual(result.passport_data.first_name, "John")

    def test_result_failure(self):
        """Test failed result creation."""
        result = AIPassportResult(
            passport_data=PassportData(),
            success=False,
            error_message="Test error message",
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error_message, "Test error message")
