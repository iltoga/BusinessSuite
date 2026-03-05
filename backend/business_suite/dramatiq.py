from __future__ import annotations

import os
from urllib.parse import urlparse, urlunparse

import django
import dramatiq
from django.apps import apps
from django.conf import settings
from dramatiq.brokers.redis import RedisBroker
from dramatiq.results import Results
from dramatiq.results.backends.redis import RedisBackend

from core.telemetry.dramatiq_tracing import DramatiqTracingMiddleware

_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _setting_or_env(name: str, default: str = "") -> str:
    value = default

    configured = getattr(settings, name, None)
    if configured is not None and str(configured).strip() != "":
        value = configured

    env_value = os.getenv(name)
    if env_value is not None and str(env_value).strip() != "":
        value = env_value

    db_value = None
    if apps.ready:
        from core.services.app_setting_service import AppSettingService

        db_value = AppSettingService.get_raw(name, default=None, require_override=True)
    if db_value is not None and str(db_value).strip() != "":
        value = db_value

    return str(value)


def _running_in_docker() -> bool:
    return os.path.exists("/.dockerenv")


def _normalize_host(host: str, *, docker_default: str = "bs-redis") -> str:
    text = str(host or "").strip()
    if _running_in_docker() and text in _LOOPBACK_HOSTS:
        return docker_default
    return text


def _normalize_redis_url(redis_url: str) -> str:
    text = str(redis_url or "").strip()
    if not text:
        return text

    parsed = urlparse(text)
    host = parsed.hostname or ""
    normalized_host = _normalize_host(host)
    if not host or normalized_host == host:
        return text

    netloc = ""
    if parsed.username is not None:
        netloc += parsed.username
        if parsed.password is not None:
            netloc += f":{parsed.password}"
        netloc += "@"
    netloc += normalized_host
    if parsed.port is not None:
        netloc += f":{parsed.port}"

    return urlunparse(parsed._replace(netloc=netloc))


def _build_redis_url() -> str:
    desired_db = int(getattr(settings, "DRAMATIQ_REDIS_DB", 0) or 0)

    # Prefer explicit Dramatiq URL when provided.
    redis_url = _normalize_redis_url(_setting_or_env("DRAMATIQ_REDIS_URL", ""))
    if redis_url:
        parsed = urlparse(redis_url)
        return urlunparse(parsed._replace(path=f"/{desired_db}"))

    # Preserve credentials/TLS/query params when REDIS_URL is configured.
    redis_url = _normalize_redis_url(_setting_or_env("REDIS_URL", ""))
    if redis_url:
        parsed = urlparse(redis_url)
        return urlunparse(parsed._replace(path=f"/{desired_db}"))

    # Fallback to host/port only when full URLs are not provided.
    raw_host = _setting_or_env("REDIS_HOST", "")
    host = _normalize_host(raw_host) if raw_host else ""
    port = int(_setting_or_env("REDIS_PORT", "6379") or 6379)
    if host:
        return f"redis://{host}:{port}/{desired_db}"

    return f"redis://{_normalize_host('localhost')}:{port}/{desired_db}"


def _build_results_redis_url() -> str:
    redis_url = _normalize_redis_url(_setting_or_env("DRAMATIQ_RESULTS_REDIS_URL", ""))
    if redis_url:
        return redis_url
    return _build_redis_url()


def setup() -> RedisBroker:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", os.getenv("DJANGO_SETTINGS_MODULE", "business_suite.settings.prod"))
    if not apps.ready and not apps.loading:
        django.setup()

    broker = RedisBroker(
        url=_build_redis_url(),
        namespace=str(getattr(settings, "DRAMATIQ_NAMESPACE", "dramatiq:queue") or "dramatiq:queue"),
    )
    broker.add_middleware(DramatiqTracingMiddleware())
    if bool(getattr(settings, "DRAMATIQ_RESULTS_ENABLED", True)):
        broker.add_middleware(
            Results(
                backend=RedisBackend(
                    url=_build_results_redis_url(),
                    namespace=str(
                        getattr(settings, "DRAMATIQ_RESULTS_NAMESPACE", "dramatiq:results")
                        or "dramatiq:results"
                    ),
                ),
                store_results=bool(getattr(settings, "DRAMATIQ_RESULTS_STORE_RESULTS", True)),
                result_ttl=int(getattr(settings, "DRAMATIQ_RESULTS_TTL_MS", 300000) or 300000),
            )
        )
    dramatiq.set_broker(broker)

    # Import actors so dramatiq can discover them.
    from core.tasks import (  # noqa: F401
        ai_usage,
        calendar_reminders,
        calendar_sync,
        cron_jobs,
        document_categorization,
        document_ocr,
        document_validation,
        local_resilience,
        ocr,
    )
    from admin_tools import tasks as admin_tasks  # noqa: F401
    from customer_applications import tasks as customer_application_tasks  # noqa: F401
    from customers import tasks as customer_tasks  # noqa: F401
    from invoices.tasks import document_jobs, download_jobs, import_jobs  # noqa: F401
    from products.tasks import product_excel_jobs  # noqa: F401

    return broker


broker = setup()
