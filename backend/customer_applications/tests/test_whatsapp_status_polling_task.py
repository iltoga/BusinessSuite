from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from customer_applications.models import DocApplication, WorkflowNotification
from customer_applications.tasks import poll_whatsapp_delivery_statuses
from customers.models import Customer
from products.models import Product

User = get_user_model()


class WhatsappStatusPollingTaskTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("wa-poll-user", "wa-poll@example.com", "pass")
        self.customer = Customer.objects.create(
            first_name="Meta",
            last_name="Polling",
            whatsapp="+628123456789",
        )
        self.product = Product.objects.create(name="WA Product", code="WA-STATUS", required_documents="")
        self.application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date="2026-02-12",
            due_date="2026-02-13",
            created_by=self.user,
        )

    @override_settings(META_WHATSAPP_ACCESS_TOKEN="meta-token", META_GRAPH_API_VERSION="v23.0")
    @patch("notifications.services.providers.requests.get")
    def test_poll_updates_notification_to_delivered(self, get_mock):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"status": "delivered"}
        get_mock.return_value = response

        notification = WorkflowNotification.objects.create(
            channel=WorkflowNotification.CHANNEL_WHATSAPP,
            recipient=self.customer.whatsapp,
            subject="Reminder",
            body="Body",
            doc_application=self.application,
            status=WorkflowNotification.STATUS_SENT,
            external_reference="wamid.delivered",
            provider_message="wamid.delivered",
            sent_at=None,
        )

        result = poll_whatsapp_delivery_statuses(notification_ids=[notification.id])

        self.assertEqual(result["checked"], 1)
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["failed"], 0)
        notification.refresh_from_db()
        self.assertEqual(notification.status, WorkflowNotification.STATUS_DELIVERED)
        self.assertIn("Meta status: delivered", notification.provider_message)
        self.assertIsNotNone(notification.sent_at)

    @override_settings(META_WHATSAPP_ACCESS_TOKEN="meta-token", META_GRAPH_API_VERSION="v23.0")
    @patch("notifications.services.providers.requests.get")
    def test_poll_updates_notification_to_read(self, get_mock):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"message_status": "read"}
        get_mock.return_value = response

        notification = WorkflowNotification.objects.create(
            channel=WorkflowNotification.CHANNEL_WHATSAPP,
            recipient=self.customer.whatsapp,
            subject="Reminder",
            body="Body",
            doc_application=self.application,
            status=WorkflowNotification.STATUS_SENT,
            external_reference="wamid.read",
            provider_message="wamid.read",
        )

        result = poll_whatsapp_delivery_statuses(notification_ids=[notification.id])

        self.assertEqual(result["checked"], 1)
        self.assertEqual(result["updated"], 1)
        notification.refresh_from_db()
        self.assertEqual(notification.status, WorkflowNotification.STATUS_READ)
        self.assertIn("Meta status: read", notification.provider_message)

    @override_settings(META_WHATSAPP_ACCESS_TOKEN="meta-token", META_GRAPH_API_VERSION="v23.0")
    @patch("notifications.services.providers.requests.get")
    def test_poll_logs_error_and_keeps_status_when_api_fails(self, get_mock):
        response = Mock()
        response.status_code = 500
        response.text = "upstream error"
        response.json.return_value = {"error": {"message": "upstream error"}}
        get_mock.return_value = response

        notification = WorkflowNotification.objects.create(
            channel=WorkflowNotification.CHANNEL_WHATSAPP,
            recipient=self.customer.whatsapp,
            subject="Reminder",
            body="Body",
            doc_application=self.application,
            status=WorkflowNotification.STATUS_SENT,
            external_reference="wamid.fail",
            provider_message="wamid.fail",
        )

        with self.assertLogs("customer_applications.tasks", level="ERROR") as logs:
            result = poll_whatsapp_delivery_statuses(notification_ids=[notification.id])

        self.assertEqual(result["checked"], 0)
        self.assertEqual(result["failed"], 1)
        notification.refresh_from_db()
        self.assertEqual(notification.status, WorkflowNotification.STATUS_SENT)
        self.assertIn("Meta poll error: RuntimeError", notification.provider_message)
        self.assertTrue(any("WhatsApp status poll failed" in line for line in logs.output))

    @override_settings(META_WHATSAPP_ACCESS_TOKEN="meta-token", META_GRAPH_API_VERSION="v23.0")
    @patch("notifications.services.providers.requests.get")
    def test_poll_skips_when_graph_message_lookup_is_unsupported(self, get_mock):
        unsupported = Mock()
        unsupported.status_code = 400
        unsupported.text = (
            '{"error":{"message":"Unsupported get request","type":"GraphMethodException","code":100,"error_subcode":33}}'
        )
        unsupported.json.return_value = {
            "error": {
                "message": "Unsupported get request",
                "type": "GraphMethodException",
                "code": 100,
                "error_subcode": 33,
            }
        }
        get_mock.return_value = unsupported

        notification = WorkflowNotification.objects.create(
            channel=WorkflowNotification.CHANNEL_WHATSAPP,
            recipient=self.customer.whatsapp,
            subject="Reminder",
            body="Body",
            doc_application=self.application,
            status=WorkflowNotification.STATUS_SENT,
            external_reference="wamid.unsupported",
        )

        result = poll_whatsapp_delivery_statuses(notification_ids=[notification.id])

        self.assertEqual(result["checked"], 0)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["skipped"], 1)
        notification.refresh_from_db()
        self.assertIn("Meta poll unsupported: waiting for webhook status updates.", notification.provider_message)
        self.assertEqual(notification.status, WorkflowNotification.STATUS_SENT)

        get_mock.reset_mock()
        second = poll_whatsapp_delivery_statuses(notification_ids=[notification.id])
        self.assertEqual(second["checked"], 0)
        self.assertEqual(second["failed"], 0)
        self.assertEqual(second["skipped"], 0)
        get_mock.assert_not_called()

    @override_settings(META_WHATSAPP_ACCESS_TOKEN="meta-token", META_GRAPH_API_VERSION="v23.0")
    @patch("notifications.services.providers.requests.get")
    def test_poll_skips_notification_without_external_reference(self, get_mock):
        notification = WorkflowNotification.objects.create(
            channel=WorkflowNotification.CHANNEL_WHATSAPP,
            recipient=self.customer.whatsapp,
            subject="Reminder",
            body="Body",
            doc_application=self.application,
            status=WorkflowNotification.STATUS_PENDING,
            external_reference="",
        )

        result = poll_whatsapp_delivery_statuses(notification_ids=[notification.id])

        self.assertEqual(result["checked"], 0)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["failed"], 0)
        get_mock.assert_not_called()

    @patch(
        "notifications.services.providers.WhatsappNotificationProvider.get_message_status",
        side_effect=RuntimeError(
            'WhatsApp status poll failed (400): {"error":{"message":"Unsupported get request","type":"GraphMethodException","code":100,"error_subcode":33}}'
        ),
    )
    def test_poll_treats_runtimeerror_unsupported_lookup_as_skipped(self, get_status_mock):
        notification = WorkflowNotification.objects.create(
            channel=WorkflowNotification.CHANNEL_WHATSAPP,
            recipient=self.customer.whatsapp,
            subject="Reminder",
            body="Body",
            doc_application=self.application,
            status=WorkflowNotification.STATUS_SENT,
            external_reference="wamid.runtime.unsupported",
        )

        result = poll_whatsapp_delivery_statuses(notification_ids=[notification.id])

        self.assertEqual(result["checked"], 0)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["skipped"], 1)
        notification.refresh_from_db()
        self.assertIn("Meta poll unsupported: waiting for webhook status updates.", notification.provider_message)
        get_status_mock.assert_called_once()

    @patch("notifications.services.providers.WhatsappNotificationProvider.get_message_status")
    def test_poll_ignores_notifications_older_than_one_day(self, get_status_mock):
        notification = WorkflowNotification.objects.create(
            channel=WorkflowNotification.CHANNEL_WHATSAPP,
            recipient=self.customer.whatsapp,
            subject="Reminder",
            body="Body",
            doc_application=self.application,
            status=WorkflowNotification.STATUS_PENDING,
            external_reference="wamid.old",
        )
        WorkflowNotification.objects.filter(pk=notification.pk).update(created_at=timezone.now() - timedelta(days=2))

        result = poll_whatsapp_delivery_statuses(notification_ids=[notification.id])

        self.assertEqual(result["checked"], 0)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(result["failed"], 0)
        get_status_mock.assert_not_called()
