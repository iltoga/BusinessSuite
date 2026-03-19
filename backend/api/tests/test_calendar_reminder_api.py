import json
import signal
from datetime import datetime, timedelta
from unittest.mock import patch

from core.models import CalendarReminder
from core.services.calendar_reminder_stream import (
    get_calendar_reminder_stream_cursor,
    reset_calendar_reminder_stream_state,
)
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

User = get_user_model()


class CalendarReminderApiTests(TestCase):
    def setUp(self):
        reset_calendar_reminder_stream_state()
        self.user = User.objects.create_user("reminder-owner", "owner@example.com", "pass")
        self.other_user = User.objects.create_user("reminder-target", "target@example.com", "pass")
        self.third_user = User.objects.create_user("other-owner", "other@example.com", "pass")
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def tearDown(self):
        reset_calendar_reminder_stream_state()

    def _decode_sse_payload(self, chunk):
        if isinstance(chunk, bytes):
            chunk = chunk.decode("utf-8")
        data_line = next((line for line in chunk.splitlines() if line.startswith("data: ")), "")
        self.assertTrue(data_line, f"Expected SSE data line in chunk: {chunk!r}")
        return json.loads(data_line.replace("data: ", "", 1))

    def _sse_iter(self, stream):
        """Return a per-stream SyncAsyncIter that runs in a dedicated event loop thread.
        
        NOTE: For tests that also do ORM writes between reads, use the async_to_sync
        pattern (wrapping the whole test body) instead, which guarantees the main
        thread handles all DB access.
        """
        key = id(stream)
        if not hasattr(self, '_sync_iters'):
            self._sync_iters = {}
        if key not in self._sync_iters:
            from api.tests.async_iter_helper import SyncAsyncIter
            self._sync_iters[key] = SyncAsyncIter(stream)
        return self._sync_iters[key]

    def _next_sse_payload_with_timeout(self, stream, timeout_seconds: int = 5):
        """Consume chunks from the stream, skipping keepalive lines, and return the first JSON payload."""
        import asyncio
        from asgiref.sync import async_to_sync

        async def _read():
            import asyncio
            while True:
                try:
                    chunk = await asyncio.wait_for(stream.__anext__(), timeout=timeout_seconds)
                except asyncio.TimeoutError:
                    raise TimeoutError(f"SSE stream read exceeded {timeout_seconds}s")
                if isinstance(chunk, bytes):
                    chunk = chunk.decode("utf-8")
                if chunk.startswith(":"):
                    continue
                return self._decode_sse_payload(chunk)

        return async_to_sync(_read)()

    def _next_sse_chunk_with_timeout(self, stream, timeout_seconds: int = 5):
        """Read the next raw chunk from the stream."""
        import asyncio
        from asgiref.sync import async_to_sync

        async def _read():
            try:
                return await asyncio.wait_for(stream.__anext__(), timeout=timeout_seconds)
            except asyncio.TimeoutError:
                raise TimeoutError(f"SSE stream read exceeded {timeout_seconds}s")

        return async_to_sync(_read)()

    def test_bulk_create_creates_one_record_per_user(self):
        response = self.client.post(
            "/api/calendar-reminders/bulk-create/",
            {
                "userIds": [self.user.id, self.other_user.id],
                "reminderDate": "2026-02-20",
                "reminderTime": "09:15",
                "timezone": "Asia/Makassar",
                "content": "Prepare customer documents",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.data), 2)
        created = CalendarReminder.objects.filter(created_by=self.user).order_by("id")
        self.assertEqual(created.count(), 2)
        self.assertEqual(set(created.values_list("user_id", flat=True)), {self.user.id, self.other_user.id})
        self.assertTrue(all(item.status == CalendarReminder.STATUS_PENDING for item in created))

    def test_create_defaults_to_logged_user_when_user_id_missing(self):
        response = self.client.post(
            "/api/calendar-reminders/",
            {
                "reminderDate": "2026-02-21",
                "reminderTime": "08:00",
                "timezone": "Asia/Makassar",
                "content": "Self reminder",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        reminder = CalendarReminder.objects.get(id=response.data["id"])
        self.assertEqual(reminder.user_id, self.user.id)
        self.assertEqual(reminder.created_by_id, self.user.id)

    def test_list_returns_only_created_by_current_user(self):
        own = CalendarReminder.objects.create(
            user=self.user,
            created_by=self.user,
            reminder_date=timezone.localdate(),
            reminder_time=timezone.localtime().time().replace(second=0, microsecond=0),
            timezone="Asia/Makassar",
            content="Owner reminder",
            status=CalendarReminder.STATUS_PENDING,
        )
        own.scheduled_for = timezone.now() + timedelta(minutes=30)
        own.save(update_fields=["scheduled_for", "updated_at"])

        CalendarReminder.objects.create(
            user=self.third_user,
            created_by=self.third_user,
            reminder_date=timezone.localdate(),
            reminder_time=timezone.localtime().time().replace(second=0, microsecond=0),
            timezone="Asia/Makassar",
            content="Other owner reminder",
            status=CalendarReminder.STATUS_PENDING,
        )

        response = self.client.get("/api/calendar-reminders/")
        self.assertEqual(response.status_code, 200)
        ids = [item["id"] for item in response.data["results"]]
        self.assertEqual(ids, [own.id])

    def test_list_status_filter(self):
        CalendarReminder.objects.create(
            user=self.user,
            created_by=self.user,
            reminder_date=timezone.localdate(),
            reminder_time=timezone.localtime().time().replace(second=0, microsecond=0),
            timezone="Asia/Makassar",
            content="Pending reminder",
            status=CalendarReminder.STATUS_PENDING,
        )
        CalendarReminder.objects.create(
            user=self.user,
            created_by=self.user,
            reminder_date=timezone.localdate(),
            reminder_time=timezone.localtime().time().replace(second=0, microsecond=0),
            timezone="Asia/Makassar",
            content="Sent reminder",
            status=CalendarReminder.STATUS_SENT,
            sent_at=timezone.now(),
        )

        response = self.client.get("/api/calendar-reminders/?status=pending")
        self.assertEqual(response.status_code, 200)
        statuses = [item["status"] for item in response.data["results"]]
        self.assertEqual(statuses, [CalendarReminder.STATUS_PENDING])

    def test_list_created_at_date_range_filter(self):
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)
        reminder_old = CalendarReminder.objects.create(
            user=self.user,
            created_by=self.user,
            reminder_date=today,
            reminder_time=timezone.localtime().time().replace(second=0, microsecond=0),
            timezone="Asia/Makassar",
            content="Yesterday created reminder",
            status=CalendarReminder.STATUS_PENDING,
        )
        reminder_today = CalendarReminder.objects.create(
            user=self.user,
            created_by=self.user,
            reminder_date=today,
            reminder_time=timezone.localtime().time().replace(second=0, microsecond=0),
            timezone="Asia/Makassar",
            content="Today created reminder",
            status=CalendarReminder.STATUS_PENDING,
        )

        tz = timezone.get_current_timezone()
        old_created_at = timezone.make_aware(datetime.combine(yesterday, datetime.min.time()), tz)
        today_created_at = timezone.make_aware(datetime.combine(today, datetime.min.time()), tz)
        CalendarReminder.objects.filter(pk=reminder_old.pk).update(created_at=old_created_at)
        CalendarReminder.objects.filter(pk=reminder_today.pk).update(created_at=today_created_at)

        response = self.client.get(f"/api/calendar-reminders/?created_from={today}&created_to={today}")
        self.assertEqual(response.status_code, 200)
        ids = [item["id"] for item in response.data["results"]]
        self.assertIn(reminder_today.id, ids)
        self.assertNotIn(reminder_old.id, ids)

    def test_partial_update_resets_status_to_pending(self):
        reminder = CalendarReminder.objects.create(
            user=self.user,
            created_by=self.user,
            reminder_date=timezone.localdate(),
            reminder_time=timezone.localtime().time().replace(second=0, microsecond=0),
            timezone="Asia/Makassar",
            content="Old content",
            status=CalendarReminder.STATUS_SENT,
            sent_at=timezone.now(),
            error_message="",
        )

        response = self.client.patch(
            f"/api/calendar-reminders/{reminder.id}/",
            {"content": "Updated content"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        reminder.refresh_from_db()
        self.assertEqual(reminder.content, "Updated content")
        self.assertEqual(reminder.status, CalendarReminder.STATUS_PENDING)
        self.assertIsNone(reminder.sent_at)
        self.assertEqual(reminder.error_message, "")

    def test_users_and_timezones_actions(self):
        response_users = self.client.get("/api/calendar-reminders/users/?q=reminder")
        self.assertEqual(response_users.status_code, 200)
        self.assertTrue(any(item["id"] == self.user.id for item in response_users.data))

        response_timezones = self.client.get("/api/calendar-reminders/timezones/?q=makassar")
        self.assertEqual(response_timezones.status_code, 200)
        self.assertTrue(any(item["value"] == "Asia/Makassar" for item in response_timezones.data))

    def test_inbox_returns_today_sent_reminders_for_authenticated_recipient(self):
        today = timezone.localdate()
        now = timezone.now()
        target = CalendarReminder.objects.create(
            user=self.user,
            created_by=self.other_user,
            reminder_date=today,
            reminder_time=timezone.localtime().time().replace(second=0, microsecond=0),
            timezone="Asia/Makassar",
            content="Recipient reminder",
            status=CalendarReminder.STATUS_SENT,
            sent_at=now,
        )
        CalendarReminder.objects.create(
            user=self.user,
            created_by=self.other_user,
            reminder_date=today,
            reminder_time=timezone.localtime().time().replace(second=0, microsecond=0),
            timezone="Asia/Makassar",
            content="Already read reminder",
            status=CalendarReminder.STATUS_SENT,
            sent_at=now,
            read_at=now,
        )
        CalendarReminder.objects.create(
            user=self.user,
            created_by=self.other_user,
            reminder_date=today - timedelta(days=1),
            reminder_time=timezone.localtime().time().replace(second=0, microsecond=0),
            timezone="Asia/Makassar",
            content="Yesterday reminder",
            status=CalendarReminder.STATUS_SENT,
            sent_at=now - timedelta(days=1),
        )

        response = self.client.get("/api/calendar-reminders/inbox/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["unreadCount"], 1)
        returned_ids = [item["id"] for item in response.data["today"]]
        self.assertIn(target.id, returned_ids)
        self.assertEqual(len(returned_ids), 2)

    def test_inbox_mark_read_marks_only_current_user_records(self):
        today = timezone.localdate()
        now = timezone.now()
        device_label = "MacBook Pro (en-US)"
        own = CalendarReminder.objects.create(
            user=self.user,
            created_by=self.other_user,
            reminder_date=today,
            reminder_time=timezone.localtime().time().replace(second=0, microsecond=0),
            timezone="Asia/Makassar",
            content="Own unread reminder",
            status=CalendarReminder.STATUS_SENT,
            sent_at=now,
        )
        foreign = CalendarReminder.objects.create(
            user=self.other_user,
            created_by=self.user,
            reminder_date=today,
            reminder_time=timezone.localtime().time().replace(second=0, microsecond=0),
            timezone="Asia/Makassar",
            content="Foreign unread reminder",
            status=CalendarReminder.STATUS_SENT,
            sent_at=now,
        )

        response = self.client.post(
            "/api/calendar-reminders/inbox/mark-read/",
            {"ids": [own.id, foreign.id], "deviceLabel": device_label},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["updated"], 1)
        self.assertEqual(response.data["unreadCount"], 0)

        own.refresh_from_db()
        foreign.refresh_from_db()
        self.assertIsNotNone(own.read_at)
        self.assertEqual(own.read_device_label, device_label)
        self.assertIsNone(foreign.read_at)
        self.assertEqual(foreign.read_device_label, "")

    def test_inbox_snooze_reschedules_sent_unread_reminder(self):
        today = timezone.localdate()
        now = timezone.now()
        reminder = CalendarReminder.objects.create(
            user=self.user,
            created_by=self.other_user,
            reminder_date=today,
            reminder_time=timezone.localtime().time().replace(second=0, microsecond=0),
            timezone="Asia/Makassar",
            content="Snooze me",
            status=CalendarReminder.STATUS_SENT,
            sent_at=now,
        )

        response = self.client.post(
            "/api/calendar-reminders/inbox/snooze/",
            {
                "id": reminder.id,
                "minutes": 15,
                "deviceLabel": "Electron Desktop notification (action: snooze-15m)",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], reminder.id)
        self.assertEqual(response.data["minutes"], 15)
        self.assertEqual(response.data["unreadCount"], 0)
        self.assertIn("scheduledFor", response.data)

        reminder.refresh_from_db()
        self.assertEqual(reminder.status, CalendarReminder.STATUS_PENDING)
        self.assertIsNone(reminder.sent_at)
        self.assertIsNone(reminder.read_at)
        self.assertEqual(reminder.delivery_channel, "")
        self.assertEqual(reminder.delivery_device_label, "")
        self.assertEqual(reminder.error_message, "")
        self.assertEqual(reminder.read_device_label, "")
        self.assertGreater(reminder.scheduled_for, now + timedelta(minutes=13))
        self.assertLess(reminder.scheduled_for, now + timedelta(minutes=16))

    def test_ack_records_delivery_channel_and_device_label(self):
        reminder = CalendarReminder.objects.create(
            user=self.user,
            created_by=self.user,
            reminder_date=timezone.localdate(),
            reminder_time=timezone.localtime().time().replace(second=0, microsecond=0),
            timezone="Asia/Makassar",
            content="Ack reminder",
            status=CalendarReminder.STATUS_SENT,
            sent_at=timezone.now(),
        )

        response = self.client.post(
            f"/api/calendar-reminders/{reminder.id}/ack/",
            {"channel": "in_app", "deviceLabel": "Desktop Chrome"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        reminder.refresh_from_db()
        self.assertEqual(reminder.delivery_channel, CalendarReminder.DELIVERY_IN_APP)
        self.assertEqual(reminder.delivery_device_label, "Desktop Chrome")

        second = self.client.post(
            f"/api/calendar-reminders/{reminder.id}/ack/",
            {"channel": "system", "deviceLabel": "Android Chrome"},
            format="json",
        )
        self.assertEqual(second.status_code, 200)
        reminder.refresh_from_db()
        self.assertEqual(reminder.delivery_channel, CalendarReminder.DELIVERY_IN_APP)
        self.assertEqual(reminder.delivery_device_label, "Desktop Chrome")

    def test_stream_returns_snapshot_and_changed_event(self):
        from asgiref.sync import async_to_sync

        @async_to_sync
        async def run_test():
            from asgiref.sync import sync_to_async
            import asyncio
            import json

            reminder = await sync_to_async(CalendarReminder.objects.create)(
                user=self.user,
                created_by=self.user,
                reminder_date=timezone.localdate(),
                reminder_time=timezone.localtime().time().replace(second=0, microsecond=0),
                timezone="Asia/Makassar",
                content="SSE reminder",
                status=CalendarReminder.STATUS_PENDING,
            )

            await sync_to_async(self.client.credentials)(HTTP_AUTHORIZATION=f"Bearer {self.token.key}")
            response = await sync_to_async(self.client.get)("/api/calendar-reminders/stream/")
            await sync_to_async(self.assertEqual)(response.status_code, 200)

            stream = response.streaming_content

            async def get_payload():
                while True:
                    try:
                        chunk = await asyncio.wait_for(anext(stream), timeout=5.0)
                    except asyncio.TimeoutError:
                        raise TimeoutError("SSE stream read exceeded 5s")
                    if isinstance(chunk, bytes):
                        chunk = chunk.decode("utf-8")
                    if chunk.startswith(":"):
                        continue
                    data_line = next((line for line in chunk.splitlines() if line.startswith("data: ")), "")
                    if not data_line:
                        continue
                    return json.loads(data_line.replace("data: ", "", 1))

            payload = await get_payload()
            await sync_to_async(self.assertEqual)(payload["event"], "calendar_reminders_snapshot")
            await sync_to_async(self.assertEqual)(payload["reason"], "initial")
            await sync_to_async(self.assertEqual)(payload["lastReminderId"], reminder.id)

            reminder.status = CalendarReminder.STATUS_FAILED
            reminder.error_message = "Delivery error"
            await sync_to_async(reminder.save)(update_fields=["status", "error_message", "updated_at"])

            changed_payload = await get_payload()
            if changed_payload.get("event") == "calendar_reminders_error":
                print("\n\nERROR PAYLOAD:", changed_payload, "\n\n")
                
            await sync_to_async(self.assertEqual)(changed_payload["event"], "calendar_reminders_changed")
            await sync_to_async(self.assertEqual)(changed_payload["lastReminderId"], reminder.id)
            await sync_to_async(self.assertIn)(changed_payload["reason"], {"signal", "db_state_change"})

        run_test()

    def test_stream_ignores_updates_for_other_creators_cursor_still_advances(self):
        reminder = CalendarReminder.objects.create(
            user=self.third_user,
            created_by=self.third_user,
            reminder_date=timezone.localdate(),
            reminder_time=timezone.localtime().time().replace(second=0, microsecond=0),
            timezone="Asia/Makassar",
            content="Foreign reminder",
            status=CalendarReminder.STATUS_PENDING,
        )
        before_cursor = get_calendar_reminder_stream_cursor()
        reminder.status = CalendarReminder.STATUS_FAILED
        reminder.save(update_fields=["status", "updated_at"])
        after_cursor = get_calendar_reminder_stream_cursor()
        self.assertGreater(after_cursor, before_cursor)

    def _mock_keepalive_events(*args, **kwargs):
        yield None

    @patch("api.utils.redis_sse.iter_replay_and_live_events", side_effect=_mock_keepalive_events)
    def test_stream_emits_keepalive_when_idle(self, _iter_events):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token.key}")
        response = self.client.get("/api/calendar-reminders/stream/")
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
