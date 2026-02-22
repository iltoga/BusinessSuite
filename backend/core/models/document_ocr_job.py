import uuid

from django.conf import settings
from django.db import models


class DocumentOCRJob(models.Model):
    STATUS_QUEUED = "queued"
    STATUS_PROCESSING = "processing"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = (
        (STATUS_QUEUED, "Queued"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_QUEUED)
    progress = models.PositiveSmallIntegerField(default=0)
    request_params = models.JSONField(default=dict, blank=True)
    result_text = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    traceback = models.TextField(blank=True)
    file_path = models.CharField(max_length=512, blank=True)
    file_url = models.CharField(max_length=512, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="document_ocr_jobs",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"DocumentOCRJob {self.id} ({self.status})"
