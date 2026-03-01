from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from core.models.calendar_event import CalendarEvent
from core.services.google_calendar_event_colors import GoogleCalendarEventColors
from customer_applications.models import DocApplication, Document, WorkflowNotification
from customer_applications.services.application_calendar_service import ApplicationCalendarService
from customers.models import Customer
from products.models import DocumentType, Product, Task

User = get_user_model()

TEST_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "application-calendar-service-default-cache",
    },
    "select2": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "application-calendar-service-select2-cache",
    },
}


@override_settings(CACHES=TEST_CACHES)
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
        with patch("core.signals_calendar.enqueue_create_google_event_task") as create_sync_mock:
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
            patch("core.signals_calendar.enqueue_create_google_event_task") as create_sync_mock,
            patch("core.signals_calendar.enqueue_update_google_event_task") as update_sync_mock,
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
        with patch("core.signals_calendar.enqueue_create_google_event_task"):
            with self.captureOnCommitCallbacks(execute=True):
                old_event = ApplicationCalendarService().sync_next_task_deadline(self.application)

        self.task.add_task_to_calendar = False
        self.task.save(update_fields=["add_task_to_calendar"])

        result = ApplicationCalendarService().sync_next_task_deadline(self.application)

        self.assertIsNone(result)
        self.assertTrue(CalendarEvent.objects.filter(pk=old_event.id).exists())
        self.application.refresh_from_db()
        self.assertIsNone(self.application.calendar_event_id)

    @patch("customer_applications.tasks.enqueue_sync_application_calendar_task")
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


@override_settings(CACHES=TEST_CACHES)
class VisaSubmissionWindowCalendarServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("visa-window-user", "visawindow@example.com", "pass")
        self.customer = Customer.objects.create(first_name="Visa", last_name="Window")
        self.stay_permit_doc_type = DocumentType.objects.create(
            name="ITK Calendar",
            has_expiration_date=True,
            is_stay_permit=True,
            has_file=True,
        )
        self.product = Product.objects.create(
            name="Visa Product",
            code="VISA-WINDOW",
            product_type="visa",
            required_documents="ITK Calendar",
            application_window_days=14,
        )
        self.task = Task.objects.create(
            product=self.product,
            step=1,
            name="Submit",
            duration=3,
            duration_is_business_days=False,
            notify_days_before=1,
            add_task_to_calendar=True,
        )
        self.application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=date(2026, 1, 10),
            due_date=date(2026, 1, 15),
            add_deadlines_to_calendar=True,
            created_by=self.user,
        )
        Document.objects.create(
            doc_application=self.application,
            doc_type=self.stay_permit_doc_type,
            expiration_date=date(2026, 2, 20),
            required=True,
            created_by=self.user,
        )

    def _visa_window_event(self):
        return CalendarEvent.objects.filter(
            application=self.application,
            source=CalendarEvent.SOURCE_APPLICATION,
            extended_properties__private__revisbali_event_kind="visa_submission_window",
        ).first()

    def test_sync_creates_visa_submission_window_event(self):
        with patch("core.signals_calendar.enqueue_create_google_event_task"):
            with self.captureOnCommitCallbacks(execute=True):
                ApplicationCalendarService().sync_next_task_deadline(self.application)

        visa_event = self._visa_window_event()
        self.assertIsNotNone(visa_event)
        self.assertEqual(visa_event.start_date.isoformat(), "2026-02-06")
        self.assertEqual(visa_event.end_date.isoformat(), "2026-02-21")
        self.assertEqual(visa_event.color_id, GoogleCalendarEventColors.visa_window_color_id())
        self.assertEqual(visa_event.notifications, {})

    def test_sync_updates_existing_visa_submission_window_event(self):
        with patch("core.signals_calendar.enqueue_create_google_event_task"), patch(
            "core.signals_calendar.enqueue_update_google_event_task"
        ):
            with self.captureOnCommitCallbacks(execute=True):
                ApplicationCalendarService().sync_next_task_deadline(self.application)

            original_event = self._visa_window_event()
            self.assertIsNotNone(original_event)

            document = Document.objects.get(doc_application=self.application, doc_type=self.stay_permit_doc_type)
            document.expiration_date = date(2026, 2, 10)
            document.save(update_fields=["expiration_date", "updated_at"])

            with self.captureOnCommitCallbacks(execute=True):
                ApplicationCalendarService().sync_next_task_deadline(self.application)

        updated_event = self._visa_window_event()
        self.assertIsNotNone(updated_event)
        self.assertEqual(updated_event.id, original_event.id)
        self.assertEqual(updated_event.start_date.isoformat(), "2026-01-27")
        self.assertEqual(updated_event.end_date.isoformat(), "2026-02-11")

    def test_sync_removes_visa_submission_window_event_when_calendar_disabled(self):
        with patch("core.signals_calendar.enqueue_create_google_event_task"):
            with self.captureOnCommitCallbacks(execute=True):
                ApplicationCalendarService().sync_next_task_deadline(self.application)

        self.assertIsNotNone(self._visa_window_event())

        self.application.add_deadlines_to_calendar = False
        self.application.save(update_fields=["add_deadlines_to_calendar", "updated_at"])
        ApplicationCalendarService().sync_next_task_deadline(self.application)

        self.assertIsNone(self._visa_window_event())

    def test_sync_logs_and_continues_when_visa_window_subsync_fails(self):
        with (
            patch("core.signals_calendar.enqueue_create_google_event_task"),
            patch(
                "customer_applications.services.application_calendar_service.ApplicationCalendarService._get_visa_submission_window_event",
                side_effect=RuntimeError("boom"),
            ),
        ):
            with self.assertLogs("customer_applications.services.application_calendar_service", level="ERROR"):
                with self.captureOnCommitCallbacks(execute=True):
                    event = ApplicationCalendarService().sync_next_task_deadline(self.application)

        self.assertIsNotNone(event)
        self.assertEqual(event.source, CalendarEvent.SOURCE_APPLICATION)


@override_settings(CACHES=TEST_CACHES)
class VisaSubmissionWindowDocumentSignalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("visa-window-doc-user", "visawindowdoc@example.com", "pass")
        self.customer = Customer.objects.create(first_name="Signal", last_name="Tester")
        self.stay_permit_doc_type = DocumentType.objects.create(
            name="ITK Signal",
            has_expiration_date=True,
            is_stay_permit=True,
            has_file=True,
        )
        self.regular_doc_type = DocumentType.objects.create(
            name="Passport Signal",
            has_expiration_date=True,
            has_file=True,
        )
        self.visa_product = Product.objects.create(
            name="Visa Product Signal",
            code="VISA-SIGNAL",
            product_type="visa",
            required_documents="ITK Signal,Passport Signal",
        )
        self.other_product = Product.objects.create(
            name="Other Product Signal",
            code="OTHER-SIGNAL",
            product_type="other",
            required_documents="ITK Signal",
        )
        self.visa_application = DocApplication.objects.create(
            customer=self.customer,
            product=self.visa_product,
            doc_date=date(2026, 1, 10),
            created_by=self.user,
        )
        self.other_application = DocApplication.objects.create(
            customer=self.customer,
            product=self.other_product,
            doc_date=date(2026, 1, 10),
            created_by=self.user,
        )

    @patch("customer_applications.tasks.enqueue_sync_application_calendar_task")
    def test_stay_permit_save_queues_calendar_sync(self, sync_task_mock):
        with self.captureOnCommitCallbacks(execute=True):
            Document.objects.create(
                doc_application=self.visa_application,
                doc_type=self.stay_permit_doc_type,
                expiration_date=date(2026, 2, 20),
                required=True,
                created_by=self.user,
            )

        sync_task_mock.assert_called_once()
        kwargs = sync_task_mock.call_args.kwargs
        self.assertEqual(kwargs["application_id"], self.visa_application.id)
        self.assertEqual(kwargs["user_id"], self.user.id)
        self.assertEqual(kwargs["action"], "upsert")

    @patch("customer_applications.tasks.enqueue_sync_application_calendar_task")
    def test_stay_permit_expiration_update_queues_calendar_sync(self, sync_task_mock):
        with self.captureOnCommitCallbacks(execute=True):
            document = Document.objects.create(
                doc_application=self.visa_application,
                doc_type=self.stay_permit_doc_type,
                expiration_date=date(2026, 2, 20),
                required=True,
                created_by=self.user,
            )

        sync_task_mock.reset_mock()

        document.expiration_date = date(2026, 2, 15)
        with self.captureOnCommitCallbacks(execute=True):
            document.save(update_fields=["expiration_date", "updated_at"])

        sync_task_mock.assert_called_once()
        kwargs = sync_task_mock.call_args.kwargs
        self.assertEqual(kwargs["application_id"], self.visa_application.id)
        self.assertEqual(kwargs["action"], "upsert")

    @patch("customer_applications.tasks.enqueue_sync_application_calendar_task")
    def test_stay_permit_delete_queues_calendar_sync(self, sync_task_mock):
        with self.captureOnCommitCallbacks(execute=True):
            document = Document.objects.create(
                doc_application=self.visa_application,
                doc_type=self.stay_permit_doc_type,
                expiration_date=date(2026, 2, 20),
                required=True,
                created_by=self.user,
            )

        sync_task_mock.reset_mock()

        with self.captureOnCommitCallbacks(execute=True):
            document.delete()

        sync_task_mock.assert_called_once()
        kwargs = sync_task_mock.call_args.kwargs
        self.assertEqual(kwargs["application_id"], self.visa_application.id)
        self.assertEqual(kwargs["action"], "upsert")

    @patch("customer_applications.tasks.enqueue_sync_application_calendar_task")
    def test_non_qualifying_documents_do_not_queue_calendar_sync(self, sync_task_mock):
        with self.captureOnCommitCallbacks(execute=True):
            Document.objects.create(
                doc_application=self.visa_application,
                doc_type=self.regular_doc_type,
                expiration_date=date(2030, 1, 1),
                required=True,
                created_by=self.user,
            )
            Document.objects.create(
                doc_application=self.other_application,
                doc_type=self.stay_permit_doc_type,
                expiration_date=date(2026, 2, 20),
                required=True,
                created_by=self.user,
            )

        sync_task_mock.assert_not_called()
