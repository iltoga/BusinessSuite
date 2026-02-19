from __future__ import annotations

import logging
import time
from typing import Any

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

META_RUNTIME_ACCESS_TOKEN_CACHE_KEY = "meta_whatsapp:runtime_access_token"
META_RUNTIME_ACCESS_TOKEN_EXPIRES_AT_CACHE_KEY = "meta_whatsapp:runtime_access_token_expires_at"


def _safe_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _now_epoch() -> int:
    return int(time.time())


def _refresh_enabled() -> bool:
    return bool(getattr(settings, "META_WHATSAPP_AUTO_REFRESH_ACCESS_TOKEN", True))


def _refresh_window_seconds() -> int:
    configured = _safe_int(getattr(settings, "META_WHATSAPP_TOKEN_REFRESH_WINDOW_SECONDS", 7 * 24 * 60 * 60))
    return configured if configured is not None and configured >= 0 else 0


def _cache_timeout_seconds() -> int:
    configured = _safe_int(getattr(settings, "META_WHATSAPP_TOKEN_CACHE_TIMEOUT_SECONDS", 70 * 24 * 60 * 60))
    return configured if configured is not None and configured > 0 else 70 * 24 * 60 * 60


def _base_configured_token() -> str:
    return str(getattr(settings, "META_WHATSAPP_ACCESS_TOKEN", "") or "").strip()


def _runtime_cached_token() -> str:
    return str(cache.get(META_RUNTIME_ACCESS_TOKEN_CACHE_KEY) or "").strip()


def _runtime_cached_expires_at() -> int | None:
    return _safe_int(cache.get(META_RUNTIME_ACCESS_TOKEN_EXPIRES_AT_CACHE_KEY))


def get_meta_whatsapp_access_token(*, force_refresh: bool = False) -> str:
    """Return active Meta access token, refreshing when needed/forced."""
    base_token = _base_configured_token()
    if not base_token:
        return ""

    token = _runtime_cached_token() or base_token
    if not _refresh_enabled():
        return token

    expires_at = _runtime_cached_expires_at()
    should_refresh = force_refresh
    if not should_refresh and expires_at is not None and expires_at > 0:
        should_refresh = _now_epoch() >= max(0, expires_at - _refresh_window_seconds())

    if not should_refresh:
        return token

    refreshed = refresh_meta_whatsapp_access_token(current_token=token)
    return refreshed or token


def refresh_meta_whatsapp_access_token(*, current_token: str | None = None) -> str | None:
    """Refresh Meta access token via OAuth token exchange endpoint."""
    app_id = str(getattr(settings, "META_APP_ID", "") or "").strip()
    app_secret = str(getattr(settings, "META_APP_SECRET", "") or "").strip()
    graph_version = str(getattr(settings, "META_GRAPH_API_VERSION", "v23.0") or "v23.0").strip()
    token = str(current_token or _runtime_cached_token() or _base_configured_token()).strip()

    if not token:
        return None
    if not app_id or not app_secret:
        logger.warning("Meta token refresh skipped: META_APP_ID or META_APP_SECRET is missing.")
        return None

    response = requests.get(
        f"https://graph.facebook.com/{graph_version}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": token,
            "set_token_expires_in_60_days": "true",
        },
        timeout=20,
    )
    if response.status_code >= 400:
        logger.error(
            "Meta token refresh failed: status=%s body=%s",
            response.status_code,
            response.text,
        )
        return None

    data = response.json() or {}
    new_token = str(data.get("access_token") or "").strip()
    if not new_token:
        logger.error("Meta token refresh failed: response does not include access_token.")
        return None

    expires_in = _safe_int(data.get("expires_in"))
    cache_timeout = _cache_timeout_seconds()
    cache.set(META_RUNTIME_ACCESS_TOKEN_CACHE_KEY, new_token, timeout=cache_timeout)
    setattr(settings, "META_WHATSAPP_ACCESS_TOKEN", new_token)
    if expires_in is not None and expires_in > 0:
        cache.set(
            META_RUNTIME_ACCESS_TOKEN_EXPIRES_AT_CACHE_KEY,
            _now_epoch() + expires_in,
            timeout=cache_timeout,
        )
    else:
        cache.delete(META_RUNTIME_ACCESS_TOKEN_EXPIRES_AT_CACHE_KEY)

    return new_token


def reset_meta_whatsapp_access_token_cache() -> None:
    cache.delete_many([META_RUNTIME_ACCESS_TOKEN_CACHE_KEY, META_RUNTIME_ACCESS_TOKEN_EXPIRES_AT_CACHE_KEY])
