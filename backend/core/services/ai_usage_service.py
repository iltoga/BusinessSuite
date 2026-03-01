from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from core.services.logger_service import Logger
from django.apps import apps

logger = Logger.get_logger(__name__)


class AIUsageFeature:
    INVOICE_IMPORT_AI_PARSER = "Invoice Import AI Parser"
    PASSPORT_OCR_AI_EXTRACTOR = "Passport OCR AI Extractor"
    PASSPORT_CHECK_API = "Passport Check API"
    DOCUMENT_AI_CATEGORIZER = "Document AI Categorizer"
    DOCUMENT_AI_VALIDATOR = "Document AI Validator"
    UNKNOWN = "Unclassified AI Feature"


class AIUsageService:
    """Centralized, fail-safe usage accounting writer for AI requests."""

    @staticmethod
    def _read(source: Any, key: str, default: Any = None) -> Any:
        if source is None:
            return default
        if isinstance(source, dict):
            return source.get(key, default)
        return getattr(source, key, default)

    @classmethod
    def _to_int(cls, value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _to_decimal(cls, value: Any) -> Decimal | None:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (TypeError, ValueError, InvalidOperation):
            return None

    @classmethod
    def _extract_usage(cls, response: Any) -> dict[str, Any]:
        usage = cls._read(response, "usage")
        if usage is None:
            return {}

        prompt_details = cls._read(usage, "prompt_tokens_details", {}) or {}
        completion_details = cls._read(usage, "completion_tokens_details", {}) or {}

        return {
            "prompt_tokens": cls._to_int(cls._read(usage, "prompt_tokens")),
            "completion_tokens": cls._to_int(cls._read(usage, "completion_tokens")),
            "total_tokens": cls._to_int(cls._read(usage, "total_tokens")),
            "cached_prompt_tokens": cls._to_int(cls._read(prompt_details, "cached_tokens")),
            "cache_write_tokens": cls._to_int(cls._read(prompt_details, "cache_write_tokens")),
            "reasoning_tokens": cls._to_int(cls._read(completion_details, "reasoning_tokens")),
            "cost_usd": cls._to_decimal(cls._read(usage, "cost")),
        }

    @classmethod
    def enqueue_request_capture(
        cls,
        *,
        feature: str,
        provider: str,
        model: str,
        response: Any = None,
        request_type: str = "chat.completions",
        success: bool = True,
        error_type: str = "",
        latency_ms: int | None = None,
    ) -> None:
        request_id = cls._read(response, "id") if response is not None else None
        usage_data = cls._extract_usage(response) if response is not None else {}
        try:
            from core.tasks.ai_usage import enqueue_capture_ai_usage_task

            enqueue_capture_ai_usage_task(
                feature=feature or AIUsageFeature.UNKNOWN,
                provider=provider or "unknown",
                model=model or "unknown",
                request_type=request_type,
                request_id=request_id or None,
                usage_data=usage_data or None,
                success=success,
                error_type=error_type or "",
                latency_ms=latency_ms,
            )
        except Exception as exc:
            logger.warning("Failed to enqueue AI usage capture task: %s", str(exc))

    @classmethod
    def record_request(
        cls,
        *,
        feature: str,
        provider: str,
        model: str,
        response: Any = None,
        request_id: str | None = None,
        usage_data: dict[str, Any] | None = None,
        request_type: str = "chat.completions",
        success: bool = True,
        error_type: str = "",
        latency_ms: int | None = None,
    ) -> None:
        normalized_usage_data: dict[str, Any]
        if usage_data is not None:
            normalized_usage_data = {
                "prompt_tokens": cls._to_int(usage_data.get("prompt_tokens")),
                "completion_tokens": cls._to_int(usage_data.get("completion_tokens")),
                "total_tokens": cls._to_int(usage_data.get("total_tokens")),
                "cached_prompt_tokens": cls._to_int(usage_data.get("cached_prompt_tokens")),
                "cache_write_tokens": cls._to_int(usage_data.get("cache_write_tokens")),
                "reasoning_tokens": cls._to_int(usage_data.get("reasoning_tokens")),
                "cost_usd": cls._to_decimal(usage_data.get("cost_usd")),
            }
        elif response is not None:
            normalized_usage_data = cls._extract_usage(response)
        else:
            normalized_usage_data = {}

        if request_id is None and response is not None:
            request_id = cls._read(response, "id")

        try:
            ai_request_usage_model = apps.get_model("core", "AIRequestUsage")
            ai_request_usage_model.objects.create(
                feature=feature or AIUsageFeature.UNKNOWN,
                provider=provider or "unknown",
                model=model or "unknown",
                request_type=request_type,
                request_id=request_id or None,
                success=success,
                error_type=error_type or "",
                latency_ms=latency_ms,
                **normalized_usage_data,
            )
        except Exception as exc:
            logger.warning("Failed to persist AI request usage record: %s", str(exc))
