import uuid

from django.db import models


def _default_calendar_event_id() -> str:
    return f"evt-local-{uuid.uuid4().hex}"


class CalendarEvent(models.Model):
    SOURCE_MANUAL = "manual"
    SOURCE_APPLICATION = "application"

    SOURCE_CHOICES = [
        (SOURCE_MANUAL, "Manual"),
        (SOURCE_APPLICATION, "Application"),
    ]

    SYNC_STATUS_PENDING = "pending"
    SYNC_STATUS_SYNCED = "synced"
    SYNC_STATUS_FAILED = "failed"
    SYNC_STATUS_CHOICES = [
        (SYNC_STATUS_PENDING, "Pending"),
        (SYNC_STATUS_SYNCED, "Synced"),
        (SYNC_STATUS_FAILED, "Failed"),
    ]

    id = models.CharField(primary_key=True, max_length=255, default=_default_calendar_event_id, editable=False)
    source = models.CharField(max_length=32, choices=SOURCE_CHOICES, default=SOURCE_MANUAL, db_index=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    start_time = models.DateTimeField(blank=True, null=True)
    end_time = models.DateTimeField(blank=True, null=True)
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    attendees = models.JSONField(blank=True, default=list)
    notifications = models.JSONField(blank=True, default=dict)
    extended_properties = models.JSONField(blank=True, default=dict)
    color_id = models.CharField(max_length=2, blank=True, null=True)
    google_calendar_id = models.CharField(max_length=255, blank=True, default="")
    google_event_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    sync_status = models.CharField(
        max_length=16,
        choices=SYNC_STATUS_CHOICES,
        default=SYNC_STATUS_PENDING,
        db_index=True,
    )
    sync_error = models.TextField(blank=True, default="")
    last_synced_at = models.DateTimeField(blank=True, null=True)
    application = models.ForeignKey(
        "customer_applications.DocApplication",
        on_delete=models.CASCADE,
        related_name="calendar_events",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_date", "-start_time", "-created_at"]
        indexes = [
            models.Index(fields=["application", "source"], name="calevent_app_source_idx"),
            models.Index(fields=["sync_status", "updated_at"], name="calevent_sync_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.id} {self.title}"
