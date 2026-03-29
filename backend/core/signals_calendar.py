"""
FILE_ROLE: Signal handlers for calendar lifecycle events.

KEY_COMPONENTS:
- _send_calendar_task: Module symbol.
- _log_dispatched_message: Module symbol.
- _mark_calendar_sync_dispatch_failed: Module symbol.
- queue_calendar_event_sync: Module symbol.
- queue_calendar_event_delete: Module symbol.

INTERACTIONS:
- Depends on: core.models, core.services, Django signal machinery, or middleware hooks as appropriate.

AI_GUIDELINES:
- Keep this module focused on framework integration and small hook functions.
- Do not move domain orchestration here when a service already owns the workflow.
"""

import logging

import dramatiq
from core.models.calendar_event import CalendarEvent
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger(__name__)

CREATE_GOOGLE_EVENT_TASK_NAME = "core.tasks.calendar_sync.create_google_event_task"
UPDATE_GOOGLE_EVENT_TASK_NAME = "core.tasks.calendar_sync.update_google_event_task"
DELETE_GOOGLE_EVENT_TASK_NAME = "core.tasks.calendar_sync.delete_google_event_task"


def _send_calendar_task(actor_name: str, **kwargs):
    actor = dramatiq.get_broker().get_actor(actor_name)
    return actor.send(**kwargs)


def _log_dispatched_message(task_name: str, message, **kwargs):
    logger.debug(
        "calendar_task_dispatched task=%s message_id=%s queue=%s kwargs=%s",
        task_name,
        getattr(message, "message_id", None),
        getattr(message, "queue_name", None),
        kwargs,
    )


def _mark_calendar_sync_dispatch_failed(event_id: str, *, task_name: str, exc: Exception) -> None:
    error_message = f"{task_name} enqueue failed: {type(exc).__name__}: {exc}"
    CalendarEvent.objects.filter(pk=event_id).update(
        sync_status=CalendarEvent.SYNC_STATUS_FAILED,
        sync_error=error_message,
        updated_at=timezone.now(),
    )


@receiver(post_save, sender=CalendarEvent)
def queue_calendar_event_sync(sender, instance: CalendarEvent, created: bool, raw: bool = False, **kwargs):
    if raw:
        return

    def _enqueue():
        task_name = "create_google_event_task" if created else "update_google_event_task"
        actor_name = CREATE_GOOGLE_EVENT_TASK_NAME if created else UPDATE_GOOGLE_EVENT_TASK_NAME
        logger.debug(
            "calendar_sync_enqueue event_id=%s created=%s google_event_id=%s calendar_id=%s",
            instance.pk,
            created,
            instance.google_event_id,
            instance.google_calendar_id,
        )
        try:
            message = _send_calendar_task(actor_name, event_id=instance.pk)
            _log_dispatched_message(task_name, message, event_id=instance.pk)
        except Exception as exc:
            _mark_calendar_sync_dispatch_failed(instance.pk, task_name=task_name, exc=exc)
            logger.error(
                "calendar_sync_dispatch_failed event_id=%s created=%s error_type=%s error=%s",
                instance.pk,
                created,
                type(exc).__name__,
                str(exc),
            )

    try:
        transaction.on_commit(_enqueue)
    except Exception as exc:
        _mark_calendar_sync_dispatch_failed(
            instance.pk,
            task_name="create_google_event_task" if created else "update_google_event_task",
            exc=exc,
        )
        logger.error(
            "calendar_sync_enqueue_failed event_id=%s created=%s error_type=%s error=%s",
            instance.pk,
            created,
            type(exc).__name__,
            str(exc),
        )


@receiver(post_delete, sender=CalendarEvent)
def queue_calendar_event_delete(sender, instance: CalendarEvent, **kwargs):
    google_event_id = (instance.google_event_id or "").strip()
    google_calendar_id = (instance.google_calendar_id or "").strip() or None

    def _enqueue():
        if google_event_id:
            delete_kwargs = {"google_event_id": google_event_id}
            if google_calendar_id:
                delete_kwargs["google_calendar_id"] = google_calendar_id
        else:
            delete_kwargs = {
                "event_id": instance.pk,
                "title": instance.title or "",
                "extended_properties": instance.extended_properties or {},
            }
            if instance.start_date:
                delete_kwargs["start_date"] = (
                    instance.start_date.isoformat()
                    if hasattr(instance.start_date, "isoformat")
                    else str(instance.start_date)
                )
            if google_calendar_id:
                delete_kwargs["google_calendar_id"] = google_calendar_id
        logger.debug(
            "calendar_delete_enqueue event_id=%s google_event_id=%s calendar_id=%s",
            instance.pk,
            google_event_id,
            google_calendar_id,
        )
        try:
            message = _send_calendar_task(DELETE_GOOGLE_EVENT_TASK_NAME, **delete_kwargs)
            _log_dispatched_message("delete_google_event_task", message, **delete_kwargs)
        except Exception as exc:
            logger.error(
                "calendar_delete_dispatch_failed event_id=%s google_event_id=%s error_type=%s error=%s",
                instance.pk,
                google_event_id,
                type(exc).__name__,
                str(exc),
            )

    try:
        transaction.on_commit(_enqueue)
    except Exception as exc:
        logger.error(
            "calendar_delete_enqueue_failed event_id=%s google_event_id=%s error_type=%s error=%s",
            instance.pk,
            google_event_id,
            type(exc).__name__,
            str(exc),
        )
