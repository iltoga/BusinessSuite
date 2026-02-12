from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from customer_applications.models import DocApplication
from customer_applications.tasks import SYNC_ACTION_UPSERT, sync_application_calendar_task
from customers.models import Customer
from products.models import Product, Task

User = get_user_model()


def _run_sync_task_locally(**kwargs):
    if hasattr(sync_application_calendar_task, "call_local"):
        return sync_application_calendar_task.call_local(**kwargs)
    if hasattr(sync_application_calendar_task, "func"):
        return sync_application_calendar_task.func(**kwargs)
    return sync_application_calendar_task(**kwargs)


class CalendarSyncFailurePushTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("calendar-push-user", "calendarpush@example.com", "pass")
        self.customer = Customer.objects.create(first_name="Calendar", last_name="Push")
        self.product = Product.objects.create(name="Calendar Product", code="CAL-PUSH", required_documents="")
        Task.objects.create(
            product=self.product,
            step=1,
            name="Review docs",
            duration=2,
            duration_is_business_days=False,
            add_task_to_calendar=True,
            notify_days_before=1,
        )
        self.application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=date(2026, 1, 10),
            due_date=date(2026, 1, 20),
            notes="Needs manual fallback if sync fails.",
            created_by=self.user,
        )

    @patch("core.services.push_notifications.push_notification_service.PushNotificationService.send_to_user")
    @patch("customer_applications.services.application_calendar_service.ApplicationCalendarService.sync_next_task_deadline")
    def test_sync_failure_triggers_push_notification(self, sync_mock, push_mock):
        sync_mock.side_effect = RuntimeError("Google Calendar temporary outage")

        result = _run_sync_task_locally(
            application_id=self.application.id,
            user_id=self.user.id,
            action=SYNC_ACTION_UPSERT,
            previous_due_date=self.application.due_date.isoformat(),
        )

        self.assertEqual(result["status"], "failed")
        self.assertIn("Google Calendar temporary outage", result["error"])
        push_mock.assert_called_once()
        kwargs = push_mock.call_args.kwargs
        self.assertEqual(kwargs["user"], self.user)
        self.assertEqual(kwargs["title"], "Calendar Sync Failed")
        self.assertIn("calendar_sync_failed", kwargs["data"]["type"])
