import uuid

from django.conf import settings
from django.db import models


class InvoiceDownloadJob(models.Model):
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
    invoice = models.ForeignKey("invoices.Invoice", on_delete=models.CASCADE, related_name="download_jobs")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_QUEUED)
    progress = models.PositiveSmallIntegerField(default=0)
    format_type = models.CharField(max_length=10, choices=FORMAT_CHOICES, default=FORMAT_PDF)
    output_path = models.CharField(max_length=512, blank=True)
    request_params = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    traceback = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoice_download_jobs",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"InvoiceDownloadJob {self.id} ({self.status})"
