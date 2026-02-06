import datetime
import logging
from typing import Iterable, Tuple

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


_register_full_backup()
_register_clear_cache()
_register_auditlog_prune()
