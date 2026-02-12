from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from customer_applications.models import DocApplication, WorkflowNotification
from customers.models import Customer
from products.models import Product

User = get_user_model()


class WorkflowNotificationApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("workflow-admin", "workflowadmin@example.com", "pass")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

        customer = Customer.objects.create(first_name="Notif", last_name="Customer", whatsapp="+628123456789")
        product = Product.objects.create(name="Notif Product", code="NOTIF-1", required_documents="")
        application = DocApplication.objects.create(
            customer=customer,
            product=product,
            doc_date=date(2026, 2, 12),
            due_date=date(2026, 2, 13),
            created_by=self.user,
        )
        self.notification = WorkflowNotification.objects.create(
            channel=WorkflowNotification.CHANNEL_WHATSAPP,
            recipient=customer.whatsapp,
            subject="Reminder",
            body="Body",
            doc_application=application,
            status=WorkflowNotification.STATUS_FAILED,
            notification_type=WorkflowNotification.TYPE_DUE_TOMORROW,
            target_date=application.due_date,
        )

    @patch("notifications.services.providers.NotificationDispatcher.send")
    def test_resend_keeps_status_pending_when_provider_returns_queued_placeholder(self, send_mock):
        send_mock.return_value = "queued_whatsapp:+628123456789"

        response = self.client.post(f"/api/workflow-notifications/{self.notification.id}/resend/", {}, format="json")

        self.assertEqual(response.status_code, 200)
        self.notification.refresh_from_db()
        self.assertEqual(self.notification.status, WorkflowNotification.STATUS_PENDING)
        self.assertEqual(self.notification.external_reference, "")
        self.assertEqual(self.notification.provider_message, "queued_whatsapp:+628123456789")
        self.assertIsNone(self.notification.sent_at)

    @patch("notifications.services.providers.NotificationDispatcher.send")
    def test_resend_updates_whatsapp_external_reference_when_sent(self, send_mock):
        send_mock.return_value = "wamid.HBgL123"

        response = self.client.post(f"/api/workflow-notifications/{self.notification.id}/resend/", {}, format="json")

        self.assertEqual(response.status_code, 200)
        self.notification.refresh_from_db()
        self.assertEqual(self.notification.status, WorkflowNotification.STATUS_SENT)
        self.assertEqual(self.notification.external_reference, "wamid.HBgL123")
        self.assertIsNotNone(self.notification.sent_at)
