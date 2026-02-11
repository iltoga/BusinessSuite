from django.conf import settings
from django.db import models


class WorkflowNotification(models.Model):
    STATUS_PENDING = "pending"
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"

    CHANNEL_EMAIL = "email"

    status = models.CharField(
        max_length=20,
        choices=[
            (STATUS_PENDING, "Pending"),
            (STATUS_SENT, "Sent"),
            (STATUS_FAILED, "Failed"),
            (STATUS_CANCELLED, "Cancelled"),
        ],
        default=STATUS_PENDING,
        db_index=True,
    )
    channel = models.CharField(max_length=20, default=CHANNEL_EMAIL, db_index=True)
    subject = models.CharField(max_length=255)
    body = models.TextField()
    recipient = models.CharField(max_length=255)
    doc_application = models.ForeignKey(
        "customer_applications.DocApplication", related_name="notifications", on_delete=models.CASCADE
    )
    doc_workflow = models.ForeignKey(
        "customer_applications.DocWorkflow", related_name="notifications", on_delete=models.SET_NULL, null=True, blank=True
    )
    scheduled_for = models.DateField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    provider_message = models.TextField(blank=True)
    external_reference = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.channel}:{self.recipient}:{self.status}"
