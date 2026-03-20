from __future__ import annotations

from typing import Any

from django.conf import settings

API_VERSION = getattr(settings, "API_VERSION", "v1")


def get_request_id(request: Any | None = None, *, fallback: str | None = None) -> str | None:
    if request is None:
        return fallback

    header_candidates = (
        "X-Request-ID",
        "X-Correlation-ID",
        "HTTP_X_REQUEST_ID",
        "HTTP_X_CORRELATION_ID",
    )
    for header_name in header_candidates:
        value = None
        if hasattr(request, "headers"):
            value = request.headers.get(header_name)
        if not value and hasattr(request, "META"):
            value = request.META.get(header_name)
        if value:
            value = str(value).strip()
            if value:
                return value

    attr_value = getattr(request, "request_id", None) or getattr(request, "correlation_id", None)
    if attr_value:
        value = str(attr_value).strip()
        if value:
            return value

    return fallback


def build_meta(
    request: Any | None = None,
    *,
    request_id: str | None = None,
    api_version: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    meta = {
        "request_id": get_request_id(request, fallback=request_id),
        "api_version": api_version or API_VERSION,
    }
    if extra:
        meta.update(extra)
    return meta


def build_success_payload(
    data: Any,
    request: Any | None = None,
    *,
    request_id: str | None = None,
    api_version: str | None = None,
    extra_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "data": data,
        "meta": build_meta(request, request_id=request_id, api_version=api_version, extra=extra_meta),
    }


def build_error_payload(
    *,
    code: str,
    message: str,
    details: Any | None = None,
    request: Any | None = None,
    request_id: str | None = None,
    api_version: str | None = None,
    extra_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {
        "code": code,
        "message": message,
    }
    if details is not None:
        error["details"] = details

    return {
        "error": error,
        "meta": build_meta(request, request_id=request_id, api_version=api_version, extra=extra_meta),
    }
