"""
Tests for the AI Passport Parser service.
"""

import json
from unittest.mock import MagicMock, patch

from core.services.ai_passport_parser import AIPassportParser, AIPassportResult, PassportData
from django.test import TestCase, override_settings
from PIL import Image

# Patch target for OpenAI client (in ai_client module)
OPENAI_PATCH_TARGET = "core.services.ai_client.OpenAI"


class AIPassportParserTestCase(TestCase):
    """Test cases for AIPassportParser class."""



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
        mock_file.name = "test.txt"  # Unsupported

        result = parser.parse_passport_image(mock_file, filename="test.txt")

        self.assertFalse(result.success)
        self.assertIn("Unsupported file type", result.error_message)



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
        self.assertIn("AI provider error", result.error_message)

    @override_settings(
        OPENROUTER_API_KEY="test-key",
        LLM_PROVIDER="openrouter",
    )
    @patch(OPENAI_PATCH_TARGET)
    def test_validate_passport_image_two_shot_success(self, mock_openai):
        parser = AIPassportParser()

        pass_one = {
            "parameter_checks": {
                "mrz_two_lines_present_and_readable": {"valid": True, "reason": "Both MRZ lines readable."},
            },
            "overall_summary": "All checks passed.",
        }
        pass_two = {
            "is_valid": True,
            "passport_data": {
                "first_name": "Mario",
                "last_name": "Rossi",
                "full_name": "Mario Rossi",
                "nationality": "ITA",
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
                "full_page_visible": True,
                "all_corners_visible": True,
                "mrz_fully_visible": True,
                "has_cropped_or_cutoff": False,
                "is_blurry": False,
            },
            "ordered_failures": [],
            "summary": "Passport is valid.",
        }

        with patch.object(parser.ai_client, "chat_completion_json", side_effect=[pass_one, pass_two]) as mock_json:
            result = parser.validate_passport_image_two_shot(
                b"\x89PNG\r\n\x1a\n" + b"\x00" * 100,
                filename="passport.jpeg",
                analysis_context={"deterministic_quality": {"is_good_quality": True}},
            )

        self.assertTrue(result.success)
        self.assertEqual(result.passport_data.passport_number, "YA1234567")
        self.assertTrue(result.decision["is_valid"])
        self.assertEqual(mock_json.call_count, 2)

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
