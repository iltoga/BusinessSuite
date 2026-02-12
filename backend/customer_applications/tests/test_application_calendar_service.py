from datetime import date
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

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

    @patch("customer_applications.services.application_calendar_service.GoogleClient")
    def test_sync_creates_calendar_event_with_pinned_application_id(self, google_client_cls):
        mock_client = google_client_cls.return_value
        mock_client.create_event.return_value = {"id": "evt-created"}
        mock_client.list_events.return_value = []

        ApplicationCalendarService().sync_next_task_deadline(self.application)

        payload = mock_client.create_event.call_args.args[0]
        self.assertEqual(payload["start_date"], "2026-01-20")
        self.assertEqual(payload["reminders"]["overrides"][0]["minutes"], 2 * 24 * 60)
        self.assertEqual(
            payload["extended_properties"]["private"]["revisbali_customer_application_id"],
            str(self.application.id),
        )
        self.assertEqual(payload["extended_properties"]["private"]["revisbali_entity"], "customer_application")

        self.application.refresh_from_db()
        self.assertEqual(self.application.calendar_event_id, "evt-created")

    @patch("customer_applications.services.application_calendar_service.GoogleClient")
    def test_sync_recreates_calendar_event_when_due_date_changes(self, google_client_cls):
        self.application.calendar_event_id = "evt-old"
        self.application.save(update_fields=["calendar_event_id", "updated_at"])

        previous_due_date = self.application.due_date
        self.application.due_date = date(2026, 1, 25)
        self.application.save(update_fields=["due_date", "updated_at"])

        mock_client = google_client_cls.return_value
        mock_client.list_events.return_value = []
        mock_client.create_event.return_value = {"id": "evt-new"}

        ApplicationCalendarService().sync_next_task_deadline(
            self.application,
            previous_due_date=previous_due_date,
        )

        mock_client.delete_event.assert_any_call(
            "evt-old",
            calendar_id=getattr(settings, "GOOGLE_CALENDAR_ID", "primary"),
        )
        payload = mock_client.create_event.call_args.args[0]
        self.assertEqual(payload["start_date"], "2026-01-25")

        self.application.refresh_from_db()
        self.assertEqual(self.application.calendar_event_id, "evt-new")

    @patch("customer_applications.services.application_calendar_service.GoogleClient")
    def test_delete_signal_cleans_all_related_calendar_events(self, google_client_cls):
        application_id = self.application.id
        self.application.calendar_event_id = "evt-primary"
        self.application.save(update_fields=["calendar_event_id", "updated_at"])
        WorkflowNotification.objects.create(
            channel=WorkflowNotification.CHANNEL_EMAIL,
            recipient="calendar@example.com",
            subject="Reminder",
            body="Body",
            doc_application=self.application,
            external_reference="evt-from-notification",
        )

        mock_client = google_client_cls.return_value
        mock_client.list_events.side_effect = [
            [{"id": "evt-by-property"}],
            [{"id": "evt-legacy", "summary": f"[Application #{application_id}] legacy event"}],
        ]

        self.application.delete()

        deleted_event_ids = {call.args[0] for call in mock_client.delete_event.call_args_list}
        self.assertSetEqual(
            deleted_event_ids,
            {"evt-primary", "evt-from-notification", "evt-by-property", "evt-legacy"},
        )

        first_lookup_kwargs = mock_client.list_events.call_args_list[0].kwargs
        self.assertEqual(
            first_lookup_kwargs["private_extended_property"],
            f"revisbali_customer_application_id={application_id}",
        )
