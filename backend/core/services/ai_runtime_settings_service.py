"""
FILE_ROLE: Service-layer logic for the core app.

KEY_COMPONENTS:
- RuntimeSettingDefinition: Module symbol.
- FallbackModelChainStep: Module symbol.
- AIRuntimeSettingsService: Service class.

INTERACTIONS:
- Depends on: nearby Django models, services, serializers, and the app packages imported by this module.

AI_GUIDELINES:
- Keep the module focused on its narrow layer boundary and avoid moving cross-cutting workflow code here.
- Preserve the existing API/model contract because other modules import these symbols directly.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse, urlunparse

from core.models import AiModel
from core.services.ai_usage_service import AIUsageFeature
from core.services.app_setting_service import AppSettingScope, AppSettingService
from django.conf import settings

logger = logging.getLogger(__name__)
_OPENROUTER_ALLOWED_BASE_URL_HOSTS = {"openrouter.ai", "api.openrouter.ai"}
_OPENROUTER_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass(frozen=True)
class RuntimeSettingDefinition:
    name: str
    value_type: str
    scope: str
    description: str


@dataclass(frozen=True)
class FallbackModelChainStep:
    provider: str
    model: str
    timeout_seconds: float


AI_RUNTIME_SETTING_DEFINITIONS: dict[str, RuntimeSettingDefinition] = {
    "LLM_PROVIDER": RuntimeSettingDefinition(
        name="LLM_PROVIDER",
        value_type="string",
        scope=AppSettingScope.BACKEND,
        description="Primary LLM provider.",
    ),
    "LLM_DEFAULT_MODEL": RuntimeSettingDefinition(
        name="LLM_DEFAULT_MODEL",
        value_type="string",
        scope=AppSettingScope.BACKEND,
        description="Global default model for non-groq providers.",
    ),
    "GROQ_DEFAULT_MODEL": RuntimeSettingDefinition(
        name="GROQ_DEFAULT_MODEL",
        value_type="string",
        scope=AppSettingScope.BACKEND,
        description="Default model used when provider is Groq.",
    ),
    "OPENROUTER_DEFAULT_MODEL": RuntimeSettingDefinition(
        name="OPENROUTER_DEFAULT_MODEL",
        value_type="string",
        scope=AppSettingScope.BACKEND,
        description="Provider-specific default model for OpenRouter.",
    ),
    "OPENAI_DEFAULT_MODEL": RuntimeSettingDefinition(
        name="OPENAI_DEFAULT_MODEL",
        value_type="string",
        scope=AppSettingScope.BACKEND,
        description="Provider-specific default model for OpenAI direct API.",
    ),
    "INVOICE_IMPORT_MODEL": RuntimeSettingDefinition(
        name="INVOICE_IMPORT_MODEL",
        value_type="string",
        scope=AppSettingScope.BACKEND,
        description="Workflow-specific model for invoice import AI parser.",
    ),
    "PASSPORT_OCR_MODEL": RuntimeSettingDefinition(
        name="PASSPORT_OCR_MODEL",
        value_type="string",
        scope=AppSettingScope.BACKEND,
        description="Workflow-specific model for passport OCR AI extractor.",
    ),
    "DOCUMENT_CATEGORIZER_MODEL": RuntimeSettingDefinition(
        name="DOCUMENT_CATEGORIZER_MODEL",
        value_type="string",
        scope=AppSettingScope.BACKEND,
        description="Primary model for document categorization pass-1.",
    ),
    "DOCUMENT_CATEGORIZER_MODEL_HIGH": RuntimeSettingDefinition(
        name="DOCUMENT_CATEGORIZER_MODEL_HIGH",
        value_type="string",
        scope=AppSettingScope.BACKEND,
        description="Fallback model for document categorization pass-2.",
    ),
    "DOCUMENT_VALIDATOR_MODEL": RuntimeSettingDefinition(
        name="DOCUMENT_VALIDATOR_MODEL",
        value_type="string",
        scope=AppSettingScope.BACKEND,
        description="Model for document validation rules.",
    ),
    "DOCUMENT_OCR_STRUCTURED_MODEL": RuntimeSettingDefinition(
        name="DOCUMENT_OCR_STRUCTURED_MODEL",
        value_type="string",
        scope=AppSettingScope.BACKEND,
        description="Model for structured OCR extraction.",
    ),
    "CHECK_PASSPORT_MODEL": RuntimeSettingDefinition(
        name="CHECK_PASSPORT_MODEL",
        value_type="string",
        scope=AppSettingScope.BACKEND,
        description="Model for passport uploadability checks.",
    ),
    "CHECK_PASSPORT_AI_MIN_CONFIDENCE_FOR_UPLOAD": RuntimeSettingDefinition(
        name="CHECK_PASSPORT_AI_MIN_CONFIDENCE_FOR_UPLOAD",
        value_type="float",
        scope=AppSettingScope.BACKEND,
        description="Minimum AI confidence threshold for passport uploadability acceptance.",
    ),
    "INVOICE_IMPORT_TIMEOUT": RuntimeSettingDefinition(
        name="INVOICE_IMPORT_TIMEOUT",
        value_type="float",
        scope=AppSettingScope.BACKEND,
        description="Primary-attempt timeout in seconds for invoice import AI parser requests.",
    ),
    "PASSPORT_OCR_TIMEOUT": RuntimeSettingDefinition(
        name="PASSPORT_OCR_TIMEOUT",
        value_type="float",
        scope=AppSettingScope.BACKEND,
        description="Primary-attempt timeout in seconds for passport OCR AI extractor requests.",
    ),
    "DOCUMENT_CATEGORIZATION_TIMEOUT": RuntimeSettingDefinition(
        name="DOCUMENT_CATEGORIZATION_TIMEOUT",
        value_type="float",
        scope=AppSettingScope.BACKEND,
        description="Primary-attempt timeout in seconds for document categorization AI requests.",
    ),
    "DOCUMENT_VALIDATION_TIMEOUT": RuntimeSettingDefinition(
        name="DOCUMENT_VALIDATION_TIMEOUT",
        value_type="float",
        scope=AppSettingScope.BACKEND,
        description="Primary-attempt timeout in seconds for document validation AI requests.",
    ),
    "DOCUMENT_OCR_TIMEOUT": RuntimeSettingDefinition(
        name="DOCUMENT_OCR_TIMEOUT",
        value_type="float",
        scope=AppSettingScope.BACKEND,
        description="Primary-attempt timeout in seconds for document OCR structured extraction AI requests.",
    ),
    "PASSPORT_CHECK_TIMEOUT": RuntimeSettingDefinition(
        name="PASSPORT_CHECK_TIMEOUT",
        value_type="float",
        scope=AppSettingScope.BACKEND,
        description="Primary-attempt timeout in seconds for passport check AI requests.",
    ),
    "LLM_AUTO_FALLBACK_ENABLED": RuntimeSettingDefinition(
        name="LLM_AUTO_FALLBACK_ENABLED",
        value_type="bool",
        scope=AppSettingScope.BACKEND,
        description="Enable automatic provider failover on retriable errors.",
    ),
    "LLM_FALLBACK_PROVIDER_ORDER": RuntimeSettingDefinition(
        name="LLM_FALLBACK_PROVIDER_ORDER",
        value_type="list",
        scope=AppSettingScope.BACKEND,
        description="Comma-separated provider order used for failover.",
    ),
    "LLM_FALLBACK_MODEL_ORDER": RuntimeSettingDefinition(
        name="LLM_FALLBACK_MODEL_ORDER",
        value_type="list",
        scope=AppSettingScope.BACKEND,
        description="Comma-separated model order used for failover retries.",
    ),
    "LLM_FALLBACK_MODEL_CHAIN": RuntimeSettingDefinition(
        name="LLM_FALLBACK_MODEL_CHAIN",
        value_type="json",
        scope=AppSettingScope.BACKEND,
        description="Ordered failover chain with per-model timeout settings.",
    ),
    "LLM_FALLBACK_STICKY_SECONDS": RuntimeSettingDefinition(
        name="LLM_FALLBACK_STICKY_SECONDS",
        value_type="int",
        scope=AppSettingScope.BACKEND,
        description="Sticky failover provider TTL in seconds.",
    ),
    "LLM_FALLBACK_STICKY_CACHE_KEY": RuntimeSettingDefinition(
        name="LLM_FALLBACK_STICKY_CACHE_KEY",
        value_type="string",
        scope=AppSettingScope.BACKEND,
        description="Cache key used to persist sticky failover provider.",
    ),
    "OPENROUTER_API_BASE_URL": RuntimeSettingDefinition(
        name="OPENROUTER_API_BASE_URL",
        value_type="string",
        scope=AppSettingScope.BACKEND,
        description="OpenRouter API base URL.",
    ),
    "OPENROUTER_PROVIDER_SORTING_PRIORITY": RuntimeSettingDefinition(
        name="OPENROUTER_PROVIDER_SORTING_PRIORITY",
        value_type="string",
        scope=AppSettingScope.BACKEND,
        description="Sorting priority for OpenRouter providers (price, throughput, latency).",
    ),
    "OPENROUTER_TIMEOUT": RuntimeSettingDefinition(
        name="OPENROUTER_TIMEOUT",
        value_type="float",
        scope=AppSettingScope.BACKEND,
        description="OpenRouter API timeout in seconds.",
    ),
    "OPENAI_TIMEOUT": RuntimeSettingDefinition(
        name="OPENAI_TIMEOUT",
        value_type="float",
        scope=AppSettingScope.BACKEND,
        description="OpenAI API timeout in seconds.",
    ),
    "DRAMATIQ_REDIS_URL": RuntimeSettingDefinition(
        name="DRAMATIQ_REDIS_URL",
        value_type="string",
        scope=AppSettingScope.BACKEND,
        description="Optional Redis URL override for Dramatiq broker.",
    ),
    "REDIS_URL": RuntimeSettingDefinition(
        name="REDIS_URL",
        value_type="string",
        scope=AppSettingScope.BACKEND,
        description="Fallback Redis URL used by Dramatiq when DRAMATIQ_REDIS_URL is empty.",
    ),
    "REDIS_HOST": RuntimeSettingDefinition(
        name="REDIS_HOST",
        value_type="string",
        scope=AppSettingScope.BACKEND,
        description="Fallback Redis host used by Dramatiq when URL settings are empty.",
    ),
    "REDIS_PORT": RuntimeSettingDefinition(
        name="REDIS_PORT",
        value_type="int",
        scope=AppSettingScope.BACKEND,
        description="Fallback Redis port used by Dramatiq when URL settings are empty.",
    ),
    "DRAMATIQ_REDIS_DB": RuntimeSettingDefinition(
        name="DRAMATIQ_REDIS_DB",
        value_type="int",
        scope=AppSettingScope.BACKEND,
        description="Redis DB index used by Dramatiq queues.",
    ),
    "DRAMATIQ_NAMESPACE": RuntimeSettingDefinition(
        name="DRAMATIQ_NAMESPACE",
        value_type="string",
        scope=AppSettingScope.BACKEND,
        description="Dramatiq queue namespace.",
    ),
    "DRAMATIQ_RESULTS_ENABLED": RuntimeSettingDefinition(
        name="DRAMATIQ_RESULTS_ENABLED",
        value_type="bool",
        scope=AppSettingScope.BACKEND,
        description="Enable Dramatiq results middleware.",
    ),
    "DRAMATIQ_RESULTS_STORE_RESULTS": RuntimeSettingDefinition(
        name="DRAMATIQ_RESULTS_STORE_RESULTS",
        value_type="bool",
        scope=AppSettingScope.BACKEND,
        description="Enable result persistence in Dramatiq results backend.",
    ),
    "DRAMATIQ_RESULTS_TTL_MS": RuntimeSettingDefinition(
        name="DRAMATIQ_RESULTS_TTL_MS",
        value_type="int",
        scope=AppSettingScope.BACKEND,
        description="Dramatiq result TTL in milliseconds.",
    ),
    "DRAMATIQ_RESULTS_NAMESPACE": RuntimeSettingDefinition(
        name="DRAMATIQ_RESULTS_NAMESPACE",
        value_type="string",
        scope=AppSettingScope.BACKEND,
        description="Dramatiq results namespace.",
    ),
    "DRAMATIQ_RESULTS_REDIS_URL": RuntimeSettingDefinition(
        name="DRAMATIQ_RESULTS_REDIS_URL",
        value_type="string",
        scope=AppSettingScope.BACKEND,
        description="Optional dedicated Redis URL for Dramatiq results backend.",
    ),
    "AUDIT_ENABLED": RuntimeSettingDefinition(
        name="AUDIT_ENABLED",
        value_type="bool",
        scope=AppSettingScope.BACKEND,
        description="Enable audit logging features.",
    ),
    "AUDIT_WATCH_AUTH_EVENTS": RuntimeSettingDefinition(
        name="AUDIT_WATCH_AUTH_EVENTS",
        value_type="bool",
        scope=AppSettingScope.BACKEND,
        description="Capture authentication events in audit logs.",
    ),
    "AUDIT_FORWARD_TO_LOKI": RuntimeSettingDefinition(
        name="AUDIT_FORWARD_TO_LOKI",
        value_type="bool",
        scope=AppSettingScope.BACKEND,
        description="Forward audit events to Loki sink.",
    ),
    "AUDITLOG_RETENTION_DAYS": RuntimeSettingDefinition(
        name="AUDITLOG_RETENTION_DAYS",
        value_type="int",
        scope=AppSettingScope.BACKEND,
        description="Retention period (days) for audit logs.",
    ),
    "AUDITLOG_RETENTION_SCHEDULE": RuntimeSettingDefinition(
        name="AUDITLOG_RETENTION_SCHEDULE",
        value_type="string",
        scope=AppSettingScope.BACKEND,
        description="Daily cron time (HH:MM) to prune audit logs.",
    ),
    "DJANGO_LOG_LEVEL": RuntimeSettingDefinition(
        name="DJANGO_LOG_LEVEL",
        value_type="string",
        scope=AppSettingScope.BACKEND,
        description="Django log level.",
    ),
    "DJANGO_DEBUG": RuntimeSettingDefinition(
        name="DJANGO_DEBUG",
        value_type="bool",
        scope=AppSettingScope.BACKEND,
        description="Enable Django debug mode.",
    ),
    "DISABLE_DJANGO_VIEWS": RuntimeSettingDefinition(
        name="DISABLE_DJANGO_VIEWS",
        value_type="bool",
        scope=AppSettingScope.BACKEND,
        description="Disable Django server-rendered views.",
    ),
    "MOCK_AUTH_ENABLED": RuntimeSettingDefinition(
        name="MOCK_AUTH_ENABLED",
        value_type="bool",
        scope=AppSettingScope.BOTH,
        description="Enable mock authentication paths.",
    ),
    "INVOICE_IMPORT_MAX_WORKERS": RuntimeSettingDefinition(
        name="INVOICE_IMPORT_MAX_WORKERS",
        value_type="int",
        scope=AppSettingScope.BACKEND,
        description="Maximum parallel workers for invoice import.",
    ),
    "DATE_FORMAT_JS": RuntimeSettingDefinition(
        name="DATE_FORMAT_JS",
        value_type="string",
        scope=AppSettingScope.BOTH,
        description="Frontend date format string.",
    ),
    "BASE_CURRENCY": RuntimeSettingDefinition(
        name="BASE_CURRENCY",
        value_type="string",
        scope=AppSettingScope.BOTH,
        description="Default base currency code.",
    ),
    "DEFAULT_DOCUMENT_LANGUAGE_CODE": RuntimeSettingDefinition(
        name="DEFAULT_DOCUMENT_LANGUAGE_CODE",
        value_type="string",
        scope=AppSettingScope.BOTH,
        description="Default document language code.",
    ),
    "DEFAULT_CUSTOMER_EMAIL": RuntimeSettingDefinition(
        name="DEFAULT_CUSTOMER_EMAIL",
        value_type="string",
        scope=AppSettingScope.BOTH,
        description="Default customer email fallback.",
    ),
    "GOOGLE_TIMEZONE": RuntimeSettingDefinition(
        name="GOOGLE_TIMEZONE",
        value_type="string",
        scope=AppSettingScope.BACKEND,
        description="Google integration timezone.",
    ),
    "GOOGLE_CALENDAR_ID": RuntimeSettingDefinition(
        name="GOOGLE_CALENDAR_ID",
        value_type="string",
        scope=AppSettingScope.BACKEND,
        description="Google Calendar ID.",
    ),
    "GOOGLE_TASKLIST_ID": RuntimeSettingDefinition(
        name="GOOGLE_TASKLIST_ID",
        value_type="string",
        scope=AppSettingScope.BACKEND,
        description="Google Tasklist ID.",
    ),
    "USE_CLOUD_STORAGE": RuntimeSettingDefinition(
        name="USE_CLOUD_STORAGE",
        value_type="bool",
        scope=AppSettingScope.BACKEND,
        description="Enable cloud storage backends.",
    ),
}

_WORKFLOW_BINDINGS = [
    {
        "feature": AIUsageFeature.INVOICE_IMPORT_AI_PARSER,
        "providerSettingName": "LLM_PROVIDER",
        "modelSettingName": "INVOICE_IMPORT_MODEL",
        "modelFailoverSettingName": None,
        "timeoutSettingName": "INVOICE_IMPORT_TIMEOUT",
    },
    {
        "feature": AIUsageFeature.PASSPORT_OCR_AI_EXTRACTOR,
        "providerSettingName": "LLM_PROVIDER",
        "modelSettingName": "PASSPORT_OCR_MODEL",
        "modelFailoverSettingName": None,
        "timeoutSettingName": "PASSPORT_OCR_TIMEOUT",
    },
    {
        "feature": AIUsageFeature.DOCUMENT_AI_CATEGORIZER,
        "providerSettingName": "LLM_PROVIDER",
        "modelSettingName": "DOCUMENT_CATEGORIZER_MODEL",
        "modelFailoverSettingName": "DOCUMENT_CATEGORIZER_MODEL_HIGH",
        "timeoutSettingName": "DOCUMENT_CATEGORIZATION_TIMEOUT",
    },
    {
        "feature": AIUsageFeature.DOCUMENT_AI_VALIDATOR,
        "providerSettingName": "LLM_PROVIDER",
        "modelSettingName": "DOCUMENT_VALIDATOR_MODEL",
        "modelFailoverSettingName": None,
        "timeoutSettingName": "DOCUMENT_VALIDATION_TIMEOUT",
    },
    {
        "feature": AIUsageFeature.DOCUMENT_OCR_AI_EXTRACTOR,
        "providerSettingName": "LLM_PROVIDER",
        "modelSettingName": "DOCUMENT_OCR_STRUCTURED_MODEL",
        "modelFailoverSettingName": None,
        "timeoutSettingName": "DOCUMENT_OCR_TIMEOUT",
    },
    {
        "feature": AIUsageFeature.PASSPORT_CHECK_API,
        "providerSettingName": "LLM_PROVIDER",
        "modelSettingName": "CHECK_PASSPORT_MODEL",
        "modelFailoverSettingName": None,
        "timeoutSettingName": "PASSPORT_CHECK_TIMEOUT",
    },
]

_MODEL_SETTING_KEYS = {
    "LLM_DEFAULT_MODEL",
    "GROQ_DEFAULT_MODEL",
    "OPENROUTER_DEFAULT_MODEL",
    "OPENAI_DEFAULT_MODEL",
    "INVOICE_IMPORT_MODEL",
    "PASSPORT_OCR_MODEL",
    "DOCUMENT_CATEGORIZER_MODEL",
    "DOCUMENT_CATEGORIZER_MODEL_HIGH",
    "DOCUMENT_VALIDATOR_MODEL",
    "DOCUMENT_OCR_STRUCTURED_MODEL",
    "CHECK_PASSPORT_MODEL",
}

_PROVIDER_OPTIONS = {"openrouter", "openai", "groq"}
_PROVIDER_PRIORITY = ("openrouter", "openai", "groq")
_WORKFLOW_TIMEOUT_DEFAULTS = {
    "INVOICE_IMPORT_TIMEOUT": 120.0,
    "PASSPORT_OCR_TIMEOUT": 120.0,
    "DOCUMENT_CATEGORIZATION_TIMEOUT": 30.0,
    "DOCUMENT_VALIDATION_TIMEOUT": 30.0,
    "DOCUMENT_OCR_TIMEOUT": 120.0,
    "PASSPORT_CHECK_TIMEOUT": 120.0,
}
_TIMEOUT_SETTING_KEYS = set(_WORKFLOW_TIMEOUT_DEFAULTS)
_TIMEOUT_SETTING_BY_FEATURE = {
    str(binding["feature"]): str(binding["timeoutSettingName"])
    for binding in _WORKFLOW_BINDINGS
    if binding.get("timeoutSettingName")
}


class AIRuntimeSettingsService:
    @staticmethod
    def _default_from_settings_and_env(name: str, hardcoded_default: Any) -> Any:
        value = hardcoded_default
        if hasattr(settings, name):
            configured_value = getattr(settings, name)
            if configured_value is not None:
                value = configured_value
        env_value = os.getenv(name)
        if env_value is not None and str(env_value).strip() != "":
            return env_value
        return value

    @classmethod
    def _provider_timeout_default(cls, provider: str) -> float:
        normalized_provider = str(provider or "").strip().lower()
        if normalized_provider == "openrouter":
            return float(cls._default_from_settings_and_env("OPENROUTER_TIMEOUT", 120.0))
        if normalized_provider == "openai":
            return float(cls._default_from_settings_and_env("OPENAI_TIMEOUT", 120.0))
        if normalized_provider == "groq":
            return float(cls._default_from_settings_and_env("GROQ_TIMEOUT", 120.0))
        return 120.0

    @classmethod
    def _normalize_openrouter_api_base_url(cls, raw_value: Any, *, strict: bool) -> str:
        candidate = str(raw_value or "").strip()
        if not candidate:
            return _OPENROUTER_DEFAULT_BASE_URL

        parsed = urlparse(candidate)
        host = str(parsed.hostname or "").strip().lower()
        is_allowed_host = host in _OPENROUTER_ALLOWED_BASE_URL_HOSTS or host.endswith(".openrouter.ai")
        port = parsed.port

        invalid_reason = None
        if parsed.scheme.lower() != "https":
            invalid_reason = "must use https"
        elif parsed.username or parsed.password:
            invalid_reason = "must not include embedded credentials"
        elif not host:
            invalid_reason = "must include a hostname"
        elif not is_allowed_host:
            invalid_reason = "must target an allowed OpenRouter hostname"
        elif port not in {None, 443}:
            invalid_reason = "must not use a custom port"

        if invalid_reason:
            if strict:
                raise ValueError(
                    "OPENROUTER_API_BASE_URL "
                    f"{invalid_reason}. Allowed hosts: {sorted(_OPENROUTER_ALLOWED_BASE_URL_HOSTS)}"
                )
            logger.warning("Ignoring unsafe OPENROUTER_API_BASE_URL value %r; using default.", candidate)
            return _OPENROUTER_DEFAULT_BASE_URL

        normalized_path = (parsed.path or "").rstrip("/") or "/api/v1"
        if normalized_path == "/":
            normalized_path = "/api/v1"
        return urlunparse(("https", host, normalized_path, "", "", ""))

    @classmethod
    def _normalize_fallback_model_chain(
        cls,
        raw_value: Any,
        *,
        strict: bool = False,
    ) -> list[dict[str, Any]]:
        parsed = AppSettingService.parse_json_like(raw_value)
        if isinstance(parsed, dict):
            parsed = parsed.get("steps") or parsed.get("items") or []
        if isinstance(parsed, str):
            parsed = AppSettingService.parse_list(parsed, [])
        if not isinstance(parsed, (list, tuple)):
            parsed = []

        model_ids = cls._all_model_ids()
        normalized_steps: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        for raw_step in parsed:
            if isinstance(raw_step, str):
                step_model = raw_step.strip()
                raw_timeout = None
            elif isinstance(raw_step, dict):
                step_model = str(
                    raw_step.get("model")
                    or raw_step.get("model_id")
                    or raw_step.get("modelId")
                    or raw_step.get("value")
                    or ""
                ).strip()
                raw_timeout = (
                    raw_step.get("timeoutSeconds") or raw_step.get("timeout_seconds") or raw_step.get("timeout")
                )
            else:
                if strict:
                    raise ValueError("LLM_FALLBACK_MODEL_CHAIN entries must be strings or objects.")
                continue

            if not step_model:
                if strict:
                    raise ValueError("LLM_FALLBACK_MODEL_CHAIN entries must include a model.")
                continue
            if step_model not in model_ids:
                if strict:
                    raise ValueError(f"LLM_FALLBACK_MODEL_CHAIN contains unknown model '{step_model}'.")
                continue

            provider = cls.get_provider_for_model(step_model)
            if not provider:
                if strict:
                    raise ValueError(f"Unable to resolve provider for fallback model '{step_model}'.")
                continue

            default_timeout = cls._provider_timeout_default(provider)
            if raw_timeout in (None, ""):
                timeout_seconds = default_timeout
            else:
                try:
                    timeout_seconds = float(raw_timeout)
                except (TypeError, ValueError):
                    if strict:
                        raise ValueError(
                            f"Fallback timeout for model '{step_model}' must be a positive number."
                        ) from None
                    timeout_seconds = default_timeout
            if timeout_seconds <= 0:
                if strict:
                    raise ValueError(f"Fallback timeout for model '{step_model}' must be greater than zero.")
                timeout_seconds = default_timeout

            dedupe_key = (provider, step_model)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            normalized_steps.append(
                {
                    "model": step_model,
                    "timeoutSeconds": timeout_seconds,
                }
            )

        return normalized_steps

    @classmethod
    def _fallback_chain_from_model_order(cls, model_ids: list[str]) -> list[dict[str, Any]]:
        return cls._normalize_fallback_model_chain(model_ids, strict=False)

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        llm_provider = (
            str(cls._default_from_settings_and_env("LLM_PROVIDER", "openrouter") or "openrouter").strip().lower()
        )
        llm_default_model = (
            str(
                cls._default_from_settings_and_env(
                    "LLM_DEFAULT_MODEL",
                    "google/gemini-3-flash-preview",
                )
                or ""
            ).strip()
            or "google/gemini-3-flash-preview"
        )
        groq_default_model = (
            str(
                cls._default_from_settings_and_env(
                    "GROQ_DEFAULT_MODEL",
                    "meta-llama/llama-4-scout-17b-16e-instruct",
                )
                or ""
            ).strip()
            or "meta-llama/llama-4-scout-17b-16e-instruct"
        )
        fallback_model_order = AppSettingService.parse_list(
            cls._default_from_settings_and_env("LLM_FALLBACK_MODEL_ORDER", []),
            [],
        )
        raw_fallback_chain = cls._default_from_settings_and_env("LLM_FALLBACK_MODEL_CHAIN", None)
        fallback_model_chain = (
            cls._normalize_fallback_model_chain(raw_fallback_chain, strict=False)
            if raw_fallback_chain not in (None, "")
            else cls._fallback_chain_from_model_order(fallback_model_order)
        )
        fallback_model_order = [step["model"] for step in fallback_model_chain] or fallback_model_order
        return {
            "LLM_PROVIDER": llm_provider,
            "LLM_DEFAULT_MODEL": llm_default_model,
            "GROQ_DEFAULT_MODEL": groq_default_model,
            "OPENROUTER_DEFAULT_MODEL": (
                str(cls._default_from_settings_and_env("OPENROUTER_DEFAULT_MODEL", llm_default_model) or "").strip()
                or llm_default_model
            ),
            "OPENROUTER_PROVIDER_SORTING_PRIORITY": (
                str(cls._default_from_settings_and_env("OPENROUTER_PROVIDER_SORTING_PRIORITY", "price") or "").strip()
                or "price"
            ),
            "OPENAI_DEFAULT_MODEL": (
                str(cls._default_from_settings_and_env("OPENAI_DEFAULT_MODEL", "gpt-5-mini") or "").strip()
                or "gpt-5-mini"
            ),
            "INVOICE_IMPORT_MODEL": str(cls._default_from_settings_and_env("INVOICE_IMPORT_MODEL", "") or "").strip(),
            "PASSPORT_OCR_MODEL": str(cls._default_from_settings_and_env("PASSPORT_OCR_MODEL", "") or "").strip(),
            "DOCUMENT_CATEGORIZER_MODEL": str(
                cls._default_from_settings_and_env("DOCUMENT_CATEGORIZER_MODEL", "") or ""
            ).strip(),
            "DOCUMENT_CATEGORIZER_MODEL_HIGH": str(
                cls._default_from_settings_and_env("DOCUMENT_CATEGORIZER_MODEL_HIGH", "") or ""
            ).strip(),
            "DOCUMENT_VALIDATOR_MODEL": str(
                cls._default_from_settings_and_env("DOCUMENT_VALIDATOR_MODEL", "") or ""
            ).strip(),
            "DOCUMENT_OCR_STRUCTURED_MODEL": str(
                cls._default_from_settings_and_env("DOCUMENT_OCR_STRUCTURED_MODEL", "") or ""
            ).strip(),
            "CHECK_PASSPORT_MODEL": str(cls._default_from_settings_and_env("CHECK_PASSPORT_MODEL", "") or "").strip(),
            "CHECK_PASSPORT_AI_MIN_CONFIDENCE_FOR_UPLOAD": float(
                cls._default_from_settings_and_env("CHECK_PASSPORT_AI_MIN_CONFIDENCE_FOR_UPLOAD", 0.95)
            ),
            "INVOICE_IMPORT_TIMEOUT": float(
                cls._default_from_settings_and_env(
                    "INVOICE_IMPORT_TIMEOUT",
                    _WORKFLOW_TIMEOUT_DEFAULTS["INVOICE_IMPORT_TIMEOUT"],
                )
            ),
            "PASSPORT_OCR_TIMEOUT": float(
                cls._default_from_settings_and_env(
                    "PASSPORT_OCR_TIMEOUT",
                    _WORKFLOW_TIMEOUT_DEFAULTS["PASSPORT_OCR_TIMEOUT"],
                )
            ),
            "DOCUMENT_CATEGORIZATION_TIMEOUT": float(
                cls._default_from_settings_and_env(
                    "DOCUMENT_CATEGORIZATION_TIMEOUT",
                    _WORKFLOW_TIMEOUT_DEFAULTS["DOCUMENT_CATEGORIZATION_TIMEOUT"],
                )
            ),
            "DOCUMENT_VALIDATION_TIMEOUT": float(
                cls._default_from_settings_and_env(
                    "DOCUMENT_VALIDATION_TIMEOUT",
                    _WORKFLOW_TIMEOUT_DEFAULTS["DOCUMENT_VALIDATION_TIMEOUT"],
                )
            ),
            "DOCUMENT_OCR_TIMEOUT": float(
                cls._default_from_settings_and_env(
                    "DOCUMENT_OCR_TIMEOUT",
                    _WORKFLOW_TIMEOUT_DEFAULTS["DOCUMENT_OCR_TIMEOUT"],
                )
            ),
            "PASSPORT_CHECK_TIMEOUT": float(
                cls._default_from_settings_and_env(
                    "PASSPORT_CHECK_TIMEOUT",
                    _WORKFLOW_TIMEOUT_DEFAULTS["PASSPORT_CHECK_TIMEOUT"],
                )
            ),
            "LLM_AUTO_FALLBACK_ENABLED": AppSettingService.parse_bool(
                cls._default_from_settings_and_env("LLM_AUTO_FALLBACK_ENABLED", True),
                True,
            ),
            "LLM_FALLBACK_PROVIDER_ORDER": AppSettingService.parse_list(
                cls._default_from_settings_and_env("LLM_FALLBACK_PROVIDER_ORDER", []),
                [],
            ),
            "LLM_FALLBACK_MODEL_ORDER": fallback_model_order,
            "LLM_FALLBACK_MODEL_CHAIN": fallback_model_chain,
            "LLM_FALLBACK_STICKY_SECONDS": int(cls._default_from_settings_and_env("LLM_FALLBACK_STICKY_SECONDS", 3600)),
            "LLM_FALLBACK_STICKY_CACHE_KEY": (
                str(
                    cls._default_from_settings_and_env(
                        "LLM_FALLBACK_STICKY_CACHE_KEY",
                        "ai:router:sticky_provider",
                    )
                    or ""
                ).strip()
                or "ai:router:sticky_provider"
            ),
            "OPENROUTER_API_BASE_URL": (
                cls._normalize_openrouter_api_base_url(
                    cls._default_from_settings_and_env(
                        "OPENROUTER_API_BASE_URL",
                        _OPENROUTER_DEFAULT_BASE_URL,
                    ),
                    strict=False,
                )
            ),
            "OPENROUTER_TIMEOUT": float(cls._default_from_settings_and_env("OPENROUTER_TIMEOUT", 120.0)),
            "OPENAI_TIMEOUT": float(cls._default_from_settings_and_env("OPENAI_TIMEOUT", 120.0)),
            "DRAMATIQ_REDIS_URL": str(cls._default_from_settings_and_env("DRAMATIQ_REDIS_URL", "") or "").strip(),
            "REDIS_URL": str(cls._default_from_settings_and_env("REDIS_URL", "") or "").strip(),
            "REDIS_HOST": str(cls._default_from_settings_and_env("REDIS_HOST", "") or "").strip(),
            "REDIS_PORT": int(cls._default_from_settings_and_env("REDIS_PORT", 6379)),
            "DRAMATIQ_REDIS_DB": int(cls._default_from_settings_and_env("DRAMATIQ_REDIS_DB", 0)),
            "DRAMATIQ_NAMESPACE": str(
                cls._default_from_settings_and_env("DRAMATIQ_NAMESPACE", "dramatiq:queue") or "dramatiq:queue"
            ).strip()
            or "dramatiq:queue",
            "DRAMATIQ_RESULTS_ENABLED": AppSettingService.parse_bool(
                cls._default_from_settings_and_env("DRAMATIQ_RESULTS_ENABLED", True),
                True,
            ),
            "DRAMATIQ_RESULTS_STORE_RESULTS": AppSettingService.parse_bool(
                cls._default_from_settings_and_env("DRAMATIQ_RESULTS_STORE_RESULTS", True),
                True,
            ),
            "DRAMATIQ_RESULTS_TTL_MS": int(cls._default_from_settings_and_env("DRAMATIQ_RESULTS_TTL_MS", 300000)),
            "DRAMATIQ_RESULTS_NAMESPACE": str(
                cls._default_from_settings_and_env("DRAMATIQ_RESULTS_NAMESPACE", "dramatiq:results")
                or "dramatiq:results"
            ).strip()
            or "dramatiq:results",
            "DRAMATIQ_RESULTS_REDIS_URL": str(
                cls._default_from_settings_and_env("DRAMATIQ_RESULTS_REDIS_URL", "") or ""
            ).strip(),
            "AUDIT_ENABLED": AppSettingService.parse_bool(
                cls._default_from_settings_and_env("AUDIT_ENABLED", True),
                True,
            ),
            "AUDIT_WATCH_AUTH_EVENTS": AppSettingService.parse_bool(
                cls._default_from_settings_and_env("AUDIT_WATCH_AUTH_EVENTS", True),
                True,
            ),
            "AUDIT_FORWARD_TO_LOKI": AppSettingService.parse_bool(
                cls._default_from_settings_and_env("AUDIT_FORWARD_TO_LOKI", True),
                True,
            ),
            "AUDITLOG_RETENTION_DAYS": int(cls._default_from_settings_and_env("AUDITLOG_RETENTION_DAYS", 14)),
            "AUDITLOG_RETENTION_SCHEDULE": str(
                cls._default_from_settings_and_env("AUDITLOG_RETENTION_SCHEDULE", "04:00") or ""
            ).strip(),
            "DJANGO_LOG_LEVEL": str(cls._default_from_settings_and_env("DJANGO_LOG_LEVEL", "INFO") or "INFO").strip()
            or "INFO",
            "DJANGO_DEBUG": AppSettingService.parse_bool(
                cls._default_from_settings_and_env("DJANGO_DEBUG", False),
                False,
            ),
            "DISABLE_DJANGO_VIEWS": AppSettingService.parse_bool(
                cls._default_from_settings_and_env("DISABLE_DJANGO_VIEWS", False),
                False,
            ),
            "MOCK_AUTH_ENABLED": AppSettingService.parse_bool(
                cls._default_from_settings_and_env("MOCK_AUTH_ENABLED", False),
                False,
            ),
            "INVOICE_IMPORT_MAX_WORKERS": int(cls._default_from_settings_and_env("INVOICE_IMPORT_MAX_WORKERS", 3)),
            "DATE_FORMAT_JS": str(
                cls._default_from_settings_and_env("DATE_FORMAT_JS", "dd-MM-yyyy") or "dd-MM-yyyy"
            ).strip()
            or "dd-MM-yyyy",
            "BASE_CURRENCY": str(cls._default_from_settings_and_env("BASE_CURRENCY", "IDR") or "IDR").strip() or "IDR",
            "DEFAULT_DOCUMENT_LANGUAGE_CODE": str(
                cls._default_from_settings_and_env("DEFAULT_DOCUMENT_LANGUAGE_CODE", "id") or "id"
            ).strip()
            or "id",
            "DEFAULT_CUSTOMER_EMAIL": str(
                cls._default_from_settings_and_env("DEFAULT_CUSTOMER_EMAIL", "sample_email@gmail.com")
                or "sample_email@gmail.com"
            ).strip()
            or "sample_email@gmail.com",
            "GOOGLE_TIMEZONE": str(
                cls._default_from_settings_and_env("GOOGLE_TIMEZONE", "Asia/Makassar") or "Asia/Makassar"
            ).strip()
            or "Asia/Makassar",
            "GOOGLE_CALENDAR_ID": str(
                cls._default_from_settings_and_env("GOOGLE_CALENDAR_ID", "primary") or "primary"
            ).strip()
            or "primary",
            "GOOGLE_TASKLIST_ID": str(
                cls._default_from_settings_and_env("GOOGLE_TASKLIST_ID", "@default") or "@default"
            ).strip()
            or "@default",
            "USE_CLOUD_STORAGE": AppSettingService.parse_bool(
                cls._default_from_settings_and_env("USE_CLOUD_STORAGE", False),
                False,
            ),
        }

    @classmethod
    def _coerce_value(cls, name: str, raw_value: Any, default_value: Any) -> Any:
        definition = AI_RUNTIME_SETTING_DEFINITIONS[name]
        if name == "OPENROUTER_API_BASE_URL":
            return cls._normalize_openrouter_api_base_url(raw_value, strict=False)
        if definition.value_type == "bool":
            return AppSettingService.parse_bool(raw_value, bool(default_value))
        if definition.value_type == "int":
            return AppSettingService.parse_int(raw_value, int(default_value))
        if definition.value_type == "float":
            return AppSettingService.parse_float(raw_value, float(default_value))
        if definition.value_type == "list":
            return AppSettingService.parse_list(raw_value, list(default_value or []))
        if definition.value_type == "json":
            if name == "LLM_FALLBACK_MODEL_CHAIN":
                return cls._normalize_fallback_model_chain(raw_value, strict=False)
            return AppSettingService.parse_json_like(raw_value)
        return str(raw_value if raw_value is not None else default_value).strip()

    @classmethod
    def get(cls, name: str) -> Any:
        defaults = cls.defaults()
        if name not in defaults or name not in AI_RUNTIME_SETTING_DEFINITIONS:
            raise KeyError(f"Unsupported runtime setting '{name}'.")
        default_value = defaults[name]
        raw_value = AppSettingService.get_raw(name, default=None, require_override=True)
        if raw_value is None:
            return default_value
        return cls._coerce_value(name, raw_value, default_value)

    @classmethod
    def get_many(cls) -> dict[str, Any]:
        defaults = cls.defaults()
        values: dict[str, Any] = {}
        for name in AI_RUNTIME_SETTING_DEFINITIONS:
            values[name] = cls.get(name)
        for key, default_value in defaults.items():
            values.setdefault(key, default_value)
        return values

    @classmethod
    def _first_available_model_for_provider(cls, provider: str) -> str:
        catalog = cls.get_model_catalog()
        providers = catalog.get("providers", {}) if isinstance(catalog, dict) else {}
        provider_data = providers.get(provider, {}) if isinstance(providers, dict) else {}
        models = provider_data.get("models", []) if isinstance(provider_data, dict) else []
        for model in models:
            model_id = str(model.get("id") or "").strip()
            if model_id:
                return model_id
        return ""

    @classmethod
    def _pick_available_model_for_provider(cls, provider: str, *candidates: Any) -> str:
        available_ids = cls._model_ids_by_provider().get(provider, set())
        for candidate in candidates:
            normalized = str(candidate or "").strip()
            if normalized and normalized in available_ids:
                return normalized
        return cls._first_available_model_for_provider(provider)

    @classmethod
    def get_llm_provider(cls) -> str:
        provider = str(cls.get("LLM_PROVIDER") or "openrouter").strip().lower()
        return provider if provider in {"openrouter", "openai", "groq"} else "openrouter"

    @classmethod
    def get_llm_default_model(cls) -> str:
        return str(cls.get("LLM_DEFAULT_MODEL") or "").strip()

    @classmethod
    def get_openrouter_default_model(cls) -> str:
        value = str(cls.get("OPENROUTER_DEFAULT_MODEL") or "").strip()
        return value or cls.get_llm_default_model()

    @classmethod
    def get_openai_default_model(cls) -> str:
        value = str(cls.get("OPENAI_DEFAULT_MODEL") or "").strip()
        return value or "gpt-5-mini"

    @classmethod
    def get_groq_default_model(cls) -> str:
        value = str(cls.get("GROQ_DEFAULT_MODEL") or "").strip()
        return value or "meta-llama/llama-4-scout-17b-16e-instruct"

    @classmethod
    def _get_runtime_workflow_model_override(cls, setting_name: str) -> str:
        return str(cls.get(setting_name) or "").strip()

    @classmethod
    def get_primary_runtime_model(cls) -> str:
        provider = cls.get_llm_provider()
        if provider == "groq":
            return cls.get_groq_default_model()
        if provider == "openai":
            return cls.get_llm_default_model() or cls.get_openai_default_model() or "gpt-5-mini"
        return cls.get_llm_default_model() or cls.get_openrouter_default_model() or "google/gemini-3-flash-preview"

    @classmethod
    def get_invoice_import_model(cls) -> str:
        value = cls._get_runtime_workflow_model_override("INVOICE_IMPORT_MODEL")
        return value or cls.get_primary_runtime_model()

    @classmethod
    def get_passport_ocr_model(cls) -> str:
        value = cls._get_runtime_workflow_model_override("PASSPORT_OCR_MODEL")
        return value or cls.get_primary_runtime_model()

    @classmethod
    def get_document_categorizer_model(cls) -> str:
        value = cls._get_runtime_workflow_model_override("DOCUMENT_CATEGORIZER_MODEL")
        return value or cls.get_primary_runtime_model()

    @classmethod
    def get_document_categorizer_model_high(cls) -> str:
        return cls._get_runtime_workflow_model_override("DOCUMENT_CATEGORIZER_MODEL_HIGH")

    @classmethod
    def get_document_validator_model(cls) -> str:
        value = cls._get_runtime_workflow_model_override("DOCUMENT_VALIDATOR_MODEL")
        return value or cls.get_primary_runtime_model()

    @classmethod
    def get_document_ocr_structured_model(cls) -> str:
        value = cls._get_runtime_workflow_model_override("DOCUMENT_OCR_STRUCTURED_MODEL")
        if value:
            return value
        validator = cls.get_document_validator_model()
        return validator or cls.get_primary_runtime_model()

    @classmethod
    def get_check_passport_model(cls) -> str:
        value = cls._get_runtime_workflow_model_override("CHECK_PASSPORT_MODEL")
        return value or cls.get_primary_runtime_model()

    @classmethod
    def get_check_passport_min_confidence(cls) -> float:
        return float(cls.get("CHECK_PASSPORT_AI_MIN_CONFIDENCE_FOR_UPLOAD"))

    @classmethod
    def get_timeout_setting_name_for_feature(cls, feature: str | None) -> str | None:
        normalized = str(feature or "").strip()
        return _TIMEOUT_SETTING_BY_FEATURE.get(normalized)

    @classmethod
    def get_timeout_for_feature(cls, feature: str | None) -> float | None:
        setting_name = cls.get_timeout_setting_name_for_feature(feature)
        if not setting_name:
            return None
        value = float(cls.get(setting_name))
        default_value = _WORKFLOW_TIMEOUT_DEFAULTS.get(setting_name, 120.0)
        return value if value > 0 else default_value

    @classmethod
    def get_auto_fallback_enabled(cls) -> bool:
        return bool(cls.get("LLM_AUTO_FALLBACK_ENABLED"))

    @classmethod
    def get_fallback_provider_order(cls) -> list[str]:
        providers = []
        seen = set()
        for provider in cls.get("LLM_FALLBACK_PROVIDER_ORDER"):
            normalized = str(provider).strip().lower()
            if normalized not in {"openrouter", "openai", "groq"}:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            providers.append(normalized)
        return providers

    @classmethod
    def get_fallback_model_chain(cls) -> list[FallbackModelChainStep]:
        raw_chain = cls.get("LLM_FALLBACK_MODEL_CHAIN")
        normalized_chain = cls._normalize_fallback_model_chain(raw_chain, strict=False)
        if not normalized_chain:
            normalized_chain = cls._fallback_chain_from_model_order(
                AppSettingService.parse_list(cls.get("LLM_FALLBACK_MODEL_ORDER"), [])
            )

        result: list[FallbackModelChainStep] = []
        for step in normalized_chain:
            model = str(step.get("model") or "").strip()
            provider = cls.get_provider_for_model(model)
            timeout_seconds = float(step.get("timeoutSeconds") or 0)
            if not model or not provider or timeout_seconds <= 0:
                continue
            result.append(
                FallbackModelChainStep(
                    provider=provider,
                    model=model,
                    timeout_seconds=timeout_seconds,
                )
            )
        return result

    @classmethod
    def get_fallback_model_order(cls) -> list[str]:
        return [step.model for step in cls.get_fallback_model_chain()]

    @classmethod
    def get_fallback_sticky_seconds(cls) -> int:
        value = int(cls.get("LLM_FALLBACK_STICKY_SECONDS"))
        return value if value > 0 else 3600

    @classmethod
    def get_fallback_sticky_cache_key(cls) -> str:
        value = str(cls.get("LLM_FALLBACK_STICKY_CACHE_KEY") or "").strip()
        return value or "ai:router:sticky_provider"

    @classmethod
    def get_openrouter_timeout(cls) -> float:
        value = float(cls.get("OPENROUTER_TIMEOUT"))
        return value if value > 0 else 30.0

    @classmethod
    def get_openai_timeout(cls) -> float:
        value = float(cls.get("OPENAI_TIMEOUT"))
        return value if value > 0 else 120.0

    @staticmethod
    def _load_llm_models_config() -> dict[str, Any]:
        provider_names = {
            "openrouter": "OpenRouter",
            "openai": "OpenAI Direct",
            "groq": "Groq",
        }
        providers: dict[str, dict[str, Any]] = {}
        for provider in _PROVIDER_PRIORITY:
            providers[provider] = {"name": provider_names.get(provider, provider.title()), "models": []}

        for model in AiModel.objects.all().order_by("provider", "name", "model_id"):
            provider_key = str(model.provider or "").strip().lower()
            if provider_key not in providers:
                providers[provider_key] = {"name": provider_names.get(provider_key, provider_key.title()), "models": []}
            providers[provider_key]["models"].append(
                {
                    "id": model.model_id,
                    "name": model.name,
                    "description": model.description,
                    "capabilities": {
                        "vision": bool(model.vision),
                        "fileUpload": bool(model.file_upload),
                        "reasoning": bool(model.reasoning),
                    },
                    "contextLength": model.context_length,
                    "maxCompletionTokens": model.max_completion_tokens,
                    "modality": model.modality,
                }
            )
        return {"providers": providers}

    @classmethod
    def get_model_catalog(cls) -> dict[str, Any]:
        return cls._load_llm_models_config()

    @classmethod
    def _all_model_ids(cls) -> set[str]:
        catalog = cls.get_model_catalog()
        providers = catalog.get("providers", {})
        model_ids: set[str] = set()
        for provider_data in providers.values():
            models = provider_data.get("models", []) if isinstance(provider_data, dict) else []
            for model in models:
                model_id = str(model.get("id") or "").strip()
                if model_id:
                    model_ids.add(model_id)
        return model_ids

    @classmethod
    def _model_ids_by_provider(cls) -> dict[str, set[str]]:
        catalog = cls.get_model_catalog()
        providers = catalog.get("providers", {})
        provider_map: dict[str, set[str]] = {}
        for provider_name, provider_data in providers.items():
            models = provider_data.get("models", []) if isinstance(provider_data, dict) else []
            values: set[str] = set()
            for model in models:
                model_id = str(model.get("id") or "").strip()
                if model_id:
                    values.add(model_id)
            provider_map[str(provider_name)] = values
        return provider_map

    @classmethod
    def get_providers_for_model(cls, model_id: str | None) -> list[str]:
        normalized_model_id = str(model_id or "").strip()
        if not normalized_model_id:
            return []

        by_provider = cls._model_ids_by_provider()
        matches = [provider for provider, model_ids in by_provider.items() if normalized_model_id in model_ids]
        if not matches:
            return []

        ordered: list[str] = []
        for provider in _PROVIDER_PRIORITY:
            if provider in matches:
                ordered.append(provider)
        for provider in sorted(matches):
            if provider not in ordered:
                ordered.append(provider)
        return ordered

    @classmethod
    def get_provider_for_model(cls, model_id: str | None, *, fallback: str | None = None) -> str | None:
        providers = cls.get_providers_for_model(model_id)
        if not providers:
            candidate = str(fallback or "").strip().lower()
            return candidate if candidate in _PROVIDER_OPTIONS else None

        preferred = str(fallback or "").strip().lower()
        if preferred and preferred in providers:
            return preferred
        return providers[0]

    @classmethod
    def workflow_bindings(cls) -> list[dict[str, Any]]:
        return [dict(item) for item in _WORKFLOW_BINDINGS]

    @classmethod
    def serialize_runtime_settings(cls) -> list[dict[str, Any]]:
        defaults = cls.defaults()
        current = cls.get_many()
        rows: list[dict[str, Any]] = []
        for definition in AI_RUNTIME_SETTING_DEFINITIONS.values():
            metadata = AppSettingService.get_metadata(
                definition.name,
                hardcoded_default=defaults.get(definition.name),
                fallback_scope=definition.scope,
                fallback_description=definition.description,
                effective_value=current.get(definition.name),
            )
            metadata.update(
                {
                    "valueType": definition.value_type,
                    # Backward compatibility for existing frontend contracts.
                    "value": metadata.get("effectiveValue"),
                }
            )
            rows.append(metadata)
        return rows

    @classmethod
    def _normalize_for_storage(cls, name: str, value: Any) -> str:
        definition = AI_RUNTIME_SETTING_DEFINITIONS[name]
        if definition.value_type == "bool":
            return "true" if AppSettingService.parse_bool(value, False) else "false"
        if definition.value_type == "int":
            return str(AppSettingService.parse_int(value, 0))
        if definition.value_type == "float":
            return str(AppSettingService.parse_float(value, 0.0))
        if definition.value_type == "list":
            values = AppSettingService.parse_list(value, [])
            return ",".join(values)
        if definition.value_type == "json":
            normalized_json = cls._coerce_value(name, value, [])
            return json.dumps(normalized_json)
        return str(value if value is not None else "").strip()

    @classmethod
    def replace_deleted_model_references(cls, deleted_model_id: str) -> None:
        normalized_deleted_model_id = str(deleted_model_id or "").strip()
        if not normalized_deleted_model_id:
            return

        defaults = cls.defaults()
        active_provider = cls.get_llm_provider()
        safe_openrouter_default = cls._pick_available_model_for_provider(
            "openrouter",
            cls.get_openrouter_default_model(),
            defaults.get("OPENROUTER_DEFAULT_MODEL"),
            defaults.get("LLM_DEFAULT_MODEL"),
        )
        safe_openai_default = cls._pick_available_model_for_provider(
            "openai",
            cls.get_openai_default_model(),
            defaults.get("OPENAI_DEFAULT_MODEL"),
        )
        safe_groq_default = cls._pick_available_model_for_provider(
            "groq",
            cls.get_groq_default_model(),
            defaults.get("GROQ_DEFAULT_MODEL"),
        )
        if active_provider == "openai":
            safe_llm_default = cls._pick_available_model_for_provider(
                "openai",
                cls.get_llm_default_model(),
                safe_openai_default,
                defaults.get("OPENAI_DEFAULT_MODEL"),
                defaults.get("LLM_DEFAULT_MODEL"),
            )
            safe_workflow_default = safe_llm_default or safe_openai_default
        elif active_provider == "groq":
            safe_llm_default = (
                cls._pick_available_model_for_provider(
                    "openrouter",
                    cls.get_llm_default_model(),
                    defaults.get("LLM_DEFAULT_MODEL"),
                    safe_openrouter_default,
                )
                or safe_openai_default
            )
            safe_workflow_default = safe_groq_default
        else:
            safe_llm_default = cls._pick_available_model_for_provider(
                "openrouter",
                cls.get_llm_default_model(),
                safe_openrouter_default,
                defaults.get("OPENROUTER_DEFAULT_MODEL"),
                defaults.get("LLM_DEFAULT_MODEL"),
            )
            safe_workflow_default = safe_llm_default or safe_openrouter_default

        replacement_map = {
            "LLM_DEFAULT_MODEL": safe_llm_default,
            "GROQ_DEFAULT_MODEL": safe_groq_default,
            "OPENROUTER_DEFAULT_MODEL": safe_openrouter_default,
            "OPENAI_DEFAULT_MODEL": safe_openai_default,
            "INVOICE_IMPORT_MODEL": safe_workflow_default,
            "PASSPORT_OCR_MODEL": safe_workflow_default,
            "DOCUMENT_CATEGORIZER_MODEL": safe_workflow_default,
            "DOCUMENT_CATEGORIZER_MODEL_HIGH": safe_workflow_default,
            "DOCUMENT_VALIDATOR_MODEL": safe_workflow_default,
            "DOCUMENT_OCR_STRUCTURED_MODEL": safe_workflow_default,
            "CHECK_PASSPORT_MODEL": safe_workflow_default,
        }

        for setting_name in _MODEL_SETTING_KEYS:
            current = str(AppSettingService.get_raw(setting_name, default="") or "").strip()
            if current != normalized_deleted_model_id:
                continue
            replacement_value = replacement_map.get(setting_name, "")
            if replacement_value:
                definition = AI_RUNTIME_SETTING_DEFINITIONS[setting_name]
                AppSettingService.set_raw(
                    name=setting_name,
                    value=replacement_value,
                    scope=definition.scope,
                    description=definition.description,
                    updated_by=None,
                    force_override=True,
                )
            else:
                AppSettingService.delete_raw(setting_name)

        chain_without_deleted_model = [
            {"model": step.model, "timeoutSeconds": step.timeout_seconds}
            for step in cls.get_fallback_model_chain()
            if step.model != normalized_deleted_model_id
        ]
        if chain_without_deleted_model != [
            {"model": step.model, "timeoutSeconds": step.timeout_seconds} for step in cls.get_fallback_model_chain()
        ]:
            cls.update_runtime_settings(
                {
                    "LLM_FALLBACK_MODEL_CHAIN": chain_without_deleted_model,
                },
                updated_by=None,
            )

    @classmethod
    def update_runtime_settings(cls, updates: dict[str, Any], updated_by=None) -> dict[str, Any]:
        if not isinstance(updates, dict):
            raise ValueError("Settings update payload must be an object.")

        model_ids = cls._all_model_ids()
        model_ids_by_provider = cls._model_ids_by_provider()
        defaults = cls.defaults()
        normalized_updates: dict[str, Any] = {}
        cleared_setting_names: set[str] = set()
        for name, raw_value in updates.items():
            if name not in AI_RUNTIME_SETTING_DEFINITIONS:
                raise ValueError(f"Unsupported setting '{name}'.")
            if raw_value is None:
                cleared_setting_names.add(name)
                continue
            normalized_updates[name] = raw_value

        if "LLM_FALLBACK_MODEL_CHAIN" in normalized_updates:
            chain = cls._normalize_fallback_model_chain(
                normalized_updates["LLM_FALLBACK_MODEL_CHAIN"],
                strict=True,
            )
            normalized_updates["LLM_FALLBACK_MODEL_CHAIN"] = chain
            normalized_updates["LLM_FALLBACK_MODEL_ORDER"] = [step["model"] for step in chain]
            cleared_setting_names.discard("LLM_FALLBACK_MODEL_ORDER")
        elif "LLM_FALLBACK_MODEL_ORDER" in normalized_updates:
            models = AppSettingService.parse_list(normalized_updates["LLM_FALLBACK_MODEL_ORDER"], [])
            unknown = [model for model in models if model not in model_ids]
            if unknown:
                raise ValueError(f"LLM_FALLBACK_MODEL_ORDER contains unknown models: {unknown}.")
            deduped_models = list(dict.fromkeys(models))
            normalized_updates["LLM_FALLBACK_MODEL_ORDER"] = deduped_models
            normalized_updates["LLM_FALLBACK_MODEL_CHAIN"] = cls._fallback_chain_from_model_order(deduped_models)
            cleared_setting_names.discard("LLM_FALLBACK_MODEL_CHAIN")

        if "LLM_FALLBACK_MODEL_CHAIN" in cleared_setting_names:
            cleared_setting_names.add("LLM_FALLBACK_MODEL_ORDER")
        if "LLM_FALLBACK_MODEL_ORDER" in cleared_setting_names:
            cleared_setting_names.add("LLM_FALLBACK_MODEL_CHAIN")

        if "LLM_PROVIDER" in normalized_updates:
            provider = str(normalized_updates["LLM_PROVIDER"]).strip().lower()
            if provider not in _PROVIDER_OPTIONS:
                raise ValueError("LLM_PROVIDER must be one of: openrouter, openai, groq.")
            normalized_updates["LLM_PROVIDER"] = provider

        if "LLM_FALLBACK_PROVIDER_ORDER" in normalized_updates:
            providers = AppSettingService.parse_list(normalized_updates["LLM_FALLBACK_PROVIDER_ORDER"], [])
            invalid = [provider for provider in providers if provider not in _PROVIDER_OPTIONS]
            if invalid:
                raise ValueError(f"LLM_FALLBACK_PROVIDER_ORDER contains unsupported providers: {invalid}.")
            normalized_updates["LLM_FALLBACK_PROVIDER_ORDER"] = list(dict.fromkeys(providers))

        for name, normalized_value in normalized_updates.items():
            if name in _MODEL_SETTING_KEYS and normalized_value and normalized_value not in model_ids:
                raise ValueError(f"Model '{normalized_value}' is not present in configured AI models.")

        openrouter_model_ids = model_ids_by_provider.get("openrouter", set())
        openai_model_ids = model_ids_by_provider.get("openai", set())
        groq_model_ids = model_ids_by_provider.get("groq", set())
        llm_provider_changed = "LLM_PROVIDER" in normalized_updates or "LLM_PROVIDER" in cleared_setting_names
        llm_default_updated = "LLM_DEFAULT_MODEL" in normalized_updates
        if "LLM_PROVIDER" in normalized_updates:
            effective_llm_provider = str(normalized_updates["LLM_PROVIDER"]).strip().lower()
        elif "LLM_PROVIDER" in cleared_setting_names:
            effective_llm_provider = str(defaults.get("LLM_PROVIDER") or "openrouter").strip().lower()
        else:
            effective_llm_provider = cls.get_llm_provider()
        if "LLM_DEFAULT_MODEL" in normalized_updates:
            effective_llm_default_model = str(normalized_updates["LLM_DEFAULT_MODEL"]).strip()
        elif "LLM_DEFAULT_MODEL" in cleared_setting_names:
            effective_llm_default_model = str(defaults.get("LLM_DEFAULT_MODEL") or "").strip()
        else:
            effective_llm_default_model = cls.get_llm_default_model()

        should_validate_llm_default = llm_provider_changed or llm_default_updated
        if should_validate_llm_default and effective_llm_default_model and effective_llm_default_model not in model_ids:
            raise ValueError("LLM_DEFAULT_MODEL must be listed in configured AI models.")
        if effective_llm_default_model in model_ids:
            if effective_llm_provider == "openrouter" and effective_llm_default_model not in openrouter_model_ids:
                raise ValueError(
                    "LLM_DEFAULT_MODEL must be a model listed under provider 'openrouter' when LLM_PROVIDER is 'openrouter'."
                )
            if effective_llm_provider == "openai" and effective_llm_default_model not in openai_model_ids:
                raise ValueError(
                    "LLM_DEFAULT_MODEL must be a model listed under provider 'openai' when LLM_PROVIDER is 'openai'."
                )
        elif llm_provider_changed and effective_llm_default_model:
            raise ValueError("LLM_DEFAULT_MODEL must be listed in configured AI models.")

        openrouter_default = str(normalized_updates.get("OPENROUTER_DEFAULT_MODEL") or "").strip()
        if openrouter_default and openrouter_default not in openrouter_model_ids:
            raise ValueError("OPENROUTER_DEFAULT_MODEL must be a model listed under provider 'openrouter'.")

        openai_default = str(normalized_updates.get("OPENAI_DEFAULT_MODEL") or "").strip()
        if openai_default and openai_default not in openai_model_ids:
            raise ValueError("OPENAI_DEFAULT_MODEL must be a model listed under provider 'openai'.")

        groq_default = str(normalized_updates.get("GROQ_DEFAULT_MODEL") or "").strip()
        if groq_default and groq_default not in groq_model_ids:
            raise ValueError("GROQ_DEFAULT_MODEL must be a model listed under provider 'groq'.")

        for name in _TIMEOUT_SETTING_KEYS:
            if name not in normalized_updates:
                continue
            try:
                normalized_timeout = float(normalized_updates[name])
            except (TypeError, ValueError):
                raise ValueError(f"{name} must be a positive number.") from None
            if normalized_timeout <= 0:
                raise ValueError(f"{name} must be greater than zero.")
            normalized_updates[name] = normalized_timeout

        if "OPENROUTER_API_BASE_URL" in normalized_updates:
            normalized_updates["OPENROUTER_API_BASE_URL"] = cls._normalize_openrouter_api_base_url(
                normalized_updates["OPENROUTER_API_BASE_URL"],
                strict=True,
            )

        for name in cleared_setting_names:
            AppSettingService.delete_raw(name)

        serialized_updates = {
            name: cls._normalize_for_storage(name, normalized_value)
            for name, normalized_value in normalized_updates.items()
        }
        for name, normalized_value in normalized_updates.items():
            definition = AI_RUNTIME_SETTING_DEFINITIONS[name]
            AppSettingService.set_raw(
                name=name,
                value=serialized_updates[name],
                scope=definition.scope,
                description=definition.description,
                updated_by=updated_by,
                force_override=True,
            )

        return cls.get_many()
