import json
from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import CalendarReminder
from core.services.calendar_reminder_stream import (
    get_calendar_reminder_stream_cursor,
    reset_calendar_reminder_stream_state,
)

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
            {"ids": [own.id, foreign.id]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["updated"], 1)
        self.assertEqual(response.data["unreadCount"], 0)

        own.refresh_from_db()
        foreign.refresh_from_db()
        self.assertIsNotNone(own.read_at)
        self.assertIsNone(foreign.read_at)

    def test_stream_returns_snapshot_and_changed_event(self):
        reminder = CalendarReminder.objects.create(
            user=self.user,
            created_by=self.user,
            reminder_date=timezone.localdate(),
            reminder_time=timezone.localtime().time().replace(second=0, microsecond=0),
            timezone="Asia/Makassar",
            content="SSE reminder",
            status=CalendarReminder.STATUS_PENDING,
        )

        response = self.client.get(f"/api/calendar-reminders/stream/?token={self.token.key}")
        self.assertEqual(response.status_code, 200)
        payload = self._decode_sse_payload(next(response.streaming_content))
        self.assertEqual(payload["event"], "calendar_reminders_snapshot")
        self.assertEqual(payload["reason"], "initial")
        self.assertEqual(payload["lastReminderId"], reminder.id)

        reminder.status = CalendarReminder.STATUS_FAILED
        reminder.error_message = "Delivery error"
        reminder.save(update_fields=["status", "error_message", "updated_at"])

        changed_payload = self._decode_sse_payload(next(response.streaming_content))
        self.assertEqual(changed_payload["event"], "calendar_reminders_changed")
        self.assertEqual(changed_payload["lastReminderId"], reminder.id)
        self.assertIn(changed_payload["reason"], {"signal", "db_state_change"})

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
