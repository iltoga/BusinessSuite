from django.conf import settings
from django.db import models


class BaseAuditEvent(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    source = models.CharField(max_length=64, default="django")
    data = models.JSONField(default=dict, blank=True)

    class Meta:
        abstract = True


class CRUDEvent(BaseAuditEvent):
    ACTION_CHOICES = ("create", "update", "delete")

    action = models.CharField(max_length=16, choices=[(a, a) for a in ACTION_CHOICES])
    object_type = models.CharField(max_length=255)
    object_id = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return f"CRUDEvent {self.action} {self.object_type}({self.object_id}) @ {self.timestamp}"


class LoginEvent(BaseAuditEvent):
    success = models.BooleanField(default=True)
    ip_address = models.CharField(max_length=64, blank=True, null=True)

    def __str__(self):
        return f"LoginEvent success={self.success} user={self.actor} @ {self.timestamp}"


class RequestEvent(BaseAuditEvent):
    method = models.CharField(max_length=8, blank=True, null=True)
    path = models.CharField(max_length=1024, blank=True, null=True)
    status_code = models.IntegerField(blank=True, null=True)
    duration_ms = models.IntegerField(blank=True, null=True)

    def __str__(self):
        return f"RequestEvent {self.method} {self.path} {self.status_code} @ {self.timestamp}"
