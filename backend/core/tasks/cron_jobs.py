import datetime
import uuid
from typing import Iterable, Tuple

import requests
from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from huey import crontab
from huey.contrib.djhuey import db_periodic_task, db_task

from core.services.logger_service import Logger

logger = Logger.get_logger(__name__)

FULL_BACKUP_ENQUEUE_LOCK_KEY = "cron:full_backup:enqueue_lock"
FULL_BACKUP_RUN_LOCK_KEY = "cron:full_backup:run_lock"
CLEAR_CACHE_ENQUEUE_LOCK_KEY = "cron:clear_cache:enqueue_lock"
CLEAR_CACHE_RUN_LOCK_KEY = "cron:clear_cache:run_lock"


def _parse_time(value: str) -> Tuple[int, int]:
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time format '{value}'. Expected HH:MM.")

    hour = int(parts[0])
    minute = int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Invalid time value '{value}'. Expected HH:MM in 24h format.")

    return hour, minute


def _coerce_positive_int(value, default: int) -> int:
    try:
        parsed = int(value)
        if parsed > 0:
            return parsed
    except (TypeError, ValueError):
        pass
    return default


def _full_backup_lock_ttl_seconds() -> int:
    return _coerce_positive_int(getattr(settings, "FULL_BACKUP_LOCK_TTL_SECONDS", 6 * 60 * 60), 6 * 60 * 60)


def _clear_cache_lock_ttl_seconds() -> int:
    return _coerce_positive_int(getattr(settings, "CLEAR_CACHE_LOCK_TTL_SECONDS", 15 * 60), 15 * 60)


def _acquire_cache_lock(lock_key: str, ttl_seconds: int) -> str | None:
    token = uuid.uuid4().hex
    acquired = cache.add(lock_key, token, timeout=max(1, ttl_seconds))
    return token if acquired else None


def _release_cache_lock(lock_key: str, token: str) -> None:
    current = cache.get(lock_key)
    if current == token:
        cache.delete(lock_key)


def reset_privileged_cron_job_locks() -> None:
    cache.delete_many(
        [
            FULL_BACKUP_ENQUEUE_LOCK_KEY,
            FULL_BACKUP_RUN_LOCK_KEY,
            CLEAR_CACHE_ENQUEUE_LOCK_KEY,
            CLEAR_CACHE_RUN_LOCK_KEY,
        ]
    )


def _enqueue_task_once(*, task, task_name: str, enqueue_lock_key: str, lock_ttl_seconds: int) -> bool:
    token = _acquire_cache_lock(enqueue_lock_key, lock_ttl_seconds)
    if not token:
        logger.info("%s trigger ignored: task already queued/running", task_name)
        return False

    try:
        task.delay()
        logger.info("%s enqueued", task_name)
        return True
    except Exception:
        _release_cache_lock(enqueue_lock_key, token)
        raise


def _run_locked_task(
    *,
    task_name: str,
    enqueue_lock_key: str,
    run_lock_key: str,
    lock_ttl_seconds: int,
    perform_fn,
) -> bool:
    run_token = _acquire_cache_lock(run_lock_key, lock_ttl_seconds)
    if not run_token:
        logger.info("%s execution skipped: already running", task_name)
        return False

    enqueue_running_marker = f"running:{run_token}"
    cache.set(enqueue_lock_key, enqueue_running_marker, timeout=max(1, lock_ttl_seconds))

    try:
        perform_fn()
        logger.info("%s execution completed", task_name)
        return True
    finally:
        _release_cache_lock(run_lock_key, run_token)
        if cache.get(enqueue_lock_key) == enqueue_running_marker:
            cache.delete(enqueue_lock_key)


def _perform_full_backup() -> None:
    call_command("dbbackup")
    logger.info("DB Backup created successfully")
    dir_name = "media_" + datetime.date.today().strftime("%Y%m%d")
    call_command("uploadmediatos3", dir_name)
    logger.info("Media files uploaded successfully")


def _perform_clear_cache() -> None:
    call_command("clear_cache")
    logger.info("Cache cleared successfully")


def _perform_full_backup_locked() -> bool:
    return _run_locked_task(
        task_name="FullBackupJob",
        enqueue_lock_key=FULL_BACKUP_ENQUEUE_LOCK_KEY,
        run_lock_key=FULL_BACKUP_RUN_LOCK_KEY,
        lock_ttl_seconds=_full_backup_lock_ttl_seconds(),
        perform_fn=_perform_full_backup,
    )


def _perform_clear_cache_locked() -> bool:
    return _run_locked_task(
        task_name="ClearCacheJob",
        enqueue_lock_key=CLEAR_CACHE_ENQUEUE_LOCK_KEY,
        run_lock_key=CLEAR_CACHE_RUN_LOCK_KEY,
        lock_ttl_seconds=_clear_cache_lock_ttl_seconds(),
        perform_fn=_perform_clear_cache,
    )


@db_task()
def run_full_backup_now() -> None:
    _perform_full_backup_locked()


@db_task()
def run_clear_cache_now() -> None:
    _perform_clear_cache_locked()


def enqueue_full_backup_now() -> bool:
    return _enqueue_task_once(
        task=run_full_backup_now,
        task_name="FullBackupJob",
        enqueue_lock_key=FULL_BACKUP_ENQUEUE_LOCK_KEY,
        lock_ttl_seconds=_full_backup_lock_ttl_seconds(),
    )


def enqueue_clear_cache_now() -> bool:
    return _enqueue_task_once(
        task=run_clear_cache_now,
        task_name="ClearCacheJob",
        enqueue_lock_key=CLEAR_CACHE_ENQUEUE_LOCK_KEY,
        lock_ttl_seconds=_clear_cache_lock_ttl_seconds(),
    )


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
        _perform_full_backup_locked()

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
            _perform_clear_cache_locked()

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
