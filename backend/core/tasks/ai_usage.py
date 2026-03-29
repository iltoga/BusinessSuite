"""
FILE_ROLE: Async task entry points for the core app.

KEY_COMPONENTS:
- _fetch_openrouter_generation_data: Private helper.
- _process_ai_usage_for_generation: Private helper.
- _create_ai_usage_from_generation: Private helper.
- _process_ai_usage_message: Private helper.

INTERACTIONS:
- Depends on: nearby Django models, services, serializers, and the app packages imported by this module.

AI_GUIDELINES:
- Keep the module focused on its narrow layer boundary and avoid moving cross-cutting workflow code here.
- Preserve the existing API/model contract because other modules import these symbols directly.
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any

import requests
from core.services.ai_runtime_settings_service import AIRuntimeSettingsService
from core.services.ai_usage_service import AIUsageService
from core.services.logger_service import Logger
from core.tasks.runtime import QUEUE_DEFAULT, db_task
from django.conf import settings

logger = Logger.get_logger(__name__)


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _extract_openrouter_generation_payload(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    data = payload.get("data", payload)
    if isinstance(data, list):
        if not data:
            return None
        data = data[0]
    if not isinstance(data, dict):
        return None
    return data


def _fetch_openrouter_generation_data(request_id: str) -> dict[str, Any]:
    api_key = getattr(settings, "OPENROUTER_API_KEY", None)
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured.")

    base_url = str(AIRuntimeSettingsService.get("OPENROUTER_API_BASE_URL") or "https://openrouter.ai/api/v1").rstrip(
        "/"
    )
    timeout = float(getattr(settings, "OPENROUTER_USAGE_FETCH_TIMEOUT", 10.0))
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}

    candidate_calls = [
        (f"{base_url}/generation", {"id": request_id}),
        (f"{base_url}/generation/{request_id}", None),
    ]

    last_error: Exception | None = None

    for attempt in range(4):
        for url, params in candidate_calls:
            try:
                response = requests.get(url, headers=headers, params=params, timeout=timeout)
            except requests.RequestException as exc:
                last_error = exc
                continue

            if response.status_code == 404:
                continue
            if response.status_code != 200:
                last_error = RuntimeError(
                    f"OpenRouter generation fetch failed ({response.status_code}): {(response.text or '')[:200]}"
                )
                continue

            try:
                payload = response.json()
            except ValueError as exc:
                last_error = exc
                continue

            data = _extract_openrouter_generation_payload(payload)
            if data is None:
                last_error = RuntimeError("OpenRouter generation payload missing object data.")
                continue

            prompt_tokens = _to_int(
                data.get("tokens_prompt")
                or data.get("tokensPrompt")
                or data.get("native_tokens_prompt")
                or data.get("nativeTokensPrompt")
            )
            completion_tokens = _to_int(
                data.get("tokens_completion")
                or data.get("tokensCompletion")
                or data.get("native_tokens_completion")
                or data.get("nativeTokensCompletion")
            )
            total_tokens = _to_int(data.get("total_tokens") or data.get("totalTokens") or data.get("tokensTotal"))
            if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
                total_tokens = prompt_tokens + completion_tokens

            # Use `.get()` then explicit None-check to avoid `or` swallowing 0 (free model)
            raw_cost = data.get("total_cost")
            if raw_cost is None:
                raw_cost = data.get("totalCost")

            usage_data = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "cost_usd": _to_decimal(raw_cost),
            }
            return {
                "model": data.get("model"),
                "usage_data": usage_data,
            }

        # If we got here, none of the candidate URLs succeeded
        if attempt < 3:
            time.sleep(5.0)  # Wait before retrying; OpenRouter may need up to 20s to index

    if last_error:
        raise last_error
    raise RuntimeError("OpenRouter generation endpoint did not return usable data.")


@db_task(queue=QUEUE_DEFAULT)
def capture_ai_usage_task(
    *,
    feature: str,
    provider: str,
    model: str,
    request_type: str = "chat.completions",
    request_id: str | None = None,
    usage_data: dict[str, Any] | None = None,
    success: bool = True,
    error_type: str = "",
    latency_ms: int | None = None,
) -> dict[str, Any]:
    """
    Best-effort async usage capture.

    Non-critical task: any provider/API failure is logged and swallowed.
    """
    provider_key = (provider or "unknown").lower()

    try:
        normalized_usage_data: dict[str, Any] = dict(usage_data or {})
        resolved_model = model or "unknown"
        usage_source = "response.usage" if normalized_usage_data else "none"

        if provider_key == "openrouter":
            if request_id:
                try:
                    generation_data = _fetch_openrouter_generation_data(request_id=request_id)
                    generation_usage_data = generation_data.get("usage_data") or {}
                    if generation_usage_data:
                        normalized_usage_data = generation_usage_data
                        usage_source = "openrouter.generation"
                    if generation_data.get("model"):
                        resolved_model = generation_data["model"]
                except Exception as exc:
                    logger.warning(
                        "OpenRouter generation fetch failed for request_id=%s; recording fallback usage data instead: %s",
                        request_id,
                        str(exc),
                    )
            else:
                logger.warning(
                    "OpenRouter usage capture missing request_id for feature=%s model=%s; recording fallback usage data.",
                    feature,
                    model,
                )

        AIUsageService.record_request(
            feature=feature,
            provider=provider_key,
            model=resolved_model,
            request_id=request_id,
            usage_data=normalized_usage_data or None,
            request_type=request_type,
            success=success,
            error_type=error_type,
            latency_ms=latency_ms,
        )
        return {"status": "ok", "usage_source": usage_source}
    except Exception as exc:
        logger.warning(
            "AI usage capture task failed for provider=%s request_id=%s: %s",
            provider_key,
            request_id,
            str(exc),
        )
        return {"status": "failed", "error": str(exc)}
