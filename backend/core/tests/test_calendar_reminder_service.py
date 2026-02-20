from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from core.models import CalendarReminder
from core.services.calendar_reminder_service import CalendarReminderService
from core.services.push_notifications import PushNotificationResult

User = get_user_model()


class _StubPushService:
    def __init__(self, *, result=None, exc: Exception | None = None):
        self._result = result or PushNotificationResult(sent=1, failed=0, skipped=0)
        self._exc = exc
        self.calls = []

    def send_to_user(self, **kwargs):
        self.calls.append(kwargs)
        if self._exc is not None:
            raise self._exc
        return self._result


class CalendarReminderServiceTests(TestCase):
    def setUp(self):
        self.creator = User.objects.create_user("reminder-creator", "creator@example.com", "pass")
        self.target_user = User.objects.create_user("reminder-target", "target@example.com", "pass")

    def test_create_for_users_creates_one_reminder_per_user(self):
        reminders = CalendarReminderService().create_for_users(
            created_by=self.creator,
            user_ids=[self.creator.id, self.target_user.id],
            reminder_date=timezone.localdate(),
            reminder_time=timezone.localtime().time().replace(second=0, microsecond=0),
            timezone_name="Asia/Makassar",
            content="Call customer for follow-up",
        )

        self.assertEqual(len(reminders), 2)
        self.assertEqual(
            CalendarReminder.objects.filter(created_by=self.creator).count(),
            2,
        )
        self.assertTrue(all(reminder.status == CalendarReminder.STATUS_PENDING for reminder in reminders))

    def test_dispatch_due_reminders_marks_sent_when_push_succeeds(self):
        now = timezone.now()
        reminder = CalendarReminder.objects.create(
            user=self.target_user,
            created_by=self.creator,
            reminder_date=timezone.localdate(now - timedelta(days=1)),
            reminder_time=timezone.localtime(now - timedelta(hours=2)).time().replace(second=0, microsecond=0),
            timezone="Asia/Makassar",
            content="Past reminder",
            status=CalendarReminder.STATUS_PENDING,
        )
        reminder.scheduled_for = timezone.now() - timedelta(minutes=5)
        reminder.save(update_fields=["scheduled_for", "updated_at"])

        service = CalendarReminderService(
            push_service=_StubPushService(result=PushNotificationResult(sent=1, failed=0, skipped=0))
        )
        stats = service.dispatch_due_reminders(limit=50)

        self.assertEqual(stats.sent, 1)
        self.assertEqual(stats.failed, 0)
        reminder.refresh_from_db()
        self.assertEqual(reminder.status, CalendarReminder.STATUS_SENT)
        self.assertIsNotNone(reminder.sent_at)
        self.assertEqual(reminder.error_message, "")

    def test_dispatch_due_reminders_marks_failed_when_user_has_no_subscriptions(self):
        reminder = CalendarReminder.objects.create(
            user=self.target_user,
            created_by=self.creator,
            reminder_date=timezone.localdate(),
            reminder_time=timezone.localtime().time().replace(second=0, microsecond=0),
            timezone="Asia/Makassar",
            content="No subscription reminder",
            status=CalendarReminder.STATUS_PENDING,
        )
        reminder.scheduled_for = timezone.now() - timedelta(minutes=1)
        reminder.save(update_fields=["scheduled_for", "updated_at"])

        service = CalendarReminderService(
            push_service=_StubPushService(result=PushNotificationResult(sent=0, failed=0, skipped=1))
        )
        stats = service.dispatch_due_reminders(limit=50)

        self.assertEqual(stats.sent, 0)
        self.assertEqual(stats.failed, 1)
        reminder.refresh_from_db()
        self.assertEqual(reminder.status, CalendarReminder.STATUS_FAILED)
        self.assertIn("No active push subscriptions", reminder.error_message)
