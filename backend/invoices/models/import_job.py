import uuid

from django.conf import settings
from django.db import models


class InvoiceImportJob(models.Model):
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
    total_files = models.PositiveIntegerField(default=0)
    processed_files = models.PositiveIntegerField(default=0)
    imported_count = models.PositiveIntegerField(default=0)
    duplicate_count = models.PositiveIntegerField(default=0)
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
        related_name="invoice_import_jobs",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"InvoiceImportJob {self.id} ({self.status})"


class InvoiceImportItem(models.Model):
    STATUS_QUEUED = "queued"
    STATUS_PROCESSING = "processing"
    STATUS_IMPORTED = "imported"
    STATUS_DUPLICATE = "duplicate"
    STATUS_ERROR = "error"

    STATUS_CHOICES = (
        (STATUS_QUEUED, "Queued"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_IMPORTED, "Imported"),
        (STATUS_DUPLICATE, "Duplicate"),
        (STATUS_ERROR, "Error"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(InvoiceImportJob, related_name="items", on_delete=models.CASCADE)
    sort_index = models.PositiveIntegerField(default=0)
    filename = models.CharField(max_length=255)
    file_path = models.CharField(max_length=512)
    is_paid = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_QUEUED)
    result = models.JSONField(blank=True, null=True)
    error_message = models.TextField(blank=True)
    traceback = models.TextField(blank=True)
    invoice = models.ForeignKey(
        "invoices.Invoice",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="import_items",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoice_import_items",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_index", "created_at"]

    def __str__(self) -> str:
        return f"InvoiceImportItem {self.filename} ({self.status})"
