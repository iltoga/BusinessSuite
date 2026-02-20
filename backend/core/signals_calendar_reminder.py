from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from core.models import CalendarReminder
from core.services.calendar_reminder_stream import bump_calendar_reminder_stream_cursor


@receiver(post_save, sender=CalendarReminder, dispatch_uid="calendar_reminder_stream_post_save")
def calendar_reminder_post_save(sender, instance, created, **kwargs):
    bump_calendar_reminder_stream_cursor(
        reminder_id=instance.id,
        owner_id=instance.created_by_id,
        operation="created" if created else "updated",
    )


@receiver(post_delete, sender=CalendarReminder, dispatch_uid="calendar_reminder_stream_post_delete")
def calendar_reminder_post_delete(sender, instance, **kwargs):
    bump_calendar_reminder_stream_cursor(
        reminder_id=instance.id,
        owner_id=instance.created_by_id,
        operation="deleted",
    )
