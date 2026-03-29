"""
FILE_ROLE: Service-layer logic for the core app.

KEY_COMPONENTS:
- UploadabilityResult: Result/dataclass helper.
- PassportUploadabilityService: Service class.

INTERACTIONS:
- Depends on: nearby Django models, services, serializers, and the app packages imported by this module.

AI_GUIDELINES:
- Keep the module focused on its narrow layer boundary and avoid moving cross-cutting workflow code here.
- Preserve the existing API/model contract because other modules import these symbols directly.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from core.services.ai_passport_parser import AIPassportParser
from core.services.ai_runtime_settings_service import AIRuntimeSettingsService
from core.services.ai_usage_service import AIUsageFeature
from core.services.image_quality_service import ImageQualityService
from core.services.logger_service import Logger
from core.utils.icao_validation import validate_passport_number_icao

logger = Logger.get_logger(__name__)


@dataclass
class UploadabilityResult:
    is_valid: bool
    method_used: str
    rejection_reason: Optional[str] = None
    rejection_reasons: Optional[list[str]] = None
    rejection_code: Optional[str] = None
    passport_data: Optional[dict] = None
    model_used: Optional[str] = None


class PassportUploadabilityService:

    def __init__(
        self, check_passport_model: Optional[str] = None, ai_min_confidence_for_upload: Optional[float] = None
    ):
        self.CHECK_PASSPORT_MODEL = check_passport_model or AIRuntimeSettingsService.get_check_passport_model()
        if not self.CHECK_PASSPORT_MODEL:
            raise ValueError("CHECK_PASSPORT_MODEL setting is required for PassportUploadabilityService")
        self.AI_MIN_CONFIDENCE_FOR_UPLOAD = (
            ai_min_confidence_for_upload or AIRuntimeSettingsService.get_check_passport_min_confidence()
        )
        if self.AI_MIN_CONFIDENCE_FOR_UPLOAD is None:
            raise ValueError(
                "CHECK_PASSPORT_AI_MIN_CONFIDENCE_FOR_UPLOAD setting is required for PassportUploadabilityService"
            )

        # Use the globally configured provider by default; model remains feature-specific.
        self.ai_parser = AIPassportParser(
            model=self.CHECK_PASSPORT_MODEL,
            feature_name=AIUsageFeature.PASSPORT_CHECK_API,
        )
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

        self._emit_progress(progress_callback, 15, "Step 1/4: Running deterministic OpenCV quality checks...")
        quality_result = self.image_quality_service.evaluate(file_content)
        if quality_result.analyzer_available and not quality_result.is_good_quality:
            return UploadabilityResult(
                is_valid=False,
                method_used=f"{normalized_method} (opencv-quality-gate)",
                rejection_code=quality_result.rejection_code or "image_low_quality",
                rejection_reason=quality_result.rejection_reason
                or "Image quality is insufficient for reliable passport verification.",
                rejection_reasons=(
                    [quality_result.rejection_reason]
                    if quality_result.rejection_reason
                    else ["Image quality is insufficient for reliable passport verification."]
                ),
                passport_data={"quality": quality_result.as_dict()},
                model_used=self.ai_parser.model,
            )

        quality_context = quality_result.as_dict()
        # Explicitly remove cutoff/cropping structural hints from passport validation context.
        # Passport rejection should be based on MRZ readability and quality, not edge/corner framing.
        for key in [
            "mrz_cutoff_suspected",
            "mrz_zone_incomplete_suspected",
            "mrz_detected_line_count",
            "mrz_bottom_touch_ratio",
            "bottom_edge_dark_ratio",
            "bottom_edge_edge_density",
        ]:
            quality_context.pop(key, None)

        if normalized_method == "ai":
            self._emit_progress(progress_callback, 35, "Step 2/4: Building AI validation context...")
            ai_context: dict[str, Any] = {
                "deterministic_quality": quality_context,
                "verification_mode": "ai",
                "internal_mode_deprecated": selected_method == "internal",
            }
            ai_result = self._check_ai(file_content, analysis_context=ai_context, progress_callback=progress_callback)
            if selected_method == "internal":
                ai_result.method_used = "ai (internal-deprecated)"
            if not ai_result.model_used:
                ai_result.model_used = self.ai_parser.model
            return ai_result

        self._emit_progress(progress_callback, 35, "Step 2/4: Building hybrid validation context...")
        ai_context = {
            "deterministic_quality": quality_context,
            "verification_mode": "hybrid",
            "internal_removed": True,
        }
        ai_result = self._check_ai(file_content, analysis_context=ai_context, progress_callback=progress_callback)
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

    @staticmethod
    def _extract_ordered_failures(decision: dict[str, Any], parameter_checks: dict[str, Any]) -> list[dict[str, str]]:
        failures: list[dict[str, str]] = []
        ordered_failures = decision.get("ordered_failures")
        if isinstance(ordered_failures, list):
            for item in ordered_failures:
                if not isinstance(item, dict):
                    continue
                parameter = str(item.get("parameter") or "").strip()
                reason = str(item.get("reason") or "").strip()
                importance = str(item.get("importance") or "major").strip().lower()
                if not parameter or not reason:
                    continue
                failures.append({"parameter": parameter, "reason": reason, "importance": importance})
        if failures:
            return failures

        # Fallback: derive failures deterministically from step-1 parameter checks.
        if isinstance(parameter_checks, dict):
            for key, value in parameter_checks.items():
                if not isinstance(value, dict):
                    continue
                if value.get("valid") is False:
                    reason = str(value.get("reason") or f"{key} failed").strip()
                    importance = "critical" if "mrz" in key else "major"
                    failures.append({"parameter": key, "reason": reason, "importance": importance})
        return failures

    @staticmethod
    def _map_parameter_to_rejection_code(parameter: str) -> str:
        p = (parameter or "").lower()
        if "mrz" in p:
            return "mrz_incomplete"
        if "blur" in p:
            return "image_blurry"
        if "corner" in p or "full_page" in p or "cropped" in p or "biodata_page" in p:
            return "page_cropped"
        if "reflection" in p or "text_readable" in p:
            return "image_low_quality"
        return "validation_failed"

    @staticmethod
    def _is_soft_quality_failure(parameter: str) -> bool:
        p = (parameter or "").lower()
        return any(token in p for token in ["blur", "reflection", "text_readable", "brightness", "confidence"])

    @staticmethod
    def _is_cutoff_failure(parameter: str, reason: str = "") -> bool:
        p = (parameter or "").lower()
        r = (reason or "").lower()
        cutoff_tokens = [
            "crop",
            "cutoff",
            "cut ",
            "corner",
            "full_page",
            "biodata_page",
            "page_visible",
            "outside frame",
            "edge",
        ]
        return any(token in p or token in r for token in cutoff_tokens)

    def _check_ai(
        self,
        file_content: bytes,
        analysis_context: Optional[dict[str, Any]] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> UploadabilityResult:
        def _stage_callback(stage: str) -> None:
            if stage == "ai_pass_1":
                self._emit_progress(
                    progress_callback,
                    60,
                    "Step 3/4: AI validation pass 1/2 (structured parameter analysis)...",
                )
            elif stage == "ai_pass_2":
                self._emit_progress(
                    progress_callback,
                    82,
                    "Step 4/4: AI validation pass 2/2 (decision synthesis)...",
                )

        validation = self.ai_parser.validate_passport_image_two_shot(
            file_content,
            "passport.jpg",
            analysis_context=analysis_context,
            stage_callback=_stage_callback,
        )

        if not validation.success:
            return UploadabilityResult(
                is_valid=False,
                method_used="ai",
                model_used=self.ai_parser.model,
                rejection_code="ai_validation_error",
                rejection_reason=validation.error_message or "AI validation failed.",
                rejection_reasons=[validation.error_message or "AI validation failed."],
            )

        data = validation.passport_data
        parameter_checks = validation.parameter_checks
        decision = validation.decision
        deterministic_quality = (analysis_context or {}).get("deterministic_quality") or {}
        deterministic_quality_passed = bool(deterministic_quality.get("analyzer_available")) and bool(
            deterministic_quality.get("is_good_quality")
        )
        mrz_param = (
            parameter_checks.get("mrz_two_lines_present_and_readable") if isinstance(parameter_checks, dict) else {}
        )
        mrz_param_failed = isinstance(mrz_param, dict) and (mrz_param.get("valid") is False)
        mrz_zone_issue = mrz_param_failed
        raw_failures = self._extract_ordered_failures(decision=decision, parameter_checks=parameter_checks)
        failures = [f for f in raw_failures if not self._is_cutoff_failure(f.get("parameter", ""), f.get("reason", ""))]

        if deterministic_quality_passed and failures:
            failures = [f for f in failures if not self._is_soft_quality_failure(f["parameter"])]

        decision_is_valid = bool(decision.get("is_valid"))
        if not failures and not decision_is_valid:
            had_only_cutoff_failures = bool(raw_failures) and all(
                self._is_cutoff_failure(f.get("parameter", ""), f.get("reason", "")) for f in raw_failures
            )
            if not had_only_cutoff_failures:
                fallback_reason = str(decision.get("summary") or "Validation failed.").strip()
                if not self._is_cutoff_failure("validation_summary", fallback_reason):
                    failures = [{"parameter": "validation_failed", "reason": fallback_reason, "importance": "major"}]

        # Always prioritize MRZ-zone failures over generic page/quality failures.
        if mrz_zone_issue and not any("mrz" in f["parameter"].lower() for f in failures):
            failures.insert(
                0,
                {
                    "parameter": "mrz_zone_complete",
                    "reason": (
                        "MRZ zone is not fully readable. "
                        "Please upload a sharp image where both MRZ lines are clearly readable."
                    ),
                    "importance": "critical",
                },
            )

        if failures:
            rejection_reasons = [f["reason"] for f in failures]
            top_parameter = failures[0]["parameter"]
            return UploadabilityResult(
                is_valid=False,
                method_used="ai",
                model_used=self.ai_parser.model,
                rejection_code=self._map_parameter_to_rejection_code(top_parameter),
                rejection_reason=rejection_reasons[0],
                rejection_reasons=rejection_reasons,
            )

        first_name = self._normalize_name(data.first_name) or None
        last_name = self._normalize_name(data.last_name) or None
        nationality_raw = data.nationality if isinstance(data.nationality, str) else ""
        nationality = nationality_raw.strip().upper() or None
        nationality_code_raw = data.nationality_code if isinstance(data.nationality_code, str) else ""
        nationality_code = nationality_code_raw.strip().upper() or None
        normalized_nationality = nationality_code or nationality
        passport_number = (data.passport_number or "").strip().upper() or None
        confidence_score = float(data.confidence_score or 0)

        # Guardrail 1: confidence threshold must remain enforced to avoid weak-pass false positives.
        if confidence_score < float(self.AI_MIN_CONFIDENCE_FOR_UPLOAD):
            reason = (
                f"AI confidence score ({confidence_score:.2f}) is below the minimum threshold "
                f"({float(self.AI_MIN_CONFIDENCE_FOR_UPLOAD):.2f})."
            )
            return UploadabilityResult(
                is_valid=False,
                method_used="ai",
                model_used=self.ai_parser.model,
                rejection_code="low_confidence",
                rejection_reason=reason,
                rejection_reasons=[reason],
            )

        # Guardrail 2: essential fields must be present.
        if not passport_number or not last_name or not first_name or not normalized_nationality:
            reason = "AI could not extract essential fields (passport number, first name, last name, nationality)."
            return UploadabilityResult(
                is_valid=False,
                method_used="ai",
                model_used=self.ai_parser.model,
                rejection_code="missing_essential_fields",
                rejection_reason=reason,
                rejection_reasons=[reason],
            )

        # Guardrail 3: extracted names and nationality must look sensible.
        if not self._is_name_sensible(first_name) or not self._is_name_sensible(last_name):
            reason = "Extracted name fields look invalid. Please upload a clearer passport image."
            return UploadabilityResult(
                is_valid=False,
                method_used="ai",
                model_used=self.ai_parser.model,
                rejection_code="invalid_name",
                rejection_reason=reason,
                rejection_reasons=[reason],
            )

        if not self._is_nationality_code_sensible(normalized_nationality):
            reason = "Extracted nationality code is invalid. Please upload a clearer passport image."
            return UploadabilityResult(
                is_valid=False,
                method_used="ai",
                model_used=self.ai_parser.model,
                rejection_code="invalid_nationality",
                rejection_reason=reason,
                rejection_reasons=[reason],
            )

        # Guardrail 4: passport number format must pass ICAO sanity checks.
        passport_ok, passport_msg = validate_passport_number_icao(passport_number)
        if not passport_ok:
            reason = f"Extracted passport number is invalid: {passport_msg}"
            return UploadabilityResult(
                is_valid=False,
                method_used="ai",
                model_used=self.ai_parser.model,
                rejection_code="invalid_passport_number",
                rejection_reason=reason,
                rejection_reasons=[reason],
            )

        # Guardrail 5: reject passports expiring within 180 days.
        expiration_date = data.passport_expiration_date
        if expiration_date:
            try:
                exp_date = datetime.strptime(expiration_date, "%Y-%m-%d").date()
                if exp_date < datetime.now().date() + timedelta(days=180):
                    reason = f"Passport expires on {exp_date}, which is less than 180 days from today."
                    return UploadabilityResult(
                        is_valid=False,
                        method_used="ai",
                        model_used=self.ai_parser.model,
                        rejection_code="expiring_soon",
                        rejection_reason=reason,
                        rejection_reasons=[reason],
                    )
            except ValueError:
                reason = "Extracted expiration date is invalid. Please upload a clearer passport image."
                return UploadabilityResult(
                    is_valid=False,
                    method_used="ai",
                    model_used=self.ai_parser.model,
                    rejection_code="invalid_expiration_date",
                    rejection_reason=reason,
                    rejection_reasons=[reason],
                )

        return UploadabilityResult(
            is_valid=True,
            method_used="ai",
            model_used=self.ai_parser.model,
            passport_data={
                "first_name": first_name,
                "last_name": last_name,
                "nationality": normalized_nationality,
                "nationality_code": nationality_code,
                "gender": (data.gender or "").strip().upper() or None,
                "date_of_birth": data.date_of_birth,
                "birth_place": data.birth_place,
                "passport_number": passport_number,
                "passport_issue_date": data.passport_issue_date,
                "expiration_date": expiration_date,
                "address_abroad": data.address_abroad,
                "confidence_score": confidence_score,
            },
        )
