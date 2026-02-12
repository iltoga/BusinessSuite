from django.contrib.auth import get_user_model
from django.test import TestCase

from core.models import WebPushSubscription
from core.services.push_notifications import FcmSendError, PushNotificationService

User = get_user_model()


class _SuccessfulClient:
    def __init__(self):
        self.sent_tokens = []

    def send_to_token(self, *, token, title, body, data=None, link=None):
        self.sent_tokens.append(token)
        return {"name": "projects/test/messages/123"}


class _UnregisteredClient:
    def send_to_token(self, **kwargs):
        raise FcmSendError("Token no longer valid", error_code="UNREGISTERED")


class PushNotificationServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("push-user", "push@example.com", "pass")
        self.subscription = WebPushSubscription.objects.create(
            user=self.user,
            token="fcm-token-1",
            device_label="Browser",
            is_active=True,
        )

    def test_send_to_user_marks_message_sent(self):
        client = _SuccessfulClient()
        service = PushNotificationService(client=client)

        result = service.send_to_user(
            user=self.user,
            title="Test",
            body="Body",
            data={"type": "test"},
            link="/applications/1",
        )

        self.assertEqual(result.sent, 1)
        self.assertEqual(result.failed, 0)
        self.assertEqual(client.sent_tokens, ["fcm-token-1"])

    def test_send_to_user_deactivates_invalid_token(self):
        service = PushNotificationService(client=_UnregisteredClient())
        result = service.send_to_user(
            user=self.user,
            title="Test",
            body="Body",
        )

        self.assertEqual(result.sent, 0)
        self.assertEqual(result.failed, 1)
        self.subscription.refresh_from_db()
        self.assertFalse(self.subscription.is_active)
        self.assertIn("Token no longer valid", self.subscription.last_error)
