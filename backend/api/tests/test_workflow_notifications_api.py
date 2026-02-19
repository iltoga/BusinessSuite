import json
from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from customer_applications.models import DocApplication, WorkflowNotification
from customer_applications.services.workflow_notification_stream import (
    get_workflow_notification_stream_cursor,
    reset_workflow_notification_stream_state,
)
from customers.models import Customer
from products.models import Product

User = get_user_model()


class WorkflowNotificationApiTests(TestCase):
    def setUp(self):
        reset_workflow_notification_stream_state()
        self.user = User.objects.create_superuser("workflow-admin", "workflowadmin@example.com", "pass")
        self.token = Token.objects.create(user=self.user)
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

    def tearDown(self):
        reset_workflow_notification_stream_state()

    def _decode_sse_payload(self, chunk):
        if isinstance(chunk, bytes):
            chunk = chunk.decode("utf-8")
        data_line = next((line for line in chunk.splitlines() if line.startswith("data: ")), "")
        self.assertTrue(data_line, f"Expected SSE data line in chunk: {chunk!r}")
        return json.loads(data_line.replace("data: ", "", 1))

    @patch("customer_applications.tasks.schedule_whatsapp_status_poll")
    @patch("notifications.services.providers.NotificationDispatcher.send")
    def test_resend_keeps_status_pending_when_provider_returns_queued_placeholder(self, send_mock, schedule_poll_mock):
        send_mock.return_value = "queued_whatsapp:+628123456789"

        response = self.client.post(f"/api/workflow-notifications/{self.notification.id}/resend/", {}, format="json")

        self.assertEqual(response.status_code, 200)
        self.notification.refresh_from_db()
        self.assertEqual(self.notification.status, WorkflowNotification.STATUS_PENDING)
        self.assertEqual(self.notification.external_reference, "")
        self.assertEqual(self.notification.provider_message, "queued_whatsapp:+628123456789")
        self.assertIsNone(self.notification.sent_at)
        self.assertIsNotNone(self.notification.scheduled_for)
        schedule_poll_mock.assert_not_called()

    @patch("customer_applications.tasks.schedule_whatsapp_status_poll")
    @patch("notifications.services.providers.NotificationDispatcher.send")
    def test_resend_updates_whatsapp_external_reference_when_accepted(self, send_mock, schedule_poll_mock):
        send_mock.return_value = "wamid.HBgL123"

        response = self.client.post(f"/api/workflow-notifications/{self.notification.id}/resend/", {}, format="json")

        self.assertEqual(response.status_code, 200)
        self.notification.refresh_from_db()
        self.assertEqual(self.notification.status, WorkflowNotification.STATUS_PENDING)
        self.assertEqual(self.notification.external_reference, "wamid.HBgL123")
        self.assertIsNone(self.notification.sent_at)
        self.assertIsNotNone(self.notification.scheduled_for)
        schedule_poll_mock.assert_called_once_with(notification_id=self.notification.id, delay_seconds=5)

    def test_stream_returns_initial_snapshot_event(self):
        response = self.client.get(f"/api/workflow-notifications/stream/?token={self.token.key}")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/event-stream"))
        payload = self._decode_sse_payload(next(response.streaming_content))
        self.assertEqual(payload["event"], "workflow_notifications_snapshot")
        self.assertEqual(payload["reason"], "initial")
        self.assertEqual(payload["windowHours"], 24)
        self.assertEqual(payload["lastNotificationId"], self.notification.id)
        self.assertIsNotNone(payload["lastUpdatedAt"])

    def test_stream_emits_changed_event_after_notification_update(self):
        response = self.client.get(f"/api/workflow-notifications/stream/?token={self.token.key}")
        _ = self._decode_sse_payload(next(response.streaming_content))

        self.notification.status = WorkflowNotification.STATUS_DELIVERED
        self.notification.save(update_fields=["status", "updated_at"])

        payload = self._decode_sse_payload(next(response.streaming_content))
        self.assertEqual(payload["event"], "workflow_notifications_changed")
        self.assertEqual(payload["lastNotificationId"], self.notification.id)
        self.assertIn(payload["reason"], {"signal", "db_state_change"})

    def test_stream_requires_staff_or_admin_permissions(self):
        plain_user = User.objects.create_user("workflow-viewer", "workflowviewer@example.com", "pass")
        plain_token = Token.objects.create(user=plain_user)
        unauthenticated_client = APIClient()
        response = unauthenticated_client.get(f"/api/workflow-notifications/stream/?token={plain_token.key}")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "Staff or 'admin' group permission required")

    def test_updating_old_notification_does_not_bump_stream_cursor(self):
        WorkflowNotification.objects.filter(pk=self.notification.id).update(created_at=timezone.now() - timedelta(days=2))
        self.notification.refresh_from_db()
        before_cursor = get_workflow_notification_stream_cursor()

        self.notification.status = WorkflowNotification.STATUS_DELIVERED
        self.notification.save(update_fields=["status", "updated_at"])
        after_cursor = get_workflow_notification_stream_cursor()

        self.assertEqual(after_cursor, before_cursor)
