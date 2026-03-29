"""
FILE_ROLE: Push notification service-layer logic for the core app.

KEY_COMPONENTS:
- PushNotificationResult: Result/dataclass helper.
- PushNotificationService: Service class.

INTERACTIONS:
- Depends on: nearby Django models, services, serializers, and the app packages imported by this module.

AI_GUIDELINES:
- Keep the module focused on its narrow layer boundary and avoid moving cross-cutting workflow code here.
- Preserve the existing API/model contract because other modules import these symbols directly.
"""

from dataclasses import dataclass
from typing import Any

from core.models import WebPushSubscription
from core.services.push_notifications.fcm_client import FcmClient, FcmSendError
from django.contrib.auth import get_user_model

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
        # Lazily initialize the FCM client so call sites can safely instantiate
        # the service in environments where credentials are intentionally absent
        # (for example in tests that mock send_to_user).
        self._client = client

    def _get_client(self) -> FcmClient:
        if self._client is None:
            self._client = FcmClient()
        return self._client

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
        client = self._get_client()

        for subscription in subscriptions:
            try:
                client.send_to_token(
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
