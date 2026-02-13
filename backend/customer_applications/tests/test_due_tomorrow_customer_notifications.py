from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from customer_applications.models import DocApplication, WorkflowNotification
from customer_applications.tasks import send_due_tomorrow_customer_notifications
from customers.models import Customer
from products.models import Product, Task

User = get_user_model()


class DueTomorrowCustomerNotificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("notify-user", "notify@example.com", "pass")
        self.customer = Customer.objects.create(
            first_name="Stefano",
            last_name="Galassi",
            email="customer@example.com",
            whatsapp="+628123456789",
        )
        self.product = Product.objects.create(name="Visa Product", code="VP-01", required_documents="Passport")
        self.task = Task.objects.create(
            product=self.product,
            step=1,
            name="biometrics",
            duration=7,
            duration_is_business_days=True,
            notify_days_before=1,
            add_task_to_calendar=True,
            notify_customer=True,
        )
        self.now = timezone.make_aware(datetime(2026, 2, 12, 8, 0, 0))
        self.application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=self.now.date(),
            due_date=self.now.date() + timedelta(days=1),
            notify_customer_too=True,
            notify_customer_channel=DocApplication.NOTIFY_CHANNEL_EMAIL,
            created_by=self.user,
        )

    @patch("notifications.services.providers.NotificationDispatcher.send", return_value="sent:1")
    def test_sends_email_for_due_tomorrow_when_task_notify_customer_enabled(self, send_mock):
        result = send_due_tomorrow_customer_notifications(now=self.now)

        self.assertEqual(result["sent"], 1)
        send_mock.assert_called_once()

        notification = WorkflowNotification.objects.get(doc_application=self.application)
        self.assertEqual(notification.channel, WorkflowNotification.CHANNEL_EMAIL)
        self.assertEqual(notification.status, WorkflowNotification.STATUS_SENT)
        self.assertIn("biometrics", notification.subject.lower())
        self.assertTrue(notification.sent_at is not None)

    @patch("notifications.services.providers.NotificationDispatcher.send")
    def test_skips_when_task_notify_customer_disabled(self, send_mock):
        self.task.notify_customer = False
        self.task.save(update_fields=["notify_customer"])

        result = send_due_tomorrow_customer_notifications(now=self.now)

        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["skipped"], 1)
        send_mock.assert_not_called()
        self.assertFalse(WorkflowNotification.objects.filter(doc_application=self.application).exists())

    @patch("notifications.services.providers.NotificationDispatcher.send", return_value="SM123")
    def test_sends_whatsapp_and_deduplicates_same_day(self, send_mock):
        self.application.notify_customer_channel = DocApplication.NOTIFY_CHANNEL_WHATSAPP
        self.application.save(update_fields=["notify_customer_channel", "updated_at"])

        first = send_due_tomorrow_customer_notifications(now=self.now)
        second = send_due_tomorrow_customer_notifications(now=self.now)

        self.assertEqual(first["sent"], 1)
        self.assertEqual(second["sent"], 0)
        self.assertEqual(second["skipped"], 1)
        self.assertEqual(send_mock.call_count, 1)

        notification = WorkflowNotification.objects.get(doc_application=self.application)
        self.assertEqual(notification.channel, DocApplication.NOTIFY_CHANNEL_WHATSAPP)
        self.assertEqual(notification.external_reference, "SM123")

    @patch("notifications.services.providers.NotificationDispatcher.send", side_effect=RuntimeError("provider down"))
    def test_failed_notification_is_not_recreated_automatically(self, send_mock):
        with self.assertLogs("customer_applications.tasks", level="ERROR") as logs:
            first = send_due_tomorrow_customer_notifications(now=self.now)
        second = send_due_tomorrow_customer_notifications(now=self.now)

        self.assertEqual(first["failed"], 1)
        self.assertEqual(second["failed"], 0)
        self.assertEqual(second["skipped"], 1)
        self.assertEqual(send_mock.call_count, 1)
        self.assertEqual(WorkflowNotification.objects.filter(doc_application=self.application).count(), 1)
        notification = WorkflowNotification.objects.get(doc_application=self.application)
        self.assertEqual(notification.status, WorkflowNotification.STATUS_FAILED)
        self.assertTrue(any("error_type=RuntimeError" in line for line in logs.output))

    @patch(
        "notifications.services.providers.NotificationDispatcher.send",
        return_value="queued_whatsapp:+628123456789",
    )
    def test_whatsapp_queued_placeholder_is_kept_pending(self, send_mock):
        self.application.notify_customer_channel = DocApplication.NOTIFY_CHANNEL_WHATSAPP
        self.application.save(update_fields=["notify_customer_channel", "updated_at"])

        result = send_due_tomorrow_customer_notifications(now=self.now)

        self.assertEqual(result["pending"], 1)
        self.assertEqual(send_mock.call_count, 1)
        notification = WorkflowNotification.objects.get(doc_application=self.application)
        self.assertEqual(notification.status, WorkflowNotification.STATUS_PENDING)
        self.assertEqual(notification.external_reference, "")
        self.assertIsNone(notification.sent_at)
