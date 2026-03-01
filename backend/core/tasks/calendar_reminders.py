import logging

from django.conf import settings

from core.queue import enqueue_job
from core.services.calendar_reminder_service import CalendarReminderService

logger = logging.getLogger(__name__)

ENTRYPOINT_DISPATCH_DUE_CALENDAR_REMINDERS_TASK = "core.dispatch_due_calendar_reminders"


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


def dispatch_due_calendar_reminders_task(*, limit: int | None = None) -> dict[str, int]:
    return _dispatch_due_calendar_reminders(limit=limit)


def enqueue_dispatch_due_calendar_reminders_task(*, limit: int | None = None) -> str | None:
    return enqueue_job(
        entrypoint=ENTRYPOINT_DISPATCH_DUE_CALENDAR_REMINDERS_TASK,
        payload={"limit": limit},
        run_local=dispatch_due_calendar_reminders_task,
    )
