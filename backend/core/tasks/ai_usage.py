from __future__ import annotations

from decimal import Decimal
from typing import Any

import requests
from django.conf import settings
from huey.contrib.djhuey import db_task

from core.services.ai_usage_service import AIUsageService
from core.services.logger_service import Logger

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

    base_url = getattr(settings, "OPENROUTER_API_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    timeout = float(getattr(settings, "OPENROUTER_USAGE_FETCH_TIMEOUT", 10.0))
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}

    candidate_calls = [
        (f"{base_url}/generation", {"id": request_id}),
        (f"{base_url}/generation/{request_id}", None),
    ]

    last_error: Exception | None = None
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

        prompt_tokens = _to_int(data.get("tokensPrompt") or data.get("tokens_prompt") or data.get("nativeTokensPrompt"))
        completion_tokens = _to_int(data.get("tokensCompletion") or data.get("tokens_completion"))
        total_tokens = _to_int(data.get("totalTokens") or data.get("tokensTotal") or data.get("total_tokens"))
        if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
            total_tokens = prompt_tokens + completion_tokens

        usage_data = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cost_usd": _to_decimal(data.get("totalCost") or data.get("total_cost")),
        }
        return {
            "model": data.get("model"),
            "usage_data": usage_data,
        }

    if last_error:
        raise last_error
    raise RuntimeError("OpenRouter generation endpoint did not return usable data.")


@db_task()
def capture_ai_usage_task(
    *,
    feature: str,
    provider: str,
    model: str,
    request_type: str = "chat.completions",
    request_id: str | None = None,
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
        usage_data: dict[str, Any] | None = None
        resolved_model = model or "unknown"

        if provider_key == "openrouter":
            if not request_id:
                logger.warning(
                    "Skipping OpenRouter usage capture: missing request_id for feature=%s model=%s",
                    feature,
                    model,
                )
                return {"status": "skipped", "reason": "missing_request_id"}

            generation_data = _fetch_openrouter_generation_data(request_id=request_id)
            usage_data = generation_data.get("usage_data") or {}
            if generation_data.get("model"):
                resolved_model = generation_data["model"]

        AIUsageService.record_request(
            feature=feature,
            provider=provider_key,
            model=resolved_model,
            request_id=request_id,
            usage_data=usage_data,
            request_type=request_type,
            success=success,
            error_type=error_type,
            latency_ms=latency_ms,
        )
        return {"status": "ok"}
    except Exception as exc:
        logger.warning(
            "AI usage capture task failed for provider=%s request_id=%s: %s",
            provider_key,
            request_id,
            str(exc),
        )
        return {"status": "failed", "error": str(exc)}
