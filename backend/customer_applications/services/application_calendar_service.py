import logging
from datetime import datetime, time, timedelta
from typing import Iterable

from core.utils.google_client import GoogleClient
from core.services.google_calendar_event_colors import GoogleCalendarEventColors
from customer_applications.models import WorkflowNotification
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class ApplicationCalendarService:
    PRIVATE_PROP_ENTITY_KEY = "revisbali_entity"
    PRIVATE_PROP_APPLICATION_ID_KEY = "revisbali_customer_application_id"
    PRIVATE_PROP_ENTITY_VALUE = "customer_application"

    def sync_next_task_deadline(self, application, start_date=None, previous_due_date=None):
        if not application.add_deadlines_to_calendar:
            self.delete_application_events(application, clear_application_reference=True)
            return None

        task = application.get_next_calendar_task()
        if not task:
            self.delete_application_events(application, clear_application_reference=True)
            return None

        # Determine the target due date
        if start_date:
            due_date = application.calculate_next_calendar_due_date(start_date=start_date)
        else:
            # If already set on application, respect it (manual change)
            # otherwise calculate it based on doc_date
            due_date = application.due_date or application.calculate_next_calendar_due_date(
                start_date=application.doc_date
            )

        event_id = self._resolve_primary_event_id(application)
        if event_id and event_id != application.calendar_event_id:
            application.calendar_event_id = event_id
            application.save(update_fields=["calendar_event_id", "updated_at"])

        if previous_due_date is not None and previous_due_date == due_date and event_id:
            # Due date didn't change; no calendar update needed.
            return None

        self.delete_application_events(application, clear_application_reference=False)

        # Update application due date
        if application.due_date != due_date:
            application.due_date = due_date
            application.save(update_fields=["due_date", "updated_at"])

        event = None
        event_payload = self._build_calendar_event_payload(application, task, due_date)
        try:
            event = self._create_calendar_event(event_payload)
        except Exception as exc:
            logger.error(
                "Calendar event create/update failed for application #%s: error_type=%s error=%s payload=%s",
                application.id,
                type(exc).__name__,
                str(exc),
                event_payload,
            )
            event = None

        if event and event.get("id"):
            application.calendar_event_id = event.get("id")
            application.save(update_fields=["calendar_event_id", "updated_at"])
        elif application.calendar_event_id:
            application.calendar_event_id = None
            application.save(update_fields=["calendar_event_id", "updated_at"])

        return event

    def delete_application_events(self, application, clear_application_reference=True):
        known_event_ids = self._known_event_ids_from_application(application)
        deleted_count = self.delete_events_for_application_id(
            application_id=application.id,
            known_event_ids=known_event_ids,
        )

        if clear_application_reference and application.calendar_event_id:
            application.calendar_event_id = None
            application.save(update_fields=["calendar_event_id", "updated_at"])

        return deleted_count

    def delete_events_for_application_id(self, application_id: int, known_event_ids: Iterable[str] | None = None):
        calendar_id = getattr(settings, "GOOGLE_CALENDAR_ID", "primary")
        try:
            client = GoogleClient()
        except Exception as e:
            logger.warning(f"Failed to initialize Google client for application #{application_id}: {e}")
            return 0

        event_ids = set(filter(None, known_event_ids or []))
        event_ids.update(self._lookup_event_ids_for_application_id(client=client, application_id=application_id))

        deleted_count = 0
        for event_id in event_ids:
            try:
                client.delete_event(event_id, calendar_id=calendar_id)
                deleted_count += 1
            except Exception as e:
                logger.warning(f"Failed to delete calendar event {event_id}: {e}")

        return deleted_count

    def _known_event_ids_from_application(self, application):
        event_ids = set()
        if application.calendar_event_id:
            event_ids.add(application.calendar_event_id)

        notification_refs = (
            WorkflowNotification.objects.filter(
                doc_application=application,
                notification_type="",
                external_reference__isnull=False,
            )
            .exclude(external_reference="")
            .values_list("external_reference", flat=True)
        )
        event_ids.update(notification_refs)
        return event_ids

    def _lookup_event_ids_for_application_id(self, client, application_id: int):
        calendar_id = getattr(settings, "GOOGLE_CALENDAR_ID", "primary")
        event_ids = set()

        try:
            events = client.list_events(
                calendar_id=calendar_id,
                max_results=250,
                include_past=True,
                fetch_all=True,
                private_extended_property=f"{self.PRIVATE_PROP_APPLICATION_ID_KEY}={application_id}",
            )
            for event in events:
                event_id = event.get("id")
                if event_id:
                    event_ids.add(event_id)
        except Exception as e:
            logger.warning(f"Failed to lookup pinned calendar events for application #{application_id}: {e}")

        try:
            summary_prefix = f"[Application #{application_id}]"
            legacy_events = client.list_events(
                calendar_id=calendar_id,
                max_results=250,
                include_past=True,
                fetch_all=True,
                query=summary_prefix,
            )
            for event in legacy_events:
                summary = event.get("summary") or ""
                event_id = event.get("id")
                if event_id and summary.startswith(summary_prefix):
                    event_ids.add(event_id)
        except Exception as e:
            logger.warning(f"Failed to lookup legacy calendar events for application #{application_id}: {e}")

        return event_ids

    def _get_application_event_ids(self, application, client):
        event_ids = set(self._known_event_ids_from_application(application))
        event_ids.update(self._lookup_event_ids_for_application_id(client=client, application_id=application.id))
        return {event_id for event_id in event_ids if event_id}

    def _resolve_primary_event_id(self, application):
        if application.calendar_event_id:
            return application.calendar_event_id

        last_notification = (
            WorkflowNotification.objects.filter(
                doc_application=application,
                notification_type="",
                external_reference__isnull=False,
            )
            .exclude(external_reference="")
            .order_by("-id")
            .first()
        )
        if last_notification and last_notification.external_reference:
            return last_notification.external_reference

        try:
            client = GoogleClient()
            events = client.list_events(
                calendar_id=getattr(settings, "GOOGLE_CALENDAR_ID", "primary"),
                max_results=1,
                include_past=True,
                private_extended_property=self._private_extended_property_filter(application),
            )
            if events:
                return events[0].get("id")
        except Exception as e:
            logger.warning(f"Failed to resolve existing calendar event for application #{application.id}: {e}")

        return None

    def _build_calendar_event_payload(self, application, task, due_date):
        notify_days = task.notify_days_before or 0
        reminder_minutes = max(0, notify_days * 24 * 60)

        notes = application.notes or "-"
        description = (
            f"Application #{application.id}\n"
            f"Customer: {application.customer.full_name}\n"
            f"Product: {application.product.name}\n"
            f"Task: {task.name}\n"
            f"Application Notes: {notes}"
        )

        return {
            "summary": f"[Application #{application.id}] {application.customer.full_name} - {task.name}",
            "description": description,
            "start_date": due_date.isoformat(),
            "end_date": (due_date + timedelta(days=1)).isoformat(),
            "color_id": GoogleCalendarEventColors.todo_color_id(),
            "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": reminder_minutes}]},
            "extended_properties": {"private": self._private_properties(application)},
        }

    def _create_calendar_event(self, payload):
        client = GoogleClient()
        return client.create_event(payload, calendar_id=getattr(settings, "GOOGLE_CALENDAR_ID", "primary"))

    def _private_properties(self, application):
        return {
            self.PRIVATE_PROP_ENTITY_KEY: self.PRIVATE_PROP_ENTITY_VALUE,
            self.PRIVATE_PROP_APPLICATION_ID_KEY: str(application.id),
        }

    def _private_extended_property_filter(self, application):
        return f"{self.PRIVATE_PROP_APPLICATION_ID_KEY}={application.id}"

    def _summary_prefix(self, application):
        return f"[Application #{application.id}]"

    def _create_notification(self, application, task, due_date, event, workflow=None):
        notify_days = task.notify_days_before or 0
        scheduled_date = due_date - timedelta(days=notify_days)
        scheduled_for = timezone.make_aware(datetime.combine(scheduled_date, time.min))

        if not application.notify_customer_too:
            return None

        channel = application.notify_customer_channel or application.NOTIFY_CHANNEL_EMAIL
        if channel == application.NOTIFY_CHANNEL_WHATSAPP:
            recipient = application.customer.whatsapp
        else:
            recipient = application.customer.email

        if not recipient:
            return None

        subject = f"Upcoming deadline: {task.name}"
        body = (
            f"Dear {application.customer.full_name},\n\n"
            f"Your next step for application #{application.id} is '{task.name}'.\n"
            f"Due date: {due_date}\n"
            f"Reminder date: {scheduled_for}\n\n"
            f"Notes: {application.notes or '-'}"
        )

        notification = WorkflowNotification.objects.create(
            channel=channel,
            recipient=recipient,
            subject=subject,
            body=body,
            doc_application=application,
            doc_workflow=workflow,
            status=WorkflowNotification.STATUS_PENDING,
            scheduled_for=scheduled_for,
            external_reference=(event or {}).get("id", ""),
        )
        return notification
