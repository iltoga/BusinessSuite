from datetime import datetime
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class CalendarReminder(models.Model):
    STATUS_PENDING = "pending"
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_SENT, "Sent"),
        (STATUS_FAILED, "Failed"),
    ]

    DELIVERY_IN_APP = "in_app"
    DELIVERY_SYSTEM = "system"

    DELIVERY_CHANNEL_CHOICES = [
        (DELIVERY_IN_APP, "In-App"),
        (DELIVERY_SYSTEM, "System Notification"),
    ]

    DEFAULT_TIMEZONE = "Asia/Makassar"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="calendar_reminders",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_calendar_reminders",
        null=True,
        blank=True,
    )
    calendar_event = models.ForeignKey(
        "core.CalendarEvent",
        on_delete=models.SET_NULL,
        related_name="reminders",
        null=True,
        blank=True,
    )
    reminder_date = models.DateField(db_index=True)
    reminder_time = models.TimeField()
    timezone = models.CharField(max_length=64, default=DEFAULT_TIMEZONE)
    scheduled_for = models.DateTimeField(db_index=True)
    content = models.TextField()
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )
    sent_at = models.DateTimeField(null=True, blank=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True, db_index=True)
    delivery_channel = models.CharField(
        max_length=16,
        choices=DELIVERY_CHANNEL_CHOICES,
        blank=True,
        default="",
        db_index=True,
    )
    delivery_device_label = models.CharField(max_length=255, blank=True, default="")
    read_device_label = models.CharField(max_length=255, blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["status", "scheduled_for"], name="core_calrem_status_sched_idx"),
            models.Index(fields=["created_by", "status"], name="core_calrem_creator_status_idx"),
            models.Index(fields=["user", "scheduled_for"], name="core_calrem_user_sched_idx"),
            models.Index(fields=["user", "status", "sent_at"], name="calrem_usr_st_sent_idx"),
            models.Index(
                fields=["user", "status", "sent_at", "read_at"],
                name="calrem_usr_st_sr_rd_idx",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"CalendarReminder<{self.id}:user={self.user_id}:"
            f"{self.reminder_date} {self.reminder_time} {self.timezone}:{self.status}>"
        )

    @classmethod
    def compute_scheduled_for(
        cls,
        *,
        reminder_date,
        reminder_time,
        timezone_name: str,
    ):
        try:
            tz = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ValidationError({"timezone": "Invalid timezone."}) from exc

        local_dt = datetime.combine(reminder_date, reminder_time).replace(tzinfo=tz)
        return local_dt.astimezone(dt_timezone.utc)

    def clean(self):
        super().clean()
        self.scheduled_for = self.compute_scheduled_for(
            reminder_date=self.reminder_date,
            reminder_time=self.reminder_time,
            timezone_name=self.timezone,
        )

    def save(self, *args, **kwargs):
        self.scheduled_for = self.compute_scheduled_for(
            reminder_date=self.reminder_date,
            reminder_time=self.reminder_time,
            timezone_name=self.timezone,
        )
        super().save(*args, **kwargs)
