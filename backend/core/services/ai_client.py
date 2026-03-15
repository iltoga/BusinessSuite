"""
AI Client Base Module
Provides a reusable AI client for OpenRouter/OpenAI/Groq API access.
All AI-powered services should use this base client for consistency.
"""

import base64
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Union

import openai
from core.services.ai_runtime_settings_service import AIRuntimeSettingsService
from core.services.ai_usage_service import AIUsageFeature, AIUsageService
from core.services.logger_service import Logger
from django.conf import settings
from django.core.cache import cache
from django.core.files.uploadedfile import UploadedFile
from openai import OpenAI

try:  # pragma: no cover - import optional for environments without groq SDK
    import groq
    from groq import Groq
except ImportError:  # pragma: no cover
    groq = None  # type: ignore[assignment]
    Groq = None  # type: ignore[assignment]

logger = Logger.get_logger(__name__)


GENERIC_AI_PROVIDER_ERROR = "AI provider error"
GENERIC_AI_SLOW_RESPONSE = "AI slow response"


class AIConnectionError(Exception):
    """Exception raised when a connection/provider error occurs with the AI provider."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "provider_error",
        is_timeout: bool = False,
    ):
        super().__init__(message)
        self.error_code = error_code
        self.is_timeout = is_timeout


def is_ai_timeout_exception(exc: BaseException) -> bool:
    """Return True when an exception represents an AI timeout."""
    return isinstance(exc, AIConnectionError) and bool(getattr(exc, "is_timeout", False))


def get_ai_user_message(exc: BaseException) -> str:
    """Map provider exceptions to safe user-facing messages."""
    if is_ai_timeout_exception(exc):
        return GENERIC_AI_SLOW_RESPONSE
    if isinstance(exc, AIConnectionError):
        return str(exc) or GENERIC_AI_PROVIDER_ERROR
    return GENERIC_AI_PROVIDER_ERROR


@dataclass
class _ProviderContext:
    provider_key: str
    provider_name: str
    client: Any
    api_key: str
    model: str
    timeout: float


@dataclass(frozen=True)
class _AttemptRoute:
    provider_key: str
    model: str
    timeout: float | None = None


class AIClient:
    """
    Base AI client for OpenRouter/OpenAI/Groq API.
    Provides common functionality for all AI-powered services.
    """

    SUPPORTED_PROVIDERS = {"openrouter", "openai", "groq"}
    RETRIABLE_ERROR_CODES = {
        "timeout",
        "connection_error",
        "rate_limit",
        "not_found",
        "internal_server",
        "status_error",
        "schema_validation_failed",
        "bad_request",
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        use_openrouter: Optional[bool] = None,
        timeout: Optional[float] = None,
        feature_name: Optional[str] = None,
    ):
        """
        Initialize the AI client.

        Args:
            api_key: API key (defaults to settings based on provider)
            model: Model to use (defaults to settings.LLM_DEFAULT_MODEL)
            provider: Explicit provider override ("openrouter", "openai", "groq")
            use_openrouter: Whether to use OpenRouter (defaults to settings.LLM_PROVIDER)
            timeout: Request timeout in seconds (defaults to settings)
            feature_name: Logical AI feature tag used for usage accounting
        """
        self.feature_name = feature_name or AIUsageFeature.UNKNOWN
        self._api_key_override = api_key
        self._model_override = model
        self._timeout_override = timeout
        self._explicit_provider_requested = provider is not None or use_openrouter is not None

        self._requested_provider = self._resolve_requested_provider(provider=provider, use_openrouter=use_openrouter)
        self._provider_contexts: dict[tuple[str, float | None], _ProviderContext] = {}
        self._initial_timeout_override = self._resolve_initial_timeout_override()

        # Compatibility attributes used by services/tests.
        self.provider_key = self._requested_provider
        self.provider_name = ""
        self.api_key = None
        self.model = ""
        self.timeout = 0.0
        self.client = None
        self.use_openrouter = False

        initial_provider = self._resolve_initial_provider(self._requested_provider)
        self._activate_provider(initial_provider, timeout_override=self._initial_timeout_override)

    @classmethod
    def _normalize_provider(cls, provider: Optional[str], *, strict: bool = False) -> str:
        candidate = (provider or "").strip().lower()
        if candidate in cls.SUPPORTED_PROVIDERS:
            return candidate
        if strict and candidate:
            raise ValueError(
                f"Unsupported LLM provider '{provider}'. "
                f"Supported providers are: {sorted(cls.SUPPORTED_PROVIDERS)}."
            )
        return "openrouter"

    def _resolve_requested_provider(self, *, provider: Optional[str], use_openrouter: Optional[bool]) -> str:
        if provider is not None:
            return self._normalize_provider(provider, strict=True)
        if use_openrouter is not None:
            return "openrouter" if bool(use_openrouter) else "openai"
        inferred_provider = AIRuntimeSettingsService.get_provider_for_model(self._model_override)
        if inferred_provider:
            return inferred_provider
        configured = AIRuntimeSettingsService.get_llm_provider()
        normalized = self._normalize_provider(configured, strict=False)
        if normalized != str(configured).strip().lower():
            logger.warning("Unknown LLM_PROVIDER '%s'. Falling back to 'openrouter'.", configured)
        return normalized

    def _resolve_initial_timeout_override(self) -> float | None:
        if self._timeout_override is not None:
            return self._timeout_override
        feature_timeout = AIRuntimeSettingsService.get_timeout_for_feature(self.feature_name)
        return feature_timeout if feature_timeout and feature_timeout > 0 else None

    @staticmethod
    def _sticky_cache_key() -> str:
        return AIRuntimeSettingsService.get_fallback_sticky_cache_key()

    @staticmethod
    def _fallback_sticky_seconds() -> int:
        configured = AIRuntimeSettingsService.get_fallback_sticky_seconds()
        return configured if configured > 0 else 3600

    @staticmethod
    def _router_enabled() -> bool:
        return AIRuntimeSettingsService.get_auto_fallback_enabled()

    def _get_sticky_provider(self) -> Optional[str]:
        provider = cache.get(self._sticky_cache_key())
        if not provider:
            return None
        candidate = str(provider).strip().lower()
        return candidate if candidate in self.SUPPORTED_PROVIDERS else None

    def _set_sticky_provider(self, provider: str) -> None:
        if not self._router_enabled():
            return
        normalized = self._normalize_provider(provider, strict=False)
        cache.set(self._sticky_cache_key(), normalized, timeout=self._fallback_sticky_seconds())
        logger.warning(
            "AI router sticky provider set to %s for %ss",
            normalized,
            self._fallback_sticky_seconds(),
        )

    def _resolve_initial_provider(self, requested_provider: str) -> str:
        if self._explicit_provider_requested:
            return requested_provider
        if not self._router_enabled():
            return requested_provider

        sticky = self._get_sticky_provider()
        if sticky and sticky != requested_provider and self._is_provider_available(sticky):
            logger.warning(
                "Using sticky AI provider '%s' instead of configured '%s'.",
                sticky,
                requested_provider,
            )
            return sticky
        return requested_provider

    def _provider_default_model(self, provider: str) -> str:
        if provider == "openrouter":
            return (
                AIRuntimeSettingsService.get_openrouter_default_model()
                or AIRuntimeSettingsService.get_llm_default_model()
                or "google/gemini-3-flash-preview"
            )
        if provider == "openai":
            configured_provider = AIRuntimeSettingsService.get_llm_provider()
            if configured_provider == "openai":
                return (
                    AIRuntimeSettingsService.get_llm_default_model()
                    or AIRuntimeSettingsService.get_openai_default_model()
                    or "gpt-4o-mini"
                )
            return AIRuntimeSettingsService.get_openai_default_model() or "gpt-4o-mini"
        if provider == "groq":
            return AIRuntimeSettingsService.get_groq_default_model()
        return ""

    def _configured_fallback_order(self, primary_provider: str) -> list[str]:
        values = AIRuntimeSettingsService.get_fallback_provider_order()
        if not values and primary_provider == "groq":
            values = ["openrouter"]

        deduped: list[str] = []
        for provider in values:
            normalized = provider.strip().lower()
            if normalized not in self.SUPPORTED_PROVIDERS:
                logger.warning("Ignoring unsupported fallback provider '%s'.", provider)
                continue
            if normalized in deduped:
                continue
            deduped.append(normalized)
        return deduped

    def _fallback_candidates(self, primary_provider: str, primary_model: str) -> list[_AttemptRoute]:
        if not self._router_enabled():
            return []

        candidates: list[_AttemptRoute] = []
        seen: set[tuple[str, str]] = set()
        primary = (primary_provider, str(primary_model or "").strip())

        configured_chain = AIRuntimeSettingsService.get_fallback_model_chain()
        for step in configured_chain:
            route = (step.provider, step.model)
            if route == primary or route in seen:
                continue
            if not self._is_provider_available(step.provider):
                logger.warning(
                    "Skipping fallback model '%s' because provider '%s' is unavailable.",
                    step.model,
                    step.provider,
                )
                continue
            seen.add(route)
            candidates.append(
                _AttemptRoute(
                    provider_key=step.provider,
                    model=step.model,
                    timeout=step.timeout_seconds,
                )
            )

        if candidates:
            return candidates

        for provider in self._configured_fallback_order(primary_provider):
            if self._is_provider_available(provider):
                model = self._provider_default_model(provider)
                route = (provider, str(model or "").strip())
                if not route[1] or route == primary or route in seen:
                    continue
                seen.add(route)
                candidates.append(
                    _AttemptRoute(
                        provider_key=provider,
                        model=route[1],
                        timeout=self._provider_timeout_for_route(provider),
                    )
                )
            else:
                logger.warning("Skipping fallback provider '%s' because it is not configured.", provider)
        return candidates

    def _provider_timeout_for_route(self, provider: str) -> float:
        if provider == "openrouter":
            return AIRuntimeSettingsService.get_openrouter_timeout()
        if provider == "openai":
            return AIRuntimeSettingsService.get_openai_timeout()
        if provider == "groq":
            return float(getattr(settings, "GROQ_TIMEOUT", 120.0))
        return 120.0

    def _api_key_for_provider(self, provider: str) -> Optional[str]:
        if self._api_key_override and provider == self._requested_provider:
            return self._api_key_override

        if provider == "openrouter":
            return getattr(settings, "OPENROUTER_API_KEY", None)
        if provider == "openai":
            return getattr(settings, "OPENAI_API_KEY", None)
        if provider == "groq":
            return getattr(settings, "GROQ_API_KEY", None)
        return None

    def _is_provider_available(self, provider: str) -> bool:
        if provider == "groq" and Groq is None:
            return False
        return bool(self._api_key_for_provider(provider))

    def _create_provider_context(self, provider: str, *, timeout_override: float | None = None) -> _ProviderContext:
        if provider == "openrouter":
            return self._create_openrouter_context(timeout_override=timeout_override)
        if provider == "openai":
            return self._create_openai_context(timeout_override=timeout_override)
        if provider == "groq":
            return self._create_groq_context(timeout_override=timeout_override)
        raise ValueError(f"Unsupported LLM provider '{provider}'.")

    def _activate_provider(self, provider: str, *, timeout_override: float | None = None) -> None:
        cache_key = (provider, timeout_override)
        context = self._provider_contexts.get(cache_key)
        if context is None:
            context = self._create_provider_context(provider, timeout_override=timeout_override)
            self._provider_contexts[cache_key] = context

        self.provider_key = context.provider_key
        self.provider_name = context.provider_name
        self.client = context.client
        self.api_key = context.api_key
        self.model = context.model
        self.timeout = context.timeout
        self.use_openrouter = self.provider_key == "openrouter"

    def _create_openrouter_context(self, *, timeout_override: float | None = None) -> _ProviderContext:
        api_key = self._api_key_for_provider("openrouter")
        if not api_key:
            raise ValueError("OpenRouter API key not configured. Set OPENROUTER_API_KEY in settings or .env file.")

        effective_default_model = (
            AIRuntimeSettingsService.get_openrouter_default_model()
            or AIRuntimeSettingsService.get_llm_default_model()
            or "google/gemini-3-flash-preview"
        )
        model = self._model_override_for_provider("openrouter") or effective_default_model

        base_url = AIRuntimeSettingsService.get("OPENROUTER_API_BASE_URL")
        timeout = timeout_override or self._timeout_override or AIRuntimeSettingsService.get_openrouter_timeout()
        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
        )
        logger.info("Initialized AI client with OpenRouter (model: %s, timeout: %ss)", model, timeout)
        return _ProviderContext(
            provider_key="openrouter",
            provider_name="OpenRouter",
            client=client,
            api_key=api_key,
            model=model,
            timeout=timeout,
        )

    def _create_openai_context(self, *, timeout_override: float | None = None) -> _ProviderContext:
        api_key = self._api_key_for_provider("openai")
        if not api_key:
            raise ValueError("OpenAI API key not configured. Set OPENAI_API_KEY in settings or .env file.")

        configured_provider = AIRuntimeSettingsService.get_llm_provider()
        openai_default_model = AIRuntimeSettingsService.get_openai_default_model()
        llm_default_model = AIRuntimeSettingsService.get_llm_default_model()
        if configured_provider == "openai":
            default_model = llm_default_model or openai_default_model or "gpt-4o-mini"
        else:
            default_model = openai_default_model or "gpt-4o-mini"

        model = self._model_override_for_provider("openai") or default_model
        timeout = timeout_override or self._timeout_override or AIRuntimeSettingsService.get_openai_timeout()
        client = OpenAI(
            api_key=api_key,
            timeout=timeout,
        )
        logger.info("Initialized AI client with OpenAI (model: %s, timeout: %ss)", model, timeout)
        return _ProviderContext(
            provider_key="openai",
            provider_name="OpenAI",
            client=client,
            api_key=api_key,
            model=model,
            timeout=timeout,
        )

    def _create_groq_context(self, *, timeout_override: float | None = None) -> _ProviderContext:
        if Groq is None:
            raise ValueError("groq library is not installed. Install `groq` package to use LLM_PROVIDER='groq'.")

        api_key = self._api_key_for_provider("groq")
        if not api_key:
            raise ValueError("Groq API key not configured. Set GROQ_API_KEY in settings or .env file.")

        default_model = AIRuntimeSettingsService.get_groq_default_model()
        model = self._model_override_for_provider("groq") or default_model
        timeout = timeout_override or self._timeout_override or float(getattr(settings, "GROQ_TIMEOUT", 120.0))
        client = Groq(api_key=api_key, timeout=timeout)
        logger.info("Initialized AI client with Groq (model: %s, timeout: %ss)", model, timeout)
        return _ProviderContext(
            provider_key="groq",
            provider_name="Groq",
            client=client,
            api_key=api_key,
            model=model,
            timeout=timeout,
        )

    def chat_completion(
        self,
        messages: list,
        temperature: float = 0.1,
        response_format: Optional[dict] = None,
        **kwargs,
    ) -> str:
        """
        Send a chat completion request.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature (0-2)
            response_format: Optional response format (e.g., json_schema)
            **kwargs: Additional arguments passed to the API

        Returns:
            Response text content
        """
        feature_name = kwargs.pop("feature_name", None) or self.feature_name or AIUsageFeature.UNKNOWN
        request_kwargs = {"messages": messages, "temperature": temperature, **kwargs}
        if response_format:
            request_kwargs["response_format"] = response_format

        primary_route = _AttemptRoute(
            provider_key=self.provider_key,
            model=self.model,
            timeout=self._initial_timeout_override,
        )

        router_enabled = self._router_enabled()
        if router_enabled:
            # Failover enabled: try primary once, then follow the fallback chain immediately on error
            attempted_routes = [primary_route] + self._fallback_candidates(self.provider_key, self.model)
        else:
            # Failover disabled: retry same model up to 3 times (no cross-provider failover)
            attempted_routes = [primary_route, primary_route, primary_route]

        last_error: Optional[AIConnectionError] = None

        for index, route in enumerate(attempted_routes):
            if route.provider_key != self.provider_key or (route.timeout is not None and route.timeout != self.timeout):
                self._activate_provider(route.provider_key, timeout_override=route.timeout)
            self.model = route.model

            try:
                result = self._chat_completion_single_attempt(
                    feature_name=feature_name,
                    request_kwargs=request_kwargs,
                )
                if index > 0:
                    self._set_sticky_provider(self.provider_key)
                return result
            except AIConnectionError as exc:
                last_error = exc
                is_last_attempt = index >= len(attempted_routes) - 1
                should_retry = exc.error_code in self.RETRIABLE_ERROR_CODES and not is_last_attempt
                if not should_retry:
                    raise

                next_route = attempted_routes[index + 1]
                if not router_enabled:
                    # Same-provider retry: brief exponential backoff (2s, 4s)
                    backoff = 2.0 * (2 ** index)
                    logger.warning(
                        "AI provider '%s' model '%s' failed with %s (attempt %d/3). "
                        "Retrying same model in %.0fs.",
                        self.provider_key,
                        self.model,
                        exc.error_code,
                        index + 1,
                        backoff,
                    )
                    time.sleep(backoff)
                else:
                    logger.warning(
                        "AI provider '%s' model '%s' failed with %s. "
                        "Retrying with fallback provider '%s' model '%s' (timeout=%ss).",
                        self.provider_key,
                        self.model,
                        exc.error_code,
                        next_route.provider_key,
                        next_route.model,
                        next_route.timeout or self.timeout,
                    )

        if last_error is not None:
            raise last_error
        raise AIConnectionError(GENERIC_AI_PROVIDER_ERROR, error_code="unexpected_error")

    def _chat_completion_single_attempt(self, *, feature_name: str, request_kwargs: dict[str, Any]) -> str:
        started_at = time.perf_counter()
        attempt_kwargs = {"model": self.model, **request_kwargs}

        # OpenRouter-specific hints (plugins, provider sorting) should not be
        # sent to other providers.  For OpenRouter requests, ensure the
        # provider-sorting preference from settings is present.
        if self.provider_key != "openrouter":
            attempt_kwargs.pop("extra_body", None)
        else:
            extra_body_raw = attempt_kwargs.get("extra_body")
            extra_body = dict(extra_body_raw) if isinstance(extra_body_raw, dict) else {}

            if "provider" not in extra_body:
                sort_pref = AIRuntimeSettingsService.get("OPENROUTER_PROVIDER_SORTING_PRIORITY")
                if sort_pref:
                    extra_body["provider"] = {"sort": sort_pref}

            if extra_body:
                attempt_kwargs["extra_body"] = extra_body

        try:
            response = self.client.chat.completions.create(**attempt_kwargs)
            self._record_usage(
                feature_name=feature_name,
                response=response,
                success=True,
                error_type="",
                started_at=started_at,
                provider_key=self.provider_key,
                model=self.model,
            )
            return response.choices[0].message.content
        except Exception as exc:
            mapped_error = self._map_provider_exception(exc)
            self._record_usage(
                feature_name=feature_name,
                response=None,
                success=False,
                error_type=type(exc).__name__,
                started_at=started_at,
                provider_key=self.provider_key,
                model=self.model,
            )
            self._log_provider_exception(exc, mapped_error)
            raise mapped_error from exc

    def _provider_exception_type(self, name: str, fallback: type[BaseException]) -> type[BaseException]:
        if self.provider_key == "groq" and groq is not None:
            return getattr(groq, name, fallback)
        return fallback

    def _model_override_for_provider(self, provider: str) -> str | None:
        normalized_override = str(self._model_override or "").strip()
        if not normalized_override:
            return None

        normalized_provider = self._normalize_provider(provider, strict=False)
        matching_provider = AIRuntimeSettingsService.get_provider_for_model(
            normalized_override,
            fallback=normalized_provider,
        )
        if matching_provider != normalized_provider:
            return None
        return normalized_override

    @staticmethod
    def _extract_provider_error_code(exc: BaseException) -> str:
        body = getattr(exc, "body", None)
        if isinstance(body, dict):
            nested_error = body.get("error")
            if isinstance(nested_error, dict):
                nested_code = nested_error.get("code")
                if nested_code:
                    return str(nested_code).strip().lower()
            body_code = body.get("code")
            if body_code:
                return str(body_code).strip().lower()

        direct_code = getattr(exc, "code", None) or getattr(exc, "error_code", None)
        if direct_code:
            return str(direct_code).strip().lower()
        return ""

    @staticmethod
    def _is_groq_schema_validation_bad_request(exc: BaseException) -> bool:
        body = getattr(exc, "body", None)
        if not isinstance(body, dict):
            return False

        nested_error = body.get("error")
        if not isinstance(nested_error, dict):
            return False

        code = str(nested_error.get("code") or "").strip().lower()
        if code == "json_validate_failed":
            return True

        message = str(nested_error.get("message") or "").strip().lower()
        if "invalid json schema for response_format" in message:
            return True

        schema_kind = str(nested_error.get("schema_kind") or "").strip().lower()
        param = str(nested_error.get("param") or "").strip().lower()
        return bool(schema_kind) and param == "response_format"

    def _map_provider_exception(self, exc: BaseException) -> AIConnectionError:
        if isinstance(exc, self._provider_exception_type("APITimeoutError", openai.APITimeoutError)):
            return AIConnectionError(GENERIC_AI_SLOW_RESPONSE, error_code="timeout", is_timeout=True)
        if isinstance(exc, self._provider_exception_type("APIConnectionError", openai.APIConnectionError)):
            return AIConnectionError(GENERIC_AI_PROVIDER_ERROR, error_code="connection_error")
        if isinstance(exc, self._provider_exception_type("RateLimitError", openai.RateLimitError)):
            return AIConnectionError(GENERIC_AI_PROVIDER_ERROR, error_code="rate_limit")
        if isinstance(exc, self._provider_exception_type("AuthenticationError", openai.AuthenticationError)):
            return AIConnectionError(GENERIC_AI_PROVIDER_ERROR, error_code="auth_error")
        if isinstance(exc, self._provider_exception_type("BadRequestError", openai.BadRequestError)):
            if self.provider_key == "groq" and self._is_groq_schema_validation_bad_request(exc):
                return AIConnectionError(GENERIC_AI_PROVIDER_ERROR, error_code="schema_validation_failed")
            return AIConnectionError(GENERIC_AI_PROVIDER_ERROR, error_code="bad_request")
        if isinstance(exc, self._provider_exception_type("NotFoundError", openai.NotFoundError)):
            return AIConnectionError(GENERIC_AI_PROVIDER_ERROR, error_code="not_found")
        if isinstance(exc, self._provider_exception_type("InternalServerError", openai.InternalServerError)):
            return AIConnectionError(GENERIC_AI_PROVIDER_ERROR, error_code="internal_server")
        if isinstance(exc, self._provider_exception_type("APIStatusError", openai.APIStatusError)):
            return AIConnectionError(GENERIC_AI_PROVIDER_ERROR, error_code="status_error")
        return AIConnectionError(GENERIC_AI_PROVIDER_ERROR, error_code="unexpected_error")

    def _log_provider_exception(self, exc: BaseException, mapped_error: AIConnectionError) -> None:
        if mapped_error.is_timeout:
            logger.error("%s timeout after %.1fs. details=%s", self.provider_name, self.timeout, str(exc))
            return
        if mapped_error.error_code == "connection_error":
            logger.error(
                "%s connection error: %s (cause=%s)",
                self.provider_name,
                str(exc),
                str(getattr(exc, "__cause__", "")) if getattr(exc, "__cause__", None) else "",
            )
            return
        if mapped_error.error_code == "rate_limit":
            logger.error("%s rate limit error: %s", self.provider_name, str(exc))
            return
        if mapped_error.error_code == "auth_error":
            logger.error("%s authentication error: %s", self.provider_name, str(exc))
            return
        if mapped_error.error_code == "bad_request":
            logger.error("%s bad request error: %s", self.provider_name, str(exc))
            return
        if mapped_error.error_code == "schema_validation_failed":
            logger.error(
                "%s schema validation error: %s (provider_code=%s)",
                self.provider_name,
                str(exc),
                self._extract_provider_error_code(exc) or "unknown",
            )
            return
        if mapped_error.error_code == "not_found":
            logger.error("%s not found error: %s", self.provider_name, str(exc))
            return
        if mapped_error.error_code == "internal_server":
            logger.error("%s internal server error: %s", self.provider_name, str(exc))
            return
        if mapped_error.error_code == "status_error":
            logger.error(
                "%s API status error http=%s details=%s",
                self.provider_name,
                getattr(exc, "status_code", "unknown"),
                str(exc),
            )
            return
        logger.error("Unexpected %s client error: %s", self.provider_name, str(exc), exc_info=True)

    def _record_usage(
        self,
        *,
        feature_name: str,
        response: Any,
        success: bool,
        error_type: str,
        started_at: float,
        provider_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        AIUsageService.enqueue_request_capture(
            feature=feature_name or self.feature_name or AIUsageFeature.UNKNOWN,
            provider=(provider_key or self.provider_key or "unknown").lower(),
            model=model or self.model or "unknown",
            response=response,
            success=success,
            error_type=error_type,
            latency_ms=elapsed_ms,
        )

    def chat_completion_json(
        self,
        messages: list,
        json_schema: dict,
        schema_name: str = "response",
        temperature: float = 0.1,
        strict: bool = True,
        retry_on_invalid_json: bool = True,
        **kwargs,
    ) -> dict:
        """
        Send a chat completion request with structured JSON output.

        OpenRouter, OpenAI and Groq support json_schema with strict mode.
        See: https://openrouter.ai/docs/guides/features/structured-outputs

        Args:
            messages: List of message dicts
            json_schema: JSON schema for the response
            schema_name: Name for the schema
            temperature: Sampling temperature
            strict: Whether to enforce strict schema adherence
            **kwargs: Additional arguments

        Returns:
            Parsed JSON response as dict
        """
        logger.debug(f"Using json_schema mode for model: {self.model} (strict={strict})")

        if self.provider_key == "openrouter":
            extra_body = kwargs.get("extra_body") or {}
            plugins = extra_body.get("plugins") or []
            if not any(isinstance(p, dict) and p.get("id") == "response-healing" for p in plugins):
                plugins.append({"id": "response-healing"})
            extra_body["plugins"] = plugins
            kwargs["extra_body"] = extra_body

        # Normalize nullable type arrays to anyOf syntax for strict mode compatibility.
        # Standard JSON Schema allows {"type": ["string", "null"]} but OpenAI strict
        # mode requires {"anyOf": [{"type": "string"}, {"type": "null"}]}.
        normalized_schema = self._normalize_schema_for_strict(json_schema) if strict else json_schema

        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": strict,
                "schema": normalized_schema,
            },
        }

        return self._request_json_with_retry(
            messages=messages,
            temperature=temperature,
            response_format=response_format,
            retry_on_invalid_json=retry_on_invalid_json,
            **kwargs,
        )

    def chat_completion_simple_json(
        self,
        messages: list,
        temperature: float = 0.3,
        retry_on_invalid_json: bool = True,
        **kwargs,
    ) -> dict:
        """
        Send a chat completion request expecting simple JSON object response.

        Args:
            messages: List of message dicts
            temperature: Sampling temperature
            **kwargs: Additional arguments

        Returns:
            Parsed JSON response as dict
        """
        return self._request_json_with_retry(
            messages=messages,
            temperature=temperature,
            response_format={"type": "json_object"},
            retry_on_invalid_json=retry_on_invalid_json,
            **kwargs,
        )

    def _request_json_with_retry(
        self,
        messages: list,
        temperature: float,
        response_format: dict,
        retry_on_invalid_json: bool = True,
        **kwargs,
    ) -> dict:
        """
        Request JSON output with one automatic retry when the model emits invalid JSON.

        Some models occasionally return malformed JSON despite response_format hints.
        We attempt local repair first, then retry once with a corrective prompt.
        """
        response_text = self.chat_completion(
            messages=messages,
            temperature=temperature,
            response_format=response_format,
            **kwargs,
        )
        try:
            return self._parse_json_dict(response_text)
        except ValueError as first_exc:
            if not retry_on_invalid_json:
                raise AIConnectionError(
                    f"Invalid JSON response from {self.provider_name}: {first_exc}",
                    error_code="schema_validation_failed",
                ) from first_exc
            logger.warning(
                "Received malformed JSON from %s. Retrying once with corrective prompt. Error: %s",
                self.provider_name,
                str(first_exc),
            )

            retry_messages = list(messages) + [
                {
                    "role": "user",
                    "content": (
                        "Your previous answer was not valid JSON. "
                        "Return ONLY a valid JSON object. "
                        "Do not use markdown code fences."
                    ),
                }
            ]

            retry_text = self.chat_completion(
                messages=retry_messages,
                temperature=0.0,
                response_format=response_format,
                **kwargs,
            )
            try:
                return self._parse_json_dict(retry_text)
            except ValueError as retry_exc:
                raise AIConnectionError(
                    f"Invalid JSON response from {self.provider_name} after retry: {retry_exc}",
                    error_code="schema_validation_failed",
                ) from retry_exc

    @staticmethod
    def _normalize_schema_for_strict(schema: Any) -> Any:
        """Recursively normalize a JSON schema for OpenAI strict mode compatibility.

        Converts ``{"type": ["string", "null"]}`` (valid JSON Schema but rejected
        by OpenAI strict mode) into ``{"anyOf": [{"type": "string"}, {"type": "null"}]}``.

        Also strips ``minimum`` / ``maximum`` / ``minItems`` / ``maxItems`` /
        ``pattern`` constraints that OpenAI strict mode does not support.
        """
        if not isinstance(schema, dict):
            return schema

        result = {}
        for key, value in schema.items():
            if key == "type" and isinstance(value, list):
                # Convert type array to anyOf
                result["anyOf"] = [{"type": t} for t in value]
            elif key == "properties" and isinstance(value, dict):
                result[key] = {
                    prop_name: AIClient._normalize_schema_for_strict(prop_schema)
                    for prop_name, prop_schema in value.items()
                }
            elif key == "items" and isinstance(value, dict):
                result[key] = AIClient._normalize_schema_for_strict(value)
            elif key in ("minimum", "maximum", "minItems", "maxItems", "pattern"):
                # OpenAI strict mode does not support these constraints; skip them.
                continue
            else:
                result[key] = value

        return result

    @classmethod
    def _parse_json_dict(cls, response_text: Any) -> dict:
        """Parse a response into a JSON object with lightweight repair heuristics."""
        if isinstance(response_text, dict):
            return response_text

        if response_text is None:
            raise ValueError("AI response was empty.")

        if not isinstance(response_text, str):
            raise ValueError(f"AI response is not text (got {type(response_text).__name__}).")

        parse_errors: list[str] = []
        for candidate in cls._extract_json_candidates(response_text):
            tried: list[str] = [candidate]
            repaired = cls._repair_common_json_issues(candidate)
            if repaired != candidate:
                tried.append(repaired)

            for current in tried:
                try:
                    parsed = json.loads(current)
                except json.JSONDecodeError as exc:
                    parse_errors.append(str(exc))
                    continue

                if not isinstance(parsed, dict):
                    raise ValueError("AI response JSON must be an object.")
                return parsed

        if parse_errors:
            raise ValueError(parse_errors[-1])
        raise ValueError("No JSON object found in AI response.")

    @classmethod
    def _extract_json_candidates(cls, response_text: str) -> list[str]:
        """
        Build parse candidates from plain text and markdown-fenced JSON blocks.
        """
        candidates: list[str] = []
        seen: set[str] = set()

        def add(value: Optional[str]) -> None:
            if not value:
                return
            candidate = value.strip()
            if not candidate or candidate in seen:
                return
            seen.add(candidate)
            candidates.append(candidate)

        add(response_text)

        for match in re.finditer(r"```(?:json)?\s*(.*?)\s*```", response_text, flags=re.IGNORECASE | re.DOTALL):
            add(match.group(1))

        add(cls._extract_first_json_block(response_text))
        return candidates

    @staticmethod
    def _extract_first_json_block(text: str) -> Optional[str]:
        """Extract the first balanced JSON object/array block from arbitrary text."""
        start_obj = text.find("{")
        start_arr = text.find("[")

        starts = [pos for pos in (start_obj, start_arr) if pos >= 0]
        if not starts:
            return None

        start_index = min(starts)
        stack: list[str] = []
        in_string = False
        escaped = False

        for index in range(start_index, len(text)):
            ch = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
                continue

            if ch == "{":
                stack.append("}")
            elif ch == "[":
                stack.append("]")
            elif ch in ("}", "]"):
                if not stack or ch != stack[-1]:
                    return None
                stack.pop()
                if not stack:
                    return text[start_index : index + 1]

        return text[start_index:] if stack else None

    @staticmethod
    def _repair_common_json_issues(text: str) -> str:
        """
        Repair common malformed JSON patterns seen in model outputs.
        """
        src = text.strip()
        src = re.sub(r",\s*([}\]])", r"\1", src)

        repaired_chars: list[str] = []
        in_string = False
        escaped = False

        for i, ch in enumerate(src):
            if in_string:
                if escaped:
                    repaired_chars.append(ch)
                    escaped = False
                    continue

                if ch == "\\":
                    repaired_chars.append(ch)
                    escaped = True
                    continue

                if ch == '"':
                    next_non_space = None
                    for j in range(i + 1, len(src)):
                        if not src[j].isspace():
                            next_non_space = src[j]
                            break

                    # If next token is not a valid string terminator context, treat quote as unescaped content.
                    if next_non_space in (None, ":", ",", "}", "]"):
                        in_string = False
                        repaired_chars.append(ch)
                    else:
                        repaired_chars.append('\\"')
                    continue

                if ch == "\n":
                    repaired_chars.append("\\n")
                    continue
                if ch == "\r":
                    repaired_chars.append("\\r")
                    continue
                if ch == "\t":
                    repaired_chars.append("\\t")
                    continue
                if ord(ch) < 0x20:
                    repaired_chars.append(f"\\u{ord(ch):04x}")
                    continue

                repaired_chars.append(ch)
                continue

            if ch == '"':
                in_string = True
            repaired_chars.append(ch)

        if in_string:
            repaired_chars.append('"')

        repaired = "".join(repaired_chars)
        return re.sub(r",\s*([}\]])", r"\1", repaired)

    @staticmethod
    def read_file_bytes(file_content: Union[bytes, UploadedFile]) -> tuple[bytes, str]:
        """
        Read file bytes from various input types.

        Args:
            file_content: File bytes or Django UploadedFile

        Returns:
            Tuple of (file_bytes, filename)
        """
        if isinstance(file_content, UploadedFile):
            file_content.seek(0)
            file_bytes = file_content.read()
            filename = file_content.name or ""
        else:
            file_bytes = file_content
            filename = ""

        return file_bytes, filename

    @staticmethod
    def encode_image_base64(image_bytes: bytes) -> str:
        """
        Encode image bytes to base64 string.

        Args:
            image_bytes: Raw image bytes

        Returns:
            Base64 encoded string
        """
        return base64.b64encode(image_bytes).decode("utf-8")

    @staticmethod
    def get_mime_type(filename: str, default: str = "image/jpeg") -> str:
        """
        Get MIME type from filename extension.

        Args:
            filename: Filename with extension
            default: Default MIME type if extension not recognized

        Returns:
            MIME type string
        """
        if not filename:
            return default

        ext = Path(filename).suffix.lower().lstrip(".")

        mime_types = {
            # Images
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "gif": "image/gif",
            "webp": "image/webp",
            # Documents
            "pdf": "application/pdf",
            "doc": "application/msword",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "xls": "application/vnd.ms-excel",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }

        return mime_types.get(ext, default)

    @staticmethod
    def get_file_extension(filename: str) -> str:
        """
        Get file extension from filename.

        Args:
            filename: Filename with extension

        Returns:
            Lowercase extension without dot
        """
        if not filename:
            return ""
        return Path(filename).suffix.lower().lstrip(".")

    def build_vision_message(
        self,
        prompt: str,
        image_bytes: bytes,
        filename: str = "",
        system_prompt: Optional[str] = None,
    ) -> list:
        """
        Build messages list for vision API request.

        Args:
            prompt: User prompt text
            image_bytes: Image bytes to analyze
            filename: Optional filename for MIME type detection
            system_prompt: Optional system prompt

        Returns:
            List of message dicts for API request
        """
        base64_image = self.encode_image_base64(image_bytes)
        mime_type = self.get_mime_type(filename)

        messages = []

        if system_prompt:
            messages.append(
                {
                    "role": "system",
                    "content": system_prompt,
                }
            )

        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{base64_image}"},
                    },
                ],
            }
        )

        return messages
