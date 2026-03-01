import logging

from core.models.calendar_event import CalendarEvent
from core.tasks.calendar_sync import (
    enqueue_create_google_event_task,
    enqueue_delete_google_event_task,
    enqueue_update_google_event_task,
)
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender=CalendarEvent)
def queue_calendar_event_sync(sender, instance: CalendarEvent, created: bool, raw: bool = False, **kwargs):
    if raw:
        return

    def _enqueue():
        logger.debug(
            "calendar_sync_enqueue event_id=%s created=%s google_event_id=%s calendar_id=%s",
            instance.pk,
            created,
            instance.google_event_id,
            instance.google_calendar_id,
        )
        if created:
            enqueue_create_google_event_task(event_id=str(instance.pk))
        else:
            enqueue_update_google_event_task(event_id=str(instance.pk))

    try:
        transaction.on_commit(_enqueue)
    except Exception as exc:
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
    if not google_event_id:
        return
    google_calendar_id = (instance.google_calendar_id or "").strip() or None

    def _enqueue():
        delete_kwargs = {"google_event_id": google_event_id}
        if google_calendar_id:
            delete_kwargs["google_calendar_id"] = google_calendar_id
        logger.debug(
            "calendar_delete_enqueue event_id=%s google_event_id=%s calendar_id=%s",
            instance.pk,
            google_event_id,
            google_calendar_id,
        )
        enqueue_delete_google_event_task(**delete_kwargs)

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
