from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from api.serializers.doc_application_serializer import DocApplicationCreateUpdateSerializer
from customer_applications.models import DocApplication, Document, WorkflowNotification
from customers.models import Customer
from products.models import Product, Task
from products.models.document_type import DocumentType

User = get_user_model()


class ImmediateDueTomorrowNotificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("immediate-user", "immediate@example.com", "pass")
        self.customer = Customer.objects.create(
            first_name="Immediate",
            last_name="Customer",
            email="customer@example.com",
            whatsapp="+628123456789",
        )
        self.product = Product.objects.create(name="Immediate Product", code="IP-01", required_documents="Passport")
        self.passport_doc_type = DocumentType.objects.create(name="Passport")
        self.task = Task.objects.create(
            product=self.product,
            step=1,
            name="biometrics",
            duration=2,
            duration_is_business_days=True,
            add_task_to_calendar=True,
            notify_customer=True,
            notify_days_before=1,
        )
        self.factory = APIRequestFactory()
        self.now = timezone.make_aware(datetime(2026, 2, 12, 9, 0, 0))

    @patch("notifications.services.providers.NotificationDispatcher.send", return_value="sent:1")
    @patch("django.utils.timezone.now")
    def test_create_sends_immediate_notification_when_due_tomorrow(self, now_mock, send_mock):
        now_mock.return_value = self.now
        request = self.factory.post("/")
        request.user = self.user

        serializer = DocApplicationCreateUpdateSerializer(
            data={
                "customer": self.customer.id,
                "product": self.product.id,
                "doc_date": self.now.date().isoformat(),
                "due_date": (self.now.date() + timedelta(days=1)).isoformat(),
                "notify_customer_too": True,
                "notify_customer_channel": DocApplication.NOTIFY_CHANNEL_EMAIL,
                "add_deadlines_to_calendar": True,
                "notes": "create immediate",
            },
            context={"request": request},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        application = serializer.save()

        send_mock.assert_called_once()
        notification = WorkflowNotification.objects.get(doc_application=application)
        self.assertEqual(notification.status, WorkflowNotification.STATUS_SENT)
        self.assertEqual(notification.scheduled_for.date(), self.now.date())

    @patch("notifications.services.providers.NotificationDispatcher.send", return_value="sent:1")
    @patch("django.utils.timezone.now")
    def test_update_sends_immediate_notification_when_due_date_becomes_tomorrow(self, now_mock, send_mock):
        now_mock.return_value = self.now

        application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=self.now.date(),
            due_date=self.now.date() + timedelta(days=3),
            notify_customer_too=True,
            notify_customer_channel=DocApplication.NOTIFY_CHANNEL_EMAIL,
            created_by=self.user,
            add_deadlines_to_calendar=True,
        )
        Document.objects.create(
            doc_application=application,
            doc_type=self.passport_doc_type,
            required=True,
            completed=False,
            created_by=self.user,
        )

        request = self.factory.patch("/")
        request.user = self.user
        serializer = DocApplicationCreateUpdateSerializer(
            instance=application,
            data={"due_date": (self.now.date() + timedelta(days=1)).isoformat()},
            partial=True,
            context={"request": request},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        application = serializer.save()

        send_mock.assert_called_once()
        notification = WorkflowNotification.objects.get(doc_application=application)
        self.assertEqual(notification.status, WorkflowNotification.STATUS_SENT)
        self.assertEqual(notification.scheduled_for.date(), self.now.date())
