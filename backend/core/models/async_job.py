import uuid

from django.conf import settings
from django.db import models


class AsyncJob(models.Model):
    """
    Generic model to track asynchronous tasks (Huey jobs).
    Allows frontend to track progress and receive results via SSE.
    """

    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task_name = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    progress = models.IntegerField(default=0)
    message = models.TextField(blank=True, null=True)
    result = models.JSONField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    traceback = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="async_jobs",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.task_name} ({self.status}) - {self.id}"

    def update_progress(self, progress, message=None, status=None):
        """Update job progress and message."""
        self.progress = progress
        update_fields = ["progress", "updated_at"]
        if message:
            self.message = message
            update_fields.append("message")
        if status:
            self.status = status
            update_fields.append("status")
        self.save(update_fields=update_fields)

    def complete(self, result=None, message="Completed"):
        """Mark job as completed."""
        self.status = self.STATUS_COMPLETED
        self.progress = 100
        self.result = result
        self.message = message
        self.save(update_fields=["status", "progress", "result", "message", "updated_at"])

    def fail(self, error_message, traceback=None):
        """Mark job as failed."""
        self.status = self.STATUS_FAILED
        self.progress = 100
        self.error_message = error_message
        self.traceback = traceback
        self.save(update_fields=["status", "progress", "error_message", "traceback", "updated_at"])
