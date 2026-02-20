import logging

from django.conf import settings
from huey import crontab
from huey.contrib.djhuey import db_periodic_task, db_task

from core.services.calendar_reminder_service import CalendarReminderService

logger = logging.getLogger(__name__)


def _dispatch_due_calendar_reminders(*, limit: int | None = None) -> dict[str, int]:
    effective_limit = int(
        limit
        if limit is not None
        else getattr(settings, "CALENDAR_REMINDER_DISPATCH_LIMIT", 200)
    )
    stats = CalendarReminderService().dispatch_due_reminders(limit=effective_limit)
    payload = {
        "sent": int(stats.sent),
        "failed": int(stats.failed),
        "limit": effective_limit,
    }
    logger.info(
        "Calendar reminder dispatch completed: sent=%s failed=%s limit=%s",
        payload["sent"],
        payload["failed"],
        payload["limit"],
    )
    return payload


@db_task()
def dispatch_due_calendar_reminders_task(*, limit: int | None = None) -> dict[str, int]:
    return _dispatch_due_calendar_reminders(limit=limit)


@db_periodic_task(
    crontab(minute="*/1"),
    name="core.dispatch_due_calendar_reminders",
)
def dispatch_due_calendar_reminders_periodic_task() -> dict[str, int]:
    return _dispatch_due_calendar_reminders()
