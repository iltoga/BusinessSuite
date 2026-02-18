import datetime
import logging
from typing import Iterable, Tuple

import requests
from django.conf import settings
from django.core.management import call_command
from huey import crontab
from huey.contrib.djhuey import db_periodic_task, db_task

from core.services.logger_service import Logger

logger = Logger.get_logger(__name__)


def _parse_time(value: str) -> Tuple[int, int]:
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time format '{value}'. Expected HH:MM.")

    hour = int(parts[0])
    minute = int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Invalid time value '{value}'. Expected HH:MM in 24h format.")

    return hour, minute


def _perform_full_backup() -> None:
    call_command("dbbackup")
    logger.info("DB Backup created successfully")
    dir_name = "media_" + datetime.date.today().strftime("%Y%m%d")
    call_command("uploadmediatodropbox", dir_name)
    logger.info("Media files uploaded successfully")


def _perform_clear_cache() -> None:
    call_command("clear_cache")
    logger.info("Cache cleared successfully")


@db_task()
def run_full_backup_now() -> None:
    _perform_full_backup()


@db_task()
def run_clear_cache_now() -> None:
    _perform_clear_cache()


@db_task()
def run_auditlog_prune_now() -> None:
    """Immediate task to prune auditlog DB entries older than configured retention."""
    _perform_prune_auditlog()


@db_task()
def run_openrouter_health_check_now() -> None:
    """Immediate task to run OpenRouter API health check."""
    _perform_openrouter_health_check()


def _register_full_backup() -> None:
    schedule = getattr(settings, "FULL_BACKUP_SCHEDULE", "02:00")
    try:
        hour, minute = _parse_time(schedule)
    except ValueError as exc:
        logger.error(str(exc))
        return

    @db_periodic_task(crontab(hour=hour, minute=minute), name="core.full_backup_daily")
    def _full_backup_daily() -> None:
        _perform_full_backup()

    globals()["_full_backup_daily"] = _full_backup_daily


def _register_clear_cache() -> None:
    schedules: Iterable[str] = getattr(settings, "CLEAR_CACHE_SCHEDULE", ["03:00"])
    for schedule in schedules:
        try:
            hour, minute = _parse_time(schedule)
        except ValueError as exc:
            logger.error(str(exc))
            continue

        task_name = f"core.clear_cache_{hour:02d}{minute:02d}"

        @db_periodic_task(crontab(hour=hour, minute=minute), name=task_name)
        def _clear_cache_scheduled() -> None:
            _perform_clear_cache()

        globals()[f"_clear_cache_{hour:02d}{minute:02d}"] = _clear_cache_scheduled


def _perform_prune_auditlog() -> None:
    """Prune `auditlog.LogEntry` rows older than `AUDITLOG_RETENTION_DAYS`.

    This uses the built-in management command `auditlogflush --before-date` to delete
    old log entries. If `AUDITLOG_RETENTION_DAYS` is <= 0 the pruning is skipped.
    """
    retention_days = getattr(settings, "AUDITLOG_RETENTION_DAYS", 14)
    if retention_days <= 0:
        logger.info("AUDITLOG_RETENTION_DAYS is <= 0; skipping audit log pruning.")
        return

    cutoff_date = datetime.date.today() - datetime.timedelta(days=retention_days)
    try:
        call_command("auditlogflush", before_date=cutoff_date.isoformat(), yes=True)
        logger.info("Pruned auditlog LogEntry objects before %s", cutoff_date.isoformat())
    except Exception as exc:
        logger.error("Failed to prune auditlog entries: %s", str(exc), exc_info=True)


def _register_auditlog_prune() -> None:
    schedule = getattr(settings, "AUDITLOG_RETENTION_SCHEDULE", "04:00")
    if not schedule:
        # Explicitly disabled
        return

    try:
        hour, minute = _parse_time(schedule)
    except ValueError as exc:
        logger.error(str(exc))
        return

    @db_periodic_task(crontab(hour=hour, minute=minute), name="core.auditlog_prune_daily")
    def _auditlog_prune_daily() -> None:
        _perform_prune_auditlog()

    globals()["_auditlog_prune_daily"] = _auditlog_prune_daily


def _perform_openrouter_health_check() -> bool:
    """
    Check OpenRouter API health using GET /api/v1/key.

    This endpoint validates connectivity and authentication and returns usage/limit metadata.
    """
    if not getattr(settings, "OPENROUTER_HEALTHCHECK_ENABLED", True):
        logger.info("OpenRouter health check is disabled by settings.")
        return True

    api_key = getattr(settings, "OPENROUTER_API_KEY", None)
    if not api_key:
        logger.warning("OpenRouter health check skipped: OPENROUTER_API_KEY is not configured.")
        return False

    base_url = getattr(settings, "OPENROUTER_API_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    timeout = float(getattr(settings, "OPENROUTER_HEALTHCHECK_TIMEOUT", 10.0))
    endpoint = f"{base_url}/key"

    try:
        response = requests.get(
            endpoint,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
            timeout=timeout,
        )
    except requests.RequestException as exc:
        logger.error("OpenRouter health check request failed: %s", str(exc))
        return False

    if response.status_code != 200:
        body_excerpt = (response.text or "").replace("\n", " ").strip()[:200]
        logger.error(
            "OpenRouter health check failed (HTTP %s). Response: %s",
            response.status_code,
            body_excerpt or "<empty>",
        )
        return False

    try:
        payload = response.json()
    except ValueError as exc:
        logger.error("OpenRouter health check returned invalid JSON: %s", str(exc))
        return False

    remaining = None
    min_remaining = float(getattr(settings, "OPENROUTER_HEALTHCHECK_MIN_CREDIT_REMAINING", 0.0))
    if not isinstance(payload, dict):
        logger.error("OpenRouter health check returned a non-object JSON payload.")
        return False

    data = payload.get("data")
    if not isinstance(data, dict):
        logger.error("OpenRouter health check response is missing the data object.")
        return False

    remaining = data.get("limit_remaining")
    if "limit_remaining" not in data:
        logger.error("OpenRouter health check response is missing data.limit_remaining.")
        return False

    if remaining is not None:
        try:
            remaining_value = float(remaining)
        except (TypeError, ValueError):
            logger.error("OpenRouter health check returned non-numeric limit_remaining=%r", remaining)
            return False

        if remaining_value <= min_remaining:
            logger.error(
                "OpenRouter health check failed: low credit remaining (limit_remaining=%s, threshold=%s)",
                remaining_value,
                min_remaining,
            )
            return False

    logger.info(
        "OpenRouter health check OK (limit_remaining=%s, threshold=%s)",
        remaining if remaining is not None else "n/a",
        min_remaining,
    )
    return True


def _register_openrouter_health_check() -> None:
    if not getattr(settings, "OPENROUTER_HEALTHCHECK_ENABLED", True):
        return

    minute_expr = getattr(settings, "OPENROUTER_HEALTHCHECK_CRON_MINUTE", "*/5")
    try:
        schedule = crontab(minute=minute_expr)
    except Exception as exc:
        logger.error("Invalid OPENROUTER_HEALTHCHECK_CRON_MINUTE '%s': %s", minute_expr, str(exc))
        return

    @db_periodic_task(schedule, name="core.openrouter_health_check")
    def _openrouter_health_check_periodic() -> None:
        _perform_openrouter_health_check()

    globals()["_openrouter_health_check_periodic"] = _openrouter_health_check_periodic


_register_full_backup()
_register_clear_cache()
_register_auditlog_prune()
_register_openrouter_health_check()
