import uuid

from django.conf import settings
from django.db import models


class InvoiceDocumentJob(models.Model):
    STATUS_QUEUED = "queued"
    STATUS_PROCESSING = "processing"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    FORMAT_DOCX = "docx"
    FORMAT_PDF = "pdf"

    STATUS_CHOICES = (
        (STATUS_QUEUED, "Queued"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
    )

    FORMAT_CHOICES = (
        (FORMAT_DOCX, "DOCX"),
        (FORMAT_PDF, "PDF"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_QUEUED)
    progress = models.PositiveSmallIntegerField(default=0)
    format_type = models.CharField(max_length=10, choices=FORMAT_CHOICES, default=FORMAT_DOCX)
    total_invoices = models.PositiveIntegerField(default=0)
    processed_invoices = models.PositiveIntegerField(default=0)
    output_path = models.CharField(max_length=512, blank=True)
    result = models.JSONField(blank=True, null=True)
    error_message = models.TextField(blank=True)
    traceback = models.TextField(blank=True)
    request_params = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoice_document_jobs",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"InvoiceDocumentJob {self.id} ({self.status})"


class InvoiceDocumentItem(models.Model):
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
    job = models.ForeignKey(InvoiceDocumentJob, related_name="items", on_delete=models.CASCADE)
    sort_index = models.PositiveIntegerField(default=0)
    invoice = models.ForeignKey("invoices.Invoice", on_delete=models.CASCADE, related_name="document_items")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_QUEUED)
    output_path = models.CharField(max_length=512, blank=True)
    error_message = models.TextField(blank=True)
    traceback = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_index", "created_at"]

    def __str__(self) -> str:
        return f"InvoiceDocumentItem {self.invoice_id} ({self.status})"
