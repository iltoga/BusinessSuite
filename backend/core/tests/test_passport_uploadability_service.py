from unittest.mock import MagicMock, patch

from core.services.image_quality_service import ImageQualityResult
from core.services.passport_uploadability_service import PassportUploadabilityService
from django.test import TestCase, override_settings


@override_settings(
    CHECK_PASSPORT_MODEL="google/gemini-3-flash-preview",
    CHECK_PASSPORT_AI_MIN_CONFIDENCE_FOR_UPLOAD=0.7,
    OPENROUTER_API_KEY="test-key",
    LLM_PROVIDER="openrouter",
)
class PassportUploadabilityServiceQualityGateTestCase(TestCase):
    @patch("core.services.passport_uploadability_service.AIPassportParser")
    def test_rejects_when_quality_gate_fails(self, mock_parser_cls):
        mock_parser = MagicMock()
        mock_parser.model = "google/gemini-3-flash-preview"
        mock_parser_cls.return_value = mock_parser

        service = PassportUploadabilityService()
        service.image_quality_service = MagicMock()
        service.image_quality_service.evaluate.return_value = ImageQualityResult(
            is_good_quality=False,
            analyzer_available=True,
            rejection_code="image_blurry",
            rejection_reason="Image appears blurry.",
        )

        result = service.check_passport(b"fake", method="hybrid")

        self.assertFalse(result.is_valid)
        self.assertEqual(result.rejection_code, "image_blurry")
        self.assertIn("opencv-quality-gate", result.method_used)

    @patch("core.services.passport_uploadability_service.AIPassportParser")
    def test_skips_gate_when_analyzer_unavailable(self, mock_parser_cls):
        mock_parser = MagicMock()
        mock_parser.model = "google/gemini-3-flash-preview"
        mock_parser_cls.return_value = mock_parser

        service = PassportUploadabilityService()
        service.image_quality_service = MagicMock()
        service.image_quality_service.evaluate.return_value = ImageQualityResult(
            is_good_quality=True,
            analyzer_available=False,
            rejection_code=None,
            rejection_reason=None,
        )

        with patch.object(service, "_check_ai") as mock_ai:
            mock_ai.return_value = MagicMock(
                is_valid=True,
                method_used="ai",
                model_used="google/gemini-3-flash-preview",
                passport_data={"passport_number": "YA1234567"},
            )
            service.check_passport(b"fake", method="ai")
            mock_ai.assert_called_once()

    @patch("core.services.passport_uploadability_service.AIPassportParser")
    def test_internal_method_is_deprecated_alias_to_ai(self, mock_parser_cls):
        mock_parser = MagicMock()
        mock_parser.model = "google/gemini-3-flash-preview"
        mock_parser_cls.return_value = mock_parser

        service = PassportUploadabilityService()
        service.image_quality_service = MagicMock()
        service.image_quality_service.evaluate.return_value = ImageQualityResult(
            is_good_quality=True,
            analyzer_available=True,
        )

        with patch.object(service, "_check_ai") as mock_ai:
            mock_ai.return_value = MagicMock(
                is_valid=True,
                method_used="ai",
                model_used="google/gemini-3-flash-preview",
                passport_data={"passport_number": "YA1234567"},
            )

            result = service.check_passport(b"fake", method="internal")

            self.assertTrue(result.is_valid)
            self.assertIn("internal-deprecated", result.method_used)
            mock_ai.assert_called_once()

    @patch("core.services.passport_uploadability_service.AIPassportParser")
    def test_hybrid_passes_deterministic_context_to_ai(self, mock_parser_cls):
        mock_parser = MagicMock()
        mock_parser.model = "google/gemini-3-flash-preview"
        mock_parser_cls.return_value = mock_parser

        service = PassportUploadabilityService()
        service.image_quality_service = MagicMock()
        service.image_quality_service.evaluate.return_value = ImageQualityResult(
            is_good_quality=True,
            analyzer_available=True,
            laplacian_variance=123.0,
        )

        with patch.object(service, "_check_ai") as mock_ai:
            mock_ai.return_value = MagicMock(
                is_valid=True,
                method_used="ai",
                model_used="google/gemini-3-flash-preview",
                passport_data={"passport_number": "YA1234567"},
            )

            service.check_passport(b"fake", method="hybrid")

            mock_ai.assert_called_once()
            _, kwargs = mock_ai.call_args
            analysis_context = kwargs.get("analysis_context")
            self.assertIsNotNone(analysis_context)
            self.assertIn("deterministic_quality", analysis_context)
            self.assertEqual(analysis_context.get("verification_mode"), "hybrid")

    @patch("core.services.passport_uploadability_service.AIPassportParser")
    def test_ai_rejects_when_deterministic_mrz_cutoff_is_true(self, mock_parser_cls):
        mock_parser = MagicMock()
        mock_parser.model = "google/gemini-3-flash-preview"
        mock_parser_cls.return_value = mock_parser

        service = PassportUploadabilityService()

        with patch.object(service.ai_parser, "parse_passport_image") as mock_parse:
            mock_data = MagicMock(
                full_page_visible=True,
                all_corners_visible=True,
                has_cropped_or_cutoff=False,
                mrz_fully_visible=True,
                is_blurry=False,
                confidence_score=0.99,
                passport_number="YA1234567",
                last_name="Rossi",
                first_name="Mario",
                nationality="ITA",
                passport_expiration_date="2032-01-01",
            )
            mock_parse.return_value = MagicMock(success=True, passport_data=mock_data)

            result = service._check_ai(
                b"fake",
                analysis_context={"deterministic_quality": {"mrz_cutoff_suspected": True}},
            )

            self.assertFalse(result.is_valid)
            self.assertEqual(result.rejection_code, "mrz_cropped")
