from datetime import date, timedelta
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

    @override_settings(
        LLM_PROVIDER="groq",
        CHECK_PASSPORT_MODEL="meta-llama/llama-4-scout-17b-16e-instruct",
    )
    @patch("core.services.passport_uploadability_service.AIPassportParser")
    def test_does_not_force_openrouter_provider(self, mock_parser_cls):
        mock_parser = MagicMock()
        mock_parser.model = "meta-llama/llama-4-scout-17b-16e-instruct"
        mock_parser_cls.return_value = mock_parser

        PassportUploadabilityService()

        kwargs = mock_parser_cls.call_args.kwargs
        self.assertNotIn("use_openrouter", kwargs)
        self.assertEqual(kwargs.get("model"), "meta-llama/llama-4-scout-17b-16e-instruct")

    @patch("core.services.passport_uploadability_service.AIPassportParser")
    def test_does_not_reject_when_only_deterministic_mrz_cutoff_hint_is_present(self, mock_parser_cls):
        mock_parser = MagicMock()
        mock_parser.model = "google/gemini-3-flash-preview"
        mock_parser_cls.return_value = mock_parser

        service = PassportUploadabilityService()
        service.image_quality_service = MagicMock()
        service.image_quality_service.evaluate.return_value = ImageQualityResult(
            is_good_quality=True,
            analyzer_available=True,
            mrz_zone_incomplete_suspected=True,
        )

        with patch.object(service, "_check_ai") as mock_ai:
            mock_ai.return_value = MagicMock(
                is_valid=True,
                method_used="ai",
                model_used="google/gemini-3-flash-preview",
                passport_data={"passport_number": "YA1234567"},
                rejection_code=None,
            )

            result = service.check_passport(b"fake", method="hybrid")

            self.assertTrue(result.is_valid)
            mock_ai.assert_called_once()

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
    def test_ai_does_not_auto_reject_when_deterministic_mrz_cutoff_is_true(self, mock_parser_cls):
        mock_parser = MagicMock()
        mock_parser.model = "google/gemini-3-flash-preview"
        mock_parser_cls.return_value = mock_parser

        service = PassportUploadabilityService()

        with patch.object(service.ai_parser, "validate_passport_image_two_shot") as mock_validate:
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
            mock_validate.return_value = MagicMock(
                success=True,
                passport_data=mock_data,
                parameter_checks={},
                decision={"is_valid": True, "ordered_failures": []},
            )

            result = service._check_ai(
                b"fake",
                analysis_context={"deterministic_quality": {"mrz_cutoff_suspected": True}},
            )

            self.assertTrue(result.is_valid)
            self.assertIsNone(result.rejection_code)

    @patch("core.services.passport_uploadability_service.AIPassportParser")
    def test_prioritizes_mrz_incomplete_over_generic_page_cropped(self, mock_parser_cls):
        mock_parser = MagicMock()
        mock_parser.model = "google/gemini-3-flash-preview"
        mock_parser_cls.return_value = mock_parser

        service = PassportUploadabilityService()

        with patch.object(service.ai_parser, "validate_passport_image_two_shot") as mock_validate:
            mock_data = MagicMock(
                full_page_visible=False,
                all_corners_visible=True,
                has_cropped_or_cutoff=True,
                mrz_fully_visible=False,
                is_blurry=False,
                confidence_score=0.9,
                passport_number="YA1234567",
                last_name="Rossi",
                first_name="Mario",
                nationality="ITA",
                passport_expiration_date="2032-01-01",
            )
            mock_validate.return_value = MagicMock(
                success=True,
                passport_data=mock_data,
                parameter_checks={},
                decision={
                    "is_valid": False,
                    "ordered_failures": [
                        {
                            "parameter": "mrz_zone_complete",
                            "reason": "MRZ zone incomplete.",
                            "importance": "critical",
                        },
                        {"parameter": "full_page_visible", "reason": "Page is cropped.", "importance": "major"},
                    ]
                },
            )

            result = service._check_ai(b"fake", analysis_context={"deterministic_quality": {}})

            self.assertFalse(result.is_valid)
            self.assertEqual(result.rejection_code, "mrz_incomplete")

    @patch("core.services.passport_uploadability_service.AIPassportParser")
    def test_ignores_cutoff_only_failures_from_ai_decision(self, mock_parser_cls):
        mock_parser = MagicMock()
        mock_parser.model = "google/gemini-3-flash-preview"
        mock_parser_cls.return_value = mock_parser

        service = PassportUploadabilityService()

        with patch.object(service.ai_parser, "validate_passport_image_two_shot") as mock_validate:
            mock_data = MagicMock(
                full_page_visible=True,
                all_corners_visible=True,
                has_cropped_or_cutoff=True,
                mrz_fully_visible=True,
                is_blurry=False,
                confidence_score=0.95,
                passport_number="YA1234567",
                last_name="Rossi",
                first_name="Mario",
                nationality="ITA",
                passport_expiration_date="2032-01-01",
            )
            mock_validate.return_value = MagicMock(
                success=True,
                passport_data=mock_data,
                parameter_checks={},
                decision={
                    "is_valid": False,
                    "ordered_failures": [
                        {
                            "parameter": "full_page_visible",
                            "reason": "The page appears cropped at the bottom edge.",
                            "importance": "major",
                        }
                    ],
                },
            )

            result = service._check_ai(
                b"fake",
                analysis_context={"deterministic_quality": {"mrz_zone_incomplete_suspected": True}},
            )

            self.assertTrue(result.is_valid)
            self.assertIsNone(result.rejection_code)


    @patch("core.services.passport_uploadability_service.AIPassportParser")
    def test_rejects_low_confidence_when_below_threshold(self, mock_parser_cls):
        mock_parser = MagicMock()
        mock_parser.model = "google/gemini-3-flash-preview"
        mock_parser_cls.return_value = mock_parser

        service = PassportUploadabilityService()

        with patch.object(service.ai_parser, "validate_passport_image_two_shot") as mock_validate:
            mock_data = MagicMock(
                full_page_visible=True,
                all_corners_visible=True,
                has_cropped_or_cutoff=False,
                mrz_fully_visible=True,
                is_blurry=False,
                confidence_score=0.45,
                passport_number="YA1234567",
                last_name="Rossi",
                first_name="Mario",
                nationality="ITA",
                passport_expiration_date="2032-01-01",
            )
            mock_validate.return_value = MagicMock(
                success=True,
                passport_data=mock_data,
                parameter_checks={},
                decision={
                    "is_valid": True,
                    "ordered_failures": [
                        {
                            "parameter": "confidence_score",
                            "reason": "Confidence score is below threshold.",
                            "importance": "major",
                        }
                    ]
                },
            )

            result = service._check_ai(
                b"fake",
                analysis_context={"deterministic_quality": {"analyzer_available": True, "is_good_quality": True}},
            )

            self.assertFalse(result.is_valid)
            self.assertEqual(result.rejection_code, "low_confidence")

    @patch("core.services.passport_uploadability_service.AIPassportParser")
    def test_rejects_invalid_passport_number_format(self, mock_parser_cls):
        mock_parser = MagicMock()
        mock_parser.model = "google/gemini-3-flash-preview"
        mock_parser_cls.return_value = mock_parser

        service = PassportUploadabilityService()

        with patch.object(service.ai_parser, "validate_passport_image_two_shot") as mock_validate:
            mock_data = MagicMock(
                full_page_visible=True,
                all_corners_visible=True,
                mrz_fully_visible=True,
                is_blurry=False,
                confidence_score=0.95,
                passport_number="A<<<123",
                last_name="Rossi",
                first_name="Mario",
                nationality="ITA",
                nationality_code="ITA",
                passport_expiration_date="2032-01-01",
            )
            mock_validate.return_value = MagicMock(
                success=True,
                passport_data=mock_data,
                parameter_checks={},
                decision={"is_valid": True, "ordered_failures": []},
            )

            result = service._check_ai(b"fake", analysis_context={"deterministic_quality": {}})

            self.assertFalse(result.is_valid)
            self.assertEqual(result.rejection_code, "invalid_passport_number")

    @patch("core.services.passport_uploadability_service.AIPassportParser")
    def test_rejects_passport_expiring_within_180_days(self, mock_parser_cls):
        mock_parser = MagicMock()
        mock_parser.model = "google/gemini-3-flash-preview"
        mock_parser_cls.return_value = mock_parser

        service = PassportUploadabilityService()

        with patch.object(service.ai_parser, "validate_passport_image_two_shot") as mock_validate:
            expiring_soon = (date.today() + timedelta(days=90)).isoformat()
            mock_data = MagicMock(
                full_page_visible=True,
                all_corners_visible=True,
                mrz_fully_visible=True,
                is_blurry=False,
                confidence_score=0.95,
                passport_number="YA1234567",
                last_name="Rossi",
                first_name="Mario",
                nationality="ITA",
                nationality_code="ITA",
                passport_expiration_date=expiring_soon,
            )
            mock_validate.return_value = MagicMock(
                success=True,
                passport_data=mock_data,
                parameter_checks={},
                decision={"is_valid": True, "ordered_failures": []},
            )

            result = service._check_ai(b"fake", analysis_context={"deterministic_quality": {}})

            self.assertFalse(result.is_valid)
            self.assertEqual(result.rejection_code, "expiring_soon")
