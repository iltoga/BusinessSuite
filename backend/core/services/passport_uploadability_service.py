import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from core.services.ai_passport_parser import AIPassportParser
from core.services.image_quality_service import ImageQualityService
from core.services.logger_service import Logger
from core.utils.icao_validation import validate_passport_number_icao

logger = Logger.get_logger(__name__)


@dataclass
class UploadabilityResult:
    is_valid: bool
    method_used: str
    rejection_reason: Optional[str] = None
    rejection_code: Optional[str] = None
    passport_data: Optional[dict] = None
    model_used: Optional[str] = None


class PassportUploadabilityService:

    def __init__(
        self, check_passport_model: Optional[str] = None, ai_min_confidence_for_upload: Optional[float] = None
    ):
        # get settings from django settings or throw if not set
        from django.conf import settings

        self.CHECK_PASSPORT_MODEL = check_passport_model or getattr(settings, "CHECK_PASSPORT_MODEL")
        if not self.CHECK_PASSPORT_MODEL:
            raise ValueError("CHECK_PASSPORT_MODEL setting is required for PassportUploadabilityService")
        self.AI_MIN_CONFIDENCE_FOR_UPLOAD = ai_min_confidence_for_upload or getattr(
            settings, "CHECK_PASSPORT_AI_MIN_CONFIDENCE_FOR_UPLOAD"
        )
        if self.AI_MIN_CONFIDENCE_FOR_UPLOAD is None:
            raise ValueError(
                "CHECK_PASSPORT_AI_MIN_CONFIDENCE_FOR_UPLOAD setting is required for PassportUploadabilityService"
            )

        # Force this feature to use Gemini 3 Flash Preview via OpenRouter as requested.
        self.ai_parser = AIPassportParser(model=self.CHECK_PASSPORT_MODEL, use_openrouter=True)
        self.image_quality_service = ImageQualityService()

    @staticmethod
    def _emit_progress(progress_callback: Optional[Callable[[int, str], None]], progress: int, message: str) -> None:
        if progress_callback:
            try:
                progress_callback(progress, message)
            except Exception:
                logger.debug("Progress callback raised an exception", exc_info=True)

    def check_passport(
        self,
        file_content: bytes,
        method: str = "hybrid",
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> UploadabilityResult:
        """
        Check passport uploadability using deterministic image quality + AI.
        Supported methods: 'ai' and 'hybrid'.
        Legacy 'internal' is mapped to 'ai' (PassportEye path removed).
        """
        selected_method = (method or "hybrid").strip().lower()
        normalized_method = "ai" if selected_method in {"internal", "ai"} else "hybrid"

        self._emit_progress(progress_callback, 15, "Step 1/3: Running deterministic OpenCV quality checks...")
        quality_result = self.image_quality_service.evaluate(file_content)
        if quality_result.analyzer_available and not quality_result.is_good_quality:
            return UploadabilityResult(
                is_valid=False,
                method_used=f"{normalized_method} (opencv-quality-gate)",
                rejection_code=quality_result.rejection_code or "image_low_quality",
                rejection_reason=quality_result.rejection_reason
                or "Image quality is insufficient for reliable passport verification.",
                passport_data={"quality": quality_result.as_dict()},
                model_used=self.ai_parser.model,
            )

        quality_context = quality_result.as_dict()

        if normalized_method == "ai":
            self._emit_progress(progress_callback, 65, "Step 2/3: Running AI passport analysis...")
            ai_context: dict[str, Any] = {
                "deterministic_quality": quality_context,
                "verification_mode": "ai",
                "internal_mode_deprecated": selected_method == "internal",
            }
            ai_result = self._check_ai(file_content, analysis_context=ai_context)
            if selected_method == "internal":
                ai_result.method_used = "ai (internal-deprecated)"
            if not ai_result.model_used:
                ai_result.model_used = self.ai_parser.model
            return ai_result

        self._emit_progress(progress_callback, 45, "Step 2/3: Building hybrid decision context...")
        self._emit_progress(progress_callback, 70, "Step 3/3: Running AI decision with deterministic context...")
        ai_context = {
            "deterministic_quality": quality_context,
            "verification_mode": "hybrid",
            "internal_removed": True,
        }
        ai_result = self._check_ai(file_content, analysis_context=ai_context)
        ai_result.method_used = "hybrid (deterministic+ai)"
        if not ai_result.model_used:
            ai_result.model_used = self.ai_parser.model
        return ai_result

    @staticmethod
    def _normalize_name(value: Optional[str]) -> str:
        if not value:
            return ""
        normalized = value.replace("<", " ")
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _is_name_sensible(self, value: Optional[str]) -> bool:
        name = self._normalize_name(value)
        if len(name) < 2 or len(name) > 80:
            return False
        if re.search(r"[^A-Za-z\s'\-]", name):
            return False
        if re.search(r"(.)\1{3,}", name, re.IGNORECASE):
            return False
        tokens = [token for token in name.split(" ") if token]
        if not tokens or len(tokens) > 6:
            return False
        if any(len(token) < 2 for token in tokens):
            return False
        return True

    @staticmethod
    def _is_nationality_code_sensible(value: Optional[str]) -> bool:
        if not value:
            return False
        return bool(re.match(r"^[A-Z]{3}$", value.strip().upper()))

    def _check_ai(self, file_content: bytes, analysis_context: Optional[dict[str, Any]] = None) -> UploadabilityResult:
        result = self.ai_parser.parse_passport_image(
            file_content,
            "passport.jpg",
            analysis_context=analysis_context,
        )

        if not result.success:
            return UploadabilityResult(
                is_valid=False,
                method_used="ai",
                model_used=self.ai_parser.model,
                rejection_reason=result.error_message or "AI could not parse the passport.",
            )

        data = result.passport_data

        deterministic_quality = (analysis_context or {}).get("deterministic_quality") or {}
        if deterministic_quality.get("mrz_cutoff_suspected") is True:
            return UploadabilityResult(
                is_valid=False,
                method_used="ai",
                model_used=self.ai_parser.model,
                rejection_code="mrz_cropped",
                rejection_reason=(
                    "Deterministic checks detected the last MRZ line touching/cut by the bottom edge. "
                    "Please upload a full passport image with both complete MRZ lines visible."
                ),
            )

        # Hard quality/completeness gates from AI quality flags.
        if (
            data.full_page_visible is not True
            or data.all_corners_visible is not True
            or data.has_cropped_or_cutoff is True
        ):
            return UploadabilityResult(
                is_valid=False,
                method_used="ai",
                model_used=self.ai_parser.model,
                rejection_code="page_cropped",
                rejection_reason=(
                    "Passport page is incomplete/cropped. Please upload one full passport biodata page "
                    "with all 4 corners and full MRZ visible."
                ),
            )

        if data.mrz_fully_visible is not True:
            return UploadabilityResult(
                is_valid=False,
                method_used="ai",
                model_used=self.ai_parser.model,
                rejection_code="mrz_incomplete",
                rejection_reason=(
                    "MRZ is incomplete or not fully readable (expected 2 full lines). "
                    "Please upload a complete, non-cropped passport page with the full MRZ visible."
                ),
            )

        if data.is_blurry is True:
            return UploadabilityResult(
                is_valid=False,
                method_used="ai",
                model_used=self.ai_parser.model,
                rejection_code="image_blurry",
                rejection_reason=(
                    "Passport image is blurry. Please upload a sharper image where text and MRZ are clearly readable."
                ),
            )

        # Reject likely cropped / partially visible passport pages.
        # The AI prompt instructs low confidence when any page edge/corner is not fully visible.
        if data.confidence_score < self.AI_MIN_CONFIDENCE_FOR_UPLOAD:
            return UploadabilityResult(
                is_valid=False,
                method_used="ai",
                model_used=self.ai_parser.model,
                rejection_code="page_cropped",
                rejection_reason=(
                    "Passport page is not fully visible or image quality is insufficient. "
                    "Please upload a clear image showing the entire passport biodata page (all 4 corners visible)."
                ),
            )

        # Check if essential fields are present
        if not data.passport_number or not data.last_name or not data.nationality:
            return UploadabilityResult(
                is_valid=False,
                method_used="ai",
                model_used=self.ai_parser.model,
                rejection_code="missing_essential_fields",
                rejection_reason="AI could not extract essential fields (passport number, name, nationality). The image might be too blurred or obscured.",
            )

        first_name = self._normalize_name(data.first_name)
        last_name = self._normalize_name(data.last_name)
        nationality = (data.nationality or "").strip().upper()
        passport_number = (data.passport_number or "").strip().upper()

        if not self._is_name_sensible(first_name) or not self._is_name_sensible(last_name):
            return UploadabilityResult(
                is_valid=False,
                method_used="ai",
                model_used=self.ai_parser.model,
                rejection_code="invalid_name",
                rejection_reason="Extracted name/lastname do not look valid. Please upload a clearer full-page passport image.",
            )

        if not self._is_nationality_code_sensible(nationality):
            return UploadabilityResult(
                is_valid=False,
                method_used="ai",
                model_used=self.ai_parser.model,
                rejection_code="invalid_nationality",
                rejection_reason="Extracted nationality code is invalid. Please upload a clearer full-page passport image.",
            )

        passport_ok, passport_msg = validate_passport_number_icao(passport_number)
        if not passport_ok:
            return UploadabilityResult(
                is_valid=False,
                method_used="ai",
                model_used=self.ai_parser.model,
                rejection_code="invalid_passport_number",
                rejection_reason=f"Extracted passport number is invalid: {passport_msg}",
            )

        # Check expiration date
        if data.passport_expiration_date:
            try:
                exp_date = datetime.strptime(data.passport_expiration_date, "%Y-%m-%d").date()
                if exp_date < datetime.now().date() + timedelta(days=180):
                    return UploadabilityResult(
                        is_valid=False,
                        method_used="ai",
                        model_used=self.ai_parser.model,
                        rejection_reason=f"Passport expires on {exp_date}, which is less than 180 days from today.",
                    )
            except ValueError:
                pass

        return UploadabilityResult(
            is_valid=True,
            method_used="ai",
            model_used=self.ai_parser.model,
            passport_data={
                "first_name": first_name,
                "last_name": last_name,
                "nationality": nationality,
                "passport_number": passport_number,
                "expiration_date": data.passport_expiration_date,
            },
        )
