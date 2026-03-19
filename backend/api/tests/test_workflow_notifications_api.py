import json
from datetime import date, timedelta
from unittest.mock import patch

from customer_applications.models import DocApplication, WorkflowNotification
from customer_applications.services.workflow_notification_stream import (
    get_workflow_notification_stream_cursor,
    reset_workflow_notification_stream_state,
)
from customers.models import Customer
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from products.models import Product
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

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

    def _next_sse_payload(self, stream):
        """Skip keepalive lines and return the first JSON payload from an async stream.
        Each call runs a fresh async_to_sync so it stays on the main thread.
        """
        import asyncio
        from asgiref.sync import async_to_sync

        async def _read():
            while True:
                try:
                    chunk = await asyncio.wait_for(stream.__anext__(), timeout=5)
                except asyncio.TimeoutError:
                    raise TimeoutError("SSE stream read exceeded 5s")
                if isinstance(chunk, bytes):
                    chunk = chunk.decode("utf-8")
                if chunk.startswith(":"):
                    continue
                return self._decode_sse_payload(chunk)

        return async_to_sync(_read)()

    def test_stream_returns_initial_snapshot_event(self):
        from asgiref.sync import async_to_sync

        @async_to_sync
        async def run_test():
            import asyncio, json
            from asgiref.sync import sync_to_async

            await sync_to_async(self.client.credentials)(HTTP_AUTHORIZATION=f"Bearer {self.token.key}")
            response = await sync_to_async(self.client.get)("/api/workflow-notifications/stream/")
            await sync_to_async(self.assertEqual)(response.status_code, 200)
            await sync_to_async(self.assertTrue)(response["Content-Type"].startswith("text/event-stream"))

            stream = response.streaming_content

            async def get_payload():
                while True:
                    try:
                        chunk = await asyncio.wait_for(stream.__anext__(), timeout=5)
                    except asyncio.TimeoutError:
                        raise TimeoutError("SSE stream read exceeded 5s")
                    if isinstance(chunk, bytes):
                        chunk = chunk.decode("utf-8")
                    if chunk.startswith(":"):
                        continue
                    data_line = next((c for c in chunk.splitlines() if c.startswith("data: ")), "")
                    if not data_line:
                        continue
                    return json.loads(data_line.replace("data: ", "", 1))

            payload = await get_payload()
            await sync_to_async(self.assertEqual)(payload["event"], "workflow_notifications_snapshot")
            await sync_to_async(self.assertEqual)(payload["reason"], "initial")
            await sync_to_async(self.assertEqual)(payload["windowHours"], 24)
            await sync_to_async(self.assertEqual)(payload["lastNotificationId"], self.notification.id)
            await sync_to_async(self.assertIsNotNone)(payload["lastUpdatedAt"])

        run_test()

    def test_stream_emits_changed_event_after_notification_update(self):
        from asgiref.sync import async_to_sync

        @async_to_sync
        async def run_test():
            import asyncio, json
            from asgiref.sync import sync_to_async

            await sync_to_async(self.client.credentials)(HTTP_AUTHORIZATION=f"Bearer {self.token.key}")
            response = await sync_to_async(self.client.get)("/api/workflow-notifications/stream/")

            stream = response.streaming_content

            async def get_payload():
                while True:
                    try:
                        chunk = await asyncio.wait_for(stream.__anext__(), timeout=5)
                    except asyncio.TimeoutError:
                        raise TimeoutError("SSE stream read exceeded 5s")
                    if isinstance(chunk, bytes):
                        chunk = chunk.decode("utf-8")
                    if chunk.startswith(":"):
                        continue
                    data_line = next((c for c in chunk.splitlines() if c.startswith("data: ")), "")
                    if not data_line:
                        continue
                    return json.loads(data_line.replace("data: ", "", 1))

            _ = await get_payload()  # consume snapshot

            self.notification.status = WorkflowNotification.STATUS_DELIVERED
            await sync_to_async(self.notification.save)(update_fields=["status", "updated_at"])

            payload = await get_payload()
            await sync_to_async(self.assertEqual)(payload["event"], "workflow_notifications_changed")
            await sync_to_async(self.assertEqual)(payload["lastNotificationId"], self.notification.id)
            await sync_to_async(self.assertIn)(payload["reason"], {"signal", "db_state_change"})

        run_test()


    def test_stream_requires_staff_or_admin_permissions(self):
        plain_user = User.objects.create_user("workflow-viewer", "workflowviewer@example.com", "pass")
        plain_token = Token.objects.create(user=plain_user)
        unauthenticated_client = APIClient()
        unauthenticated_client.credentials(HTTP_AUTHORIZATION=f"Bearer {plain_token.key}")
        response = unauthenticated_client.get("/api/workflow-notifications/stream/")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "Staff or 'admin' group permission required")

    def test_updating_old_notification_does_not_bump_stream_cursor(self):
        WorkflowNotification.objects.filter(pk=self.notification.id).update(
            created_at=timezone.now() - timedelta(days=2)
        )
        self.notification.refresh_from_db()
        before_cursor = get_workflow_notification_stream_cursor()

        self.notification.status = WorkflowNotification.STATUS_DELIVERED
        self.notification.save(update_fields=["status", "updated_at"])
        after_cursor = get_workflow_notification_stream_cursor()

        self.assertEqual(after_cursor, before_cursor)

    def _mock_keepalive_events(*args, **kwargs):
        yield None

    @patch("api.utils.redis_sse.iter_replay_and_live_events", side_effect=_mock_keepalive_events)
    def test_stream_emits_keepalive_when_idle(self, _iter_events):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token.key}")
        response = self.client.get("/api/workflow-notifications/stream/")
        self.assertEqual(response.status_code, 200)

        stream = response.streaming_content

        # First item: initial snapshot
        snapshot_chunk = next(stream)
        if isinstance(snapshot_chunk, bytes):
            snapshot_chunk = snapshot_chunk.decode("utf-8")
        _ = self._decode_sse_payload(snapshot_chunk)

        # Second item: keepalive
        keepalive_chunk = next(stream)
        if isinstance(keepalive_chunk, bytes):
            keepalive_chunk = keepalive_chunk.decode("utf-8")
        self.assertEqual(keepalive_chunk, ": keepalive\n\n")
