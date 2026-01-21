import datetime
import logging
from typing import Iterable, Tuple

from django.conf import settings
from django.core.management import call_command
from huey import crontab
from huey.contrib.djhuey import db_periodic_task, db_task

logger = logging.getLogger(__name__)


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


_register_full_backup()
_register_clear_cache()
