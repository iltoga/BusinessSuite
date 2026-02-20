from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from typing import Iterable

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.models import CalendarReminder
from core.services.push_notifications import FcmConfigurationError, PushNotificationService

User = get_user_model()


@dataclass
class CalendarReminderDispatchStats:
    sent: int = 0
    failed: int = 0


class CalendarReminderService:
    def __init__(self, push_service: PushNotificationService | None = None):
        self.push_service = push_service or PushNotificationService()

    def create_for_users(
        self,
        *,
        created_by: User,
        user_ids: Iterable[int],
        reminder_date: date,
        reminder_time: time,
        timezone_name: str,
        content: str,
        calendar_event_id: str | None = None,
    ) -> list[CalendarReminder]:
        cleaned_user_ids = []
        for raw_user_id in user_ids:
            try:
                normalized = int(raw_user_id)
            except (TypeError, ValueError):
                continue
            if normalized not in cleaned_user_ids:
                cleaned_user_ids.append(normalized)

        if not cleaned_user_ids:
            raise ValidationError({"userIds": "At least one user must be selected."})

        users = User.objects.filter(is_active=True, id__in=cleaned_user_ids).order_by("id")
        found_user_ids = {int(user.id) for user in users}
        missing_user_ids = [user_id for user_id in cleaned_user_ids if user_id not in found_user_ids]
        if missing_user_ids:
            raise ValidationError({"userIds": f"User(s) not found or inactive: {missing_user_ids}"})

        reminders: list[CalendarReminder] = []
        with transaction.atomic():
            for user in users:
                reminders.append(
                    CalendarReminder.objects.create(
                        user=user,
                        created_by=created_by,
                        calendar_event_id=calendar_event_id,
                        reminder_date=reminder_date,
                        reminder_time=reminder_time,
                        timezone=timezone_name,
                        content=content.strip(),
                        status=CalendarReminder.STATUS_PENDING,
                        error_message="",
                        sent_at=None,
                        read_at=None,
                    )
                )
        return reminders

    def apply_update(
        self,
        *,
        reminder: CalendarReminder,
        reminder_date: date,
        reminder_time: time,
        timezone_name: str,
        content: str,
        user_id: int | None = None,
        calendar_event_id: str | None = None,
    ) -> CalendarReminder:
        if user_id is not None:
            target_user = User.objects.filter(id=user_id, is_active=True).first()
            if target_user is None:
                raise ValidationError({"userId": "User not found or inactive."})
            reminder.user = target_user

        reminder.calendar_event_id = calendar_event_id
        reminder.reminder_date = reminder_date
        reminder.reminder_time = reminder_time
        reminder.timezone = timezone_name
        reminder.content = content.strip()
        reminder.status = CalendarReminder.STATUS_PENDING
        reminder.error_message = ""
        reminder.sent_at = None
        reminder.read_at = None
        reminder.save()
        return reminder

    def dispatch_due_reminders(self, *, limit: int = 200) -> CalendarReminderDispatchStats:
        now = timezone.now()
        reminders = (
            CalendarReminder.objects.select_related("user")
            .filter(status=CalendarReminder.STATUS_PENDING, scheduled_for__lte=now)
            .order_by("scheduled_for", "id")[:limit]
        )

        stats = CalendarReminderDispatchStats()
        for reminder in reminders:
            if self._dispatch_single(reminder=reminder, now=now):
                stats.sent += 1
            else:
                stats.failed += 1
        return stats

    def _dispatch_single(self, *, reminder: CalendarReminder, now) -> bool:
        try:
            result = self.push_service.send_to_user(
                user=reminder.user,
                title="Reminder",
                body=reminder.content,
                data={
                    "type": "calendar_reminder",
                    "reminderId": str(reminder.id),
                    "scheduledFor": reminder.scheduled_for.isoformat(),
                    "timezone": reminder.timezone,
                },
                link="/reminders",
            )
        except FcmConfigurationError as exc:
            reminder.status = CalendarReminder.STATUS_FAILED
            reminder.error_message = str(exc)
            reminder.sent_at = None
            reminder.read_at = None
            reminder.save(update_fields=["status", "error_message", "sent_at", "read_at", "updated_at"])
            return False
        except Exception as exc:
            reminder.status = CalendarReminder.STATUS_FAILED
            reminder.error_message = f"{type(exc).__name__}: {exc}"
            reminder.sent_at = None
            reminder.read_at = None
            reminder.save(update_fields=["status", "error_message", "sent_at", "read_at", "updated_at"])
            return False

        if result.sent > 0:
            reminder.status = CalendarReminder.STATUS_SENT
            reminder.sent_at = now
            reminder.read_at = None
            reminder.error_message = ""
            reminder.save(update_fields=["status", "sent_at", "read_at", "error_message", "updated_at"])
            return True

        if result.failed > 0:
            error_message = f"Push delivery failed for {result.failed} active device(s)."
        elif result.skipped > 0:
            error_message = "No active push subscriptions for the selected user."
        else:
            error_message = "Push delivery failed."

        reminder.status = CalendarReminder.STATUS_FAILED
        reminder.sent_at = None
        reminder.read_at = None
        reminder.error_message = error_message
        reminder.save(update_fields=["status", "sent_at", "read_at", "error_message", "updated_at"])
        return False
