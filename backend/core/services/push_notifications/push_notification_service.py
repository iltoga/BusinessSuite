from dataclasses import dataclass
from typing import Any

from django.contrib.auth import get_user_model

from core.models import WebPushSubscription
from core.services.push_notifications.fcm_client import FcmClient, FcmSendError

User = get_user_model()


@dataclass
class PushNotificationResult:
    sent: int = 0
    failed: int = 0
    skipped: int = 0

    @property
    def total(self) -> int:
        return self.sent + self.failed + self.skipped


class PushNotificationService:
    """Reusable user-oriented push notifications service."""

    def __init__(self, client: FcmClient | None = None):
        self.client = client or FcmClient()

    def send_to_user(
        self,
        *,
        user: User,
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
        link: str | None = None,
    ) -> PushNotificationResult:
        subscriptions = WebPushSubscription.objects.filter(user=user, is_active=True).order_by("-updated_at")
        result = PushNotificationResult()

        for subscription in subscriptions:
            try:
                self.client.send_to_token(
                    token=subscription.token,
                    title=title,
                    body=body,
                    data=data,
                    link=link,
                )
                if subscription.last_error:
                    subscription.last_error = ""
                    subscription.save(update_fields=["last_error", "last_seen_at", "updated_at"])
                result.sent += 1
            except FcmSendError as exc:
                result.failed += 1
                subscription.last_error = str(exc)
                if exc.is_token_invalid():
                    subscription.is_active = False
                    subscription.save(update_fields=["is_active", "last_error", "last_seen_at", "updated_at"])
                else:
                    subscription.save(update_fields=["last_error", "last_seen_at", "updated_at"])

        if not subscriptions.exists():
            result.skipped = 1

        return result
