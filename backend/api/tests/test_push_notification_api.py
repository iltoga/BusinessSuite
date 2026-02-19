from unittest.mock import patch

from customer_applications.models import DocApplication, WorkflowNotification
from customers.models import Customer
from core.models import WebPushSubscription
from core.services.push_notifications import PushNotificationResult
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test.utils import override_settings
from products.models import Product
from rest_framework.test import APIClient

User = get_user_model()


class PushNotificationApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("push-api-user", "pushapi@example.com", "pass")
        customer = Customer.objects.create(first_name="Push", last_name="Tester", whatsapp="+628111111111")
        product = Product.objects.create(name="Push Product", code="PUSH-01", required_documents="")
        self.application = DocApplication.objects.create(
            customer=customer,
            product=product,
            doc_date="2026-02-12",
            due_date="2026-02-13",
            created_by=self.user,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_register_and_unregister_subscription(self):
        register_resp = self.client.post(
            "/api/push-notifications/register/",
            {
                "token": "fcm-token-api-1",
                "device_label": "Chrome",
                "user_agent": "Mozilla/5.0",
            },
            format="json",
        )
        self.assertEqual(register_resp.status_code, 201)
        self.assertTrue(WebPushSubscription.objects.filter(token="fcm-token-api-1", user=self.user).exists())

        unregister_resp = self.client.post(
            "/api/push-notifications/unregister/",
            {"token": "fcm-token-api-1"},
            format="json",
        )
        self.assertEqual(unregister_resp.status_code, 200)

        subscription = WebPushSubscription.objects.get(token="fcm-token-api-1")
        self.assertFalse(subscription.is_active)

    @patch("api.views.PushNotificationService.send_to_user")
    def test_test_endpoint_returns_delivery_summary(self, send_to_user_mock):
        WebPushSubscription.objects.create(user=self.user, token="fcm-token-api-test", is_active=True)
        send_to_user_mock.return_value = PushNotificationResult(sent=1, failed=0, skipped=0)

        response = self.client.post(
            "/api/push-notifications/test/",
            {
                "title": "Test title",
                "body": "Test body",
                "data": {"type": "manual_test"},
                "link": "/applications/1",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["sent"], 1)
        self.assertEqual(response.data["failed"], 0)
        self.assertEqual(response.data["total"], 1)

    @patch("api.views.PushNotificationService.send_to_user")
    def test_admin_send_test_to_selected_user(self, send_to_user_mock):
        WebPushSubscription.objects.create(user=self.user, token="fcm-token-api-admin", is_active=True)
        send_to_user_mock.return_value = PushNotificationResult(sent=1, failed=0, skipped=0)

        response = self.client.post(
            "/api/push-notifications/send-test/",
            {
                "user_id": self.user.id,
                "title": "Admin test",
                "body": "Body",
                "data": {"type": "admin_test"},
                "link": "/applications/1",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["sent"], 1)

    def test_admin_users_endpoint_lists_users(self):
        WebPushSubscription.objects.create(user=self.user, token="fcm-token-api-users", is_active=True)
        response = self.client.get("/api/push-notifications/users/")
        self.assertEqual(response.status_code, 200)
        current = next((item for item in response.data if item["id"] == self.user.id), None)
        self.assertIsNotNone(current)
        if current:
            self.assertEqual(current["active_push_subscriptions"], 1)
            self.assertEqual(current["total_push_subscriptions"], 1)

    def test_test_endpoint_returns_409_when_no_active_subscription(self):
        response = self.client.post(
            "/api/push-notifications/test/",
            {"title": "No sub", "body": "No active subscription"},
            format="json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("No active browser push subscriptions", str(response.data.get("error")))

    def test_admin_send_test_returns_409_when_target_has_no_subscription(self):
        response = self.client.post(
            "/api/push-notifications/send-test/",
            {"user_id": self.user.id, "title": "No sub", "body": "No active subscription"},
            format="json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("Target user has no active browser push subscriptions", str(response.data.get("error")))

    @patch("customer_applications.tasks.schedule_whatsapp_status_poll")
    @patch("notifications.services.providers.WhatsappNotificationProvider.send")
    @override_settings(WHATSAPP_TEST_NUMBER="+628111111111")
    def test_admin_send_test_whatsapp_uses_default_number_when_to_omitted(self, send_mock, schedule_poll_mock):
        send_mock.return_value = "wamid.test.123"

        response = self.client.post(
            "/api/push-notifications/send-test-whatsapp/",
            {
                "subject": "WhatsApp subject",
                "body": "WhatsApp body",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["recipient"], "+628111111111")
        self.assertTrue(response.data["used_default_recipient"])
        self.assertEqual(response.data["message_id"], "wamid.test.123")
        self.assertEqual(response.data["workflow_notification_status"], WorkflowNotification.STATUS_PENDING)
        send_mock.assert_called_once()
        kwargs = send_mock.call_args.kwargs
        self.assertEqual(kwargs["recipient"], "+628111111111")
        self.assertEqual(kwargs["subject"], "WhatsApp subject")
        self.assertEqual(kwargs["body"], "WhatsApp subject\n\nWhatsApp body")
        self.assertFalse(kwargs["prefer_template"])
        self.assertFalse(kwargs["allow_template_fallback"])
        created = WorkflowNotification.objects.get(pk=response.data["workflow_notification_id"])
        self.assertEqual(created.channel, WorkflowNotification.CHANNEL_WHATSAPP)
        self.assertEqual(created.recipient, "+628111111111")
        self.assertEqual(created.subject, "WhatsApp subject")
        self.assertEqual(created.body, "WhatsApp body")
        self.assertEqual(created.doc_application_id, self.application.id)
        self.assertEqual(created.status, WorkflowNotification.STATUS_PENDING)
        self.assertEqual(created.external_reference, "wamid.test.123")
        self.assertEqual(created.notification_type, "manual_whatsapp_test")
        schedule_poll_mock.assert_called_once_with(notification_id=created.id, delay_seconds=5)

    @patch("customer_applications.tasks.schedule_whatsapp_status_poll")
    @patch("notifications.services.providers.WhatsappNotificationProvider.send")
    def test_admin_send_test_whatsapp_uses_explicit_to(self, send_mock, schedule_poll_mock):
        send_mock.return_value = "wamid.test.456"

        response = self.client.post(
            "/api/push-notifications/send-test-whatsapp/",
            {
                "to": "+628222222222",
                "subject": "Explicit recipient",
                "body": "Body",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["recipient"], "+628222222222")
        self.assertFalse(response.data["used_default_recipient"])
        self.assertEqual(response.data["message_id"], "wamid.test.456")
        created = WorkflowNotification.objects.get(pk=response.data["workflow_notification_id"])
        self.assertEqual(created.status, WorkflowNotification.STATUS_PENDING)
        self.assertEqual(created.external_reference, "wamid.test.456")
        schedule_poll_mock.assert_called_once_with(notification_id=created.id, delay_seconds=5)

    @patch("customer_applications.tasks.schedule_whatsapp_status_poll")
    @patch("notifications.services.providers.WhatsappNotificationProvider.send")
    def test_admin_send_test_whatsapp_keeps_dummy_pending_for_queued_result(self, send_mock, schedule_poll_mock):
        send_mock.return_value = "queued_whatsapp:+628222222222"

        response = self.client.post(
            "/api/push-notifications/send-test-whatsapp/",
            {
                "to": "+628222222222",
                "subject": "Queued recipient",
                "body": "Body",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        created = WorkflowNotification.objects.get(pk=response.data["workflow_notification_id"])
        self.assertEqual(created.status, WorkflowNotification.STATUS_PENDING)
        self.assertEqual(created.external_reference, "")
        self.assertIsNone(created.sent_at)
        schedule_poll_mock.assert_not_called()

    @override_settings(WHATSAPP_TEST_NUMBER="")
    def test_admin_send_test_whatsapp_returns_400_when_no_destination(self):
        response = self.client.post(
            "/api/push-notifications/send-test-whatsapp/",
            {
                "subject": "No recipient configured",
                "body": "Body",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("No WhatsApp destination configured", str(response.data.get("error")))

    @patch("notifications.services.providers.WhatsappNotificationProvider.send")
    def test_admin_send_test_whatsapp_returns_409_when_no_application_available(self, send_mock):
        DocApplication.objects.all().delete()

        response = self.client.post(
            "/api/push-notifications/send-test-whatsapp/",
            {
                "to": "+628333333333",
                "subject": "No app",
                "body": "Body",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("No applications available", str(response.data.get("error")))
        send_mock.assert_not_called()

    @patch("notifications.services.providers.WhatsappNotificationProvider.send", side_effect=RuntimeError("blocked"))
    def test_admin_send_test_whatsapp_returns_400_when_text_send_fails(self, send_mock):
        response = self.client.post(
            "/api/push-notifications/send-test-whatsapp/",
            {
                "to": "+628222222222",
                "subject": "Explicit recipient",
                "body": "Body",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("WhatsApp text send failed", str(response.data.get("error")))
        send_mock.assert_called_once()
