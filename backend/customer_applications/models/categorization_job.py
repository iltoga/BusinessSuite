import uuid

from django.conf import settings
from django.db import models


class DocumentCategorizationJob(models.Model):
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
    doc_application = models.ForeignKey(
        "customer_applications.DocApplication",
        on_delete=models.CASCADE,
        related_name="categorization_jobs",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_QUEUED)
    progress = models.PositiveSmallIntegerField(default=0)
    total_files = models.PositiveIntegerField(default=0)
    processed_files = models.PositiveIntegerField(default=0)
    success_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    request_params = models.JSONField(default=dict, blank=True)
    result = models.JSONField(blank=True, null=True)
    error_message = models.TextField(blank=True)
    traceback = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="document_categorization_jobs",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"DocumentCategorizationJob {self.id} ({self.status})"


class DocumentCategorizationItem(models.Model):
    STATUS_QUEUED = "queued"
    STATUS_PROCESSING = "processing"
    STATUS_CATEGORIZED = "categorized"
    STATUS_ERROR = "error"

    STATUS_CHOICES = (
        (STATUS_QUEUED, "Queued"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_CATEGORIZED, "Categorized"),
        (STATUS_ERROR, "Error"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(
        DocumentCategorizationJob,
        related_name="items",
        on_delete=models.CASCADE,
    )
    sort_index = models.PositiveIntegerField(default=0)
    filename = models.CharField(max_length=255)
    file_path = models.CharField(max_length=512)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_QUEUED)
    document_type = models.ForeignKey(
        "products.DocumentType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="categorization_items",
    )
    document = models.ForeignKey(
        "customer_applications.Document",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="categorization_items",
    )
    confidence = models.FloatField(null=True, blank=True)
    result = models.JSONField(blank=True, null=True)
    validation_status = models.CharField(max_length=20, blank=True)
    validation_result = models.JSONField(blank=True, null=True)
    error_message = models.TextField(blank=True)
    traceback = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_index", "created_at"]

    def __str__(self) -> str:
        return f"DocumentCategorizationItem {self.filename} ({self.status})"
