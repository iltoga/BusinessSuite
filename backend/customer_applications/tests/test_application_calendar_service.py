from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from core.models.calendar_event import CalendarEvent
from customer_applications.models import DocApplication, WorkflowNotification
from customer_applications.services.application_calendar_service import ApplicationCalendarService
from customers.models import Customer
from products.models import Product, Task

User = get_user_model()


class ApplicationCalendarServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("calendar-user", "calendar@example.com", "pass")
        self.customer = Customer.objects.create(first_name="Calendar", last_name="Tester")
        self.product = Product.objects.create(name="Test Product", code="TP-CALENDAR", required_documents="Passport")
        self.task = Task.objects.create(
            product=self.product,
            step=1,
            name="Submit Documents",
            duration=5,
            duration_is_business_days=False,
            notify_days_before=2,
            add_task_to_calendar=True,
        )
        self.application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=date(2026, 1, 10),
            due_date=date(2026, 1, 20),
            add_deadlines_to_calendar=True,
            created_by=self.user,
        )

    def test_sync_creates_local_calendar_event_with_pinned_application_id(self):
        with patch("core.signals_calendar.create_google_event_task") as create_sync_mock:
            with self.captureOnCommitCallbacks(execute=True):
                event = ApplicationCalendarService().sync_next_task_deadline(self.application)

        self.assertIsNotNone(event)
        self.assertEqual(event.start_date.isoformat(), "2026-01-20")
        self.assertEqual(event.notifications["overrides"][0]["minutes"], 2 * 24 * 60)
        self.assertEqual(
            event.extended_properties["private"]["revisbali_customer_application_id"],
            str(self.application.id),
        )
        self.assertEqual(event.extended_properties["private"]["revisbali_entity"], "customer_application")
        self.assertEqual(event.source, CalendarEvent.SOURCE_APPLICATION)
        create_sync_mock.assert_called_once_with(event_id=event.id)

        self.application.refresh_from_db()
        self.assertEqual(self.application.calendar_event_id, event.id)

    def test_sync_updates_existing_calendar_event_when_due_date_changes(self):
        with (
            patch("core.signals_calendar.create_google_event_task") as create_sync_mock,
            patch("core.signals_calendar.update_google_event_task") as update_sync_mock,
        ):
            with self.captureOnCommitCallbacks(execute=True):
                old_event = ApplicationCalendarService().sync_next_task_deadline(self.application)

            previous_due_date = self.application.due_date
            self.application.due_date = date(2026, 1, 25)
            self.application.save(update_fields=["due_date", "updated_at"])

            with self.captureOnCommitCallbacks(execute=True):
                updated_event = ApplicationCalendarService().sync_next_task_deadline(
                    self.application,
                    previous_due_date=previous_due_date,
                )

        self.assertEqual(old_event.id, updated_event.id)
        self.assertEqual(updated_event.start_date.isoformat(), "2026-01-25")
        self.assertTrue(CalendarEvent.objects.filter(pk=old_event.id).exists())
        self.assertEqual(CalendarEvent.objects.filter(application=self.application).count(), 1)
        create_sync_mock.assert_called_once_with(event_id=old_event.id)
        update_sync_mock.assert_called_once_with(event_id=old_event.id)

        self.application.refresh_from_db()
        self.assertEqual(self.application.calendar_event_id, updated_event.id)

    def test_sync_keeps_existing_events_when_no_next_calendar_task(self):
        with patch("core.signals_calendar.create_google_event_task"):
            with self.captureOnCommitCallbacks(execute=True):
                old_event = ApplicationCalendarService().sync_next_task_deadline(self.application)

        self.task.add_task_to_calendar = False
        self.task.save(update_fields=["add_task_to_calendar"])

        result = ApplicationCalendarService().sync_next_task_deadline(self.application)

        self.assertIsNone(result)
        self.assertTrue(CalendarEvent.objects.filter(pk=old_event.id).exists())
        self.application.refresh_from_db()
        self.assertIsNone(self.application.calendar_event_id)

    @patch("customer_applications.tasks.sync_application_calendar_task")
    def test_delete_signal_queues_calendar_cleanup_task(self, sync_task_mock):
        application_id = self.application.id
        self.application.calendar_event_id = "local-app-100"
        self.application.save(update_fields=["calendar_event_id", "updated_at"])
        WorkflowNotification.objects.create(
            channel=WorkflowNotification.CHANNEL_EMAIL,
            recipient="calendar@example.com",
            subject="Reminder",
            body="Body",
            doc_application=self.application,
            external_reference="evt-from-notification",
        )

        with self.captureOnCommitCallbacks(execute=True):
            self.application.delete()

        sync_task_mock.assert_called_once()
        kwargs = sync_task_mock.call_args.kwargs
        self.assertEqual(kwargs["application_id"], application_id)
        self.assertEqual(kwargs["action"], "delete")
        self.assertSetEqual(
            set(kwargs["known_event_ids"]),
            {"local-app-100", "evt-from-notification"},
        )
