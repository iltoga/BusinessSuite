"""
FILE_ROLE: Signal handlers for calendar reminder lifecycle events.

KEY_COMPONENTS:
- calendar_reminder_post_save: Module symbol.
- calendar_reminder_post_delete: Module symbol.

INTERACTIONS:
- Depends on: core.models, core.services, Django signal machinery, or middleware hooks as appropriate.

AI_GUIDELINES:
- Keep this module focused on framework integration and small hook functions.
- Do not move domain orchestration here when a service already owns the workflow.
"""

from core.models import CalendarReminder
from core.services.calendar_reminder_stream import bump_calendar_reminder_stream_cursor
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver


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
