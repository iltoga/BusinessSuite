from django.conf import settings
from django.db import models


class WebPushSubscription(models.Model):
    """Stores browser push registrations (FCM tokens) for authenticated users."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="web_push_subscriptions")
    token = models.CharField(max_length=512, unique=True)
    device_label = models.CharField(max_length=255, blank=True, default="")
    user_agent = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    last_error = models.TextField(blank=True, default="")
    last_seen_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["user", "is_active"], name="pushsub_user_active_idx"),
        ]

    def __str__(self) -> str:
        username = getattr(self.user, "username", None) or self.user_id
        label = self.device_label or "browser"
        return f"WebPushSubscription<{username}:{label}>"
