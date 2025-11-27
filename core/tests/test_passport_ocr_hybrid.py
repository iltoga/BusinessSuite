"""
Tests for hybrid passport OCR extraction (MRZ + AI).
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from core.utils.passport_ocr import _merge_passport_data, extract_passport_with_ai


class MergePassportDataTestCase(TestCase):
    """Test cases for _merge_passport_data function."""

    def setUp(self):
        """Set up test data."""
        self.mrz_data = {
            "names": "Mario",
            "surname": "Rossi",
            "sex": "M",
            "nationality": "ITA",
            "nationality_raw": "ITA",
            "country_name": "Italy",
            "number": "YA1234567",
            "date_of_birth": "850315",
            "date_of_birth_yyyy_mm_dd": "1985-03-15",
            "expiration_date": "300109",
            "expiration_date_yyyy_mm_dd": "2030-01-09",
        }

        self.ai_data = {
            "ai_first_name": "Mario",
            "ai_last_name": "Rossi",
            "ai_full_name": "Mario Rossi",
            "ai_nationality": "Italy",
            "ai_nationality_code": "ITA",
            "ai_gender": "M",
            "ai_date_of_birth": "1985-03-15",
            "ai_birth_place": "Rome",
            "ai_passport_number": "YA1234567",
            "ai_passport_issue_date": "2020-01-10",
            "ai_passport_expiration_date": "2030-01-09",
            "ai_issuing_country": "Italy",
            "ai_issuing_country_code": "ITA",
            "ai_issuing_authority": "Ministry of Interior",
            "ai_height_cm": 175,
            "ai_eye_color": "Brown",
            "ai_address_abroad": "123 Example St, Bali",
            "ai_document_type": "P",
            "ai_confidence_score": 0.92,
        }

    def test_merge_adds_ai_only_fields(self):
        """Test that AI-only fields are added to merged result."""
        import logging

        logger = logging.getLogger("passport_ocr")

        merged = _merge_passport_data(self.mrz_data, self.ai_data, logger)

        # Check AI-only fields are added
        self.assertEqual(merged["birth_place"], "Rome")
        self.assertEqual(merged["passport_issue_date"], "2020-01-10")
        self.assertEqual(merged["issuing_authority"], "Ministry of Interior")
        self.assertEqual(merged["height_cm"], 175)
        self.assertEqual(merged["eye_color"], "Brown")
        self.assertEqual(merged["address_abroad"], "123 Example St, Bali")
        self.assertEqual(merged["issuing_country"], "Italy")

    def test_merge_preserves_mrz_data(self):
        """Test that original MRZ data is preserved."""
        import logging

        logger = logging.getLogger("passport_ocr")

        merged = _merge_passport_data(self.mrz_data, self.ai_data, logger)

        # Check MRZ data is preserved
        self.assertEqual(merged["number"], "YA1234567")
        self.assertEqual(merged["date_of_birth_yyyy_mm_dd"], "1985-03-15")
        self.assertEqual(merged["expiration_date_yyyy_mm_dd"], "2030-01-09")
        self.assertEqual(merged["nationality"], "ITA")
        self.assertEqual(merged["sex"], "M")

    def test_merge_adds_extraction_method_flag(self):
        """Test that extraction method flag is added."""
        import logging

        logger = logging.getLogger("passport_ocr")

        merged = _merge_passport_data(self.mrz_data, self.ai_data, logger)

        self.assertEqual(merged["extraction_method"], "hybrid_mrz_ai")
        self.assertEqual(merged["ai_confidence_score"], 0.92)

    def test_merge_handles_empty_ai_fields(self):
        """Test handling of empty AI fields."""
        import logging

        logger = logging.getLogger("passport_ocr")

        # Remove some AI fields
        ai_data_partial = {
            "ai_first_name": "Mario",
            "ai_last_name": "Rossi",
            "ai_birth_place": None,  # Empty
            "ai_passport_issue_date": None,  # Empty
            "ai_height_cm": None,  # Empty
            "ai_confidence_score": 0.75,
        }

        merged = _merge_passport_data(self.mrz_data, ai_data_partial, logger)

        # Fields with None should not be added
        self.assertNotIn("birth_place", merged)
        self.assertNotIn("passport_issue_date", merged)
        self.assertNotIn("height_cm", merged)

    def test_merge_handles_nationality_mismatch(self):
        """Test handling of nationality mismatch between MRZ and AI."""
        import logging

        logger = logging.getLogger("passport_ocr")

        ai_data_mismatch = self.ai_data.copy()
        ai_data_mismatch["ai_nationality_code"] = "USA"  # Different from MRZ
        ai_data_mismatch["ai_nationality"] = "United States"

        merged = _merge_passport_data(self.mrz_data, ai_data_mismatch, logger)

        # MRZ nationality should be kept
        self.assertEqual(merged["nationality"], "ITA")
        # AI nationality should be stored for reference
        self.assertEqual(merged["ai_nationality_code"], "USA")
        self.assertEqual(merged["ai_nationality_name"], "United States")


class ExtractPassportWithAITestCase(TestCase):
    """Test cases for extract_passport_with_ai function."""

    @override_settings(
        OPENROUTER_API_KEY="test-key",
        LLM_PROVIDER="openrouter",
    )
    @patch("core.utils.passport_ocr.extract_mrz_data")
    @patch("core.utils.passport_ocr._extract_with_ai")
    def test_extract_with_ai_enabled(self, mock_ai_extract, mock_mrz_extract):
        """Test extraction with AI enabled returns merged data."""
        # Mock MRZ data
        mock_mrz_extract.return_value = {
            "names": "Mario",
            "surname": "Rossi",
            "number": "YA1234567",
            "nationality": "ITA",
            "sex": "M",
            "date_of_birth_yyyy_mm_dd": "1985-03-15",
            "expiration_date_yyyy_mm_dd": "2030-01-09",
        }

        # Mock AI data
        mock_ai_extract.return_value = {
            "ai_first_name": "Mario",
            "ai_last_name": "Rossi",
            "ai_birth_place": "Rome",
            "ai_passport_issue_date": "2020-01-10",
            "ai_confidence_score": 0.9,
        }

        mock_file = MagicMock()
        mock_file.name = "test.jpeg"

        result = extract_passport_with_ai(mock_file, use_ai=True)

        # Should have both MRZ and AI fields
        self.assertEqual(result["names"], "Mario")
        self.assertEqual(result["surname"], "Rossi")
        self.assertEqual(result["birth_place"], "Rome")
        self.assertEqual(result["passport_issue_date"], "2020-01-10")
        self.assertEqual(result["extraction_method"], "hybrid_mrz_ai")

    @patch("core.utils.passport_ocr.extract_mrz_data")
    def test_extract_with_ai_disabled(self, mock_mrz_extract):
        """Test extraction with AI disabled returns only MRZ data."""
        mock_mrz_extract.return_value = {
            "names": "Mario",
            "surname": "Rossi",
            "number": "YA1234567",
        }

        mock_file = MagicMock()
        mock_file.name = "test.jpeg"

        result = extract_passport_with_ai(mock_file, use_ai=False)

        # Should only have MRZ fields
        self.assertEqual(result["names"], "Mario")
        self.assertNotIn("extraction_method", result)
        self.assertNotIn("birth_place", result)

    @override_settings(
        OPENROUTER_API_KEY="test-key",
        LLM_PROVIDER="openrouter",
    )
    @patch("core.utils.passport_ocr.extract_mrz_data")
    @patch("core.utils.passport_ocr._extract_with_ai")
    def test_extract_with_ai_failure_falls_back(self, mock_ai_extract, mock_mrz_extract):
        """Test that AI failure falls back to MRZ-only data."""
        mock_mrz_extract.return_value = {
            "names": "Mario",
            "surname": "Rossi",
            "number": "YA1234567",
        }

        # AI extraction fails
        mock_ai_extract.return_value = None

        mock_file = MagicMock()
        mock_file.name = "test.jpeg"

        result = extract_passport_with_ai(mock_file, use_ai=True)

        # Should still return MRZ data
        self.assertEqual(result["names"], "Mario")
        self.assertEqual(result["surname"], "Rossi")
        self.assertNotIn("extraction_method", result)

    @override_settings(
        OPENROUTER_API_KEY="test-key",
        LLM_PROVIDER="openrouter",
    )
    @patch("core.utils.passport_ocr.extract_mrz_data")
    @patch("core.utils.passport_ocr._extract_with_ai")
    def test_extract_with_ai_exception_falls_back(self, mock_ai_extract, mock_mrz_extract):
        """Test that AI exception falls back to MRZ-only data."""
        mock_mrz_extract.return_value = {
            "names": "Mario",
            "surname": "Rossi",
            "number": "YA1234567",
        }

        # AI extraction raises exception
        mock_ai_extract.side_effect = Exception("API error")

        mock_file = MagicMock()
        mock_file.name = "test.jpeg"

        result = extract_passport_with_ai(mock_file, use_ai=True)

        # Should still return MRZ data
        self.assertEqual(result["names"], "Mario")
        self.assertNotIn("extraction_method", result)
