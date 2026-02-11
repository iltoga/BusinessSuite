import logging
from datetime import datetime, time, timedelta

from core.utils.google_client import GoogleClient
from customer_applications.models import WorkflowNotification
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class ApplicationCalendarService:
    def sync_next_task_deadline(self, application, start_date=None, previous_due_date=None):
        if not application.add_deadlines_to_calendar:
            # If it was turned off, try to delete the last event if it exists
            event_id = application.calendar_event_id
            if not event_id:
                last_notification = (
                    WorkflowNotification.objects.filter(doc_application=application, external_reference__isnull=False)
                    .exclude(external_reference="")
                    .order_by("-id")
                    .first()
                )
                event_id = last_notification.external_reference if last_notification else None
            if event_id:
                try:
                    client = GoogleClient()
                    client.delete_event(event_id, calendar_id=getattr(settings, "GOOGLE_CALENDAR_ID", "primary"))
                except Exception:
                    pass
            else:
                self._delete_events_by_application(application)
            if application.calendar_event_id:
                application.calendar_event_id = None
                application.save(update_fields=["calendar_event_id", "updated_at"])
            return None

        task = application.get_next_calendar_task()
        if not task:
            return None

        # Find the workflow instance for this task if it exists
        workflow = application.workflows.filter(task=task).first()

        # Determine the target due date
        if start_date:
            due_date = application.calculate_next_calendar_due_date(start_date=start_date)
        else:
            # If already set on application, respect it (manual change)
            # otherwise calculate it based on doc_date
            due_date = application.due_date or application.calculate_next_calendar_due_date(
                start_date=application.doc_date
            )

        event_id = application.calendar_event_id
        if not event_id:
            last_notification = (
                WorkflowNotification.objects.filter(doc_application=application, external_reference__isnull=False)
                .exclude(external_reference="")
                .order_by("-id")
                .first()
            )
            event_id = last_notification.external_reference if last_notification else None
            if event_id and not application.calendar_event_id:
                application.calendar_event_id = event_id
                application.save(update_fields=["calendar_event_id", "updated_at"])

        if previous_due_date is not None and previous_due_date == due_date and event_id:
            # Due date didn't change; no calendar update needed.
            return None

        if event_id:
            try:
                client = GoogleClient()
                client.delete_event(event_id, calendar_id=getattr(settings, "GOOGLE_CALENDAR_ID", "primary"))
            except Exception as e:
                logger.warning(f"Failed to delete old calendar event {event_id}: {e}")
        elif previous_due_date is None or previous_due_date != due_date:
            self._delete_events_by_application(application)

        # Update application due date
        application.due_date = due_date
        application.save(update_fields=["due_date", "updated_at"])

        event = None
        try:
            event = self._create_calendar_event(application, task, due_date)
        except Exception:
            event = None

        if event and event.get("id"):
            application.calendar_event_id = event.get("id")
            application.save(update_fields=["calendar_event_id", "updated_at"])
        elif application.calendar_event_id:
            application.calendar_event_id = None
            application.save(update_fields=["calendar_event_id", "updated_at"])

        self._create_notification(application, task, due_date, event, workflow=workflow)
        return event

    def _delete_events_by_application(self, application):
        try:
            client = GoogleClient()
            summary_prefix = f"[Application #{application.id}]"
            events = client.list_events(calendar_id=getattr(settings, "GOOGLE_CALENDAR_ID", "primary"), max_results=250)
            for event in events:
                summary = event.get("summary") or ""
                if summary.startswith(summary_prefix):
                    try:
                        client.delete_event(
                            event.get("id"), calendar_id=getattr(settings, "GOOGLE_CALENDAR_ID", "primary")
                        )
                    except Exception:
                        continue
        except Exception as e:
            logger.warning(f"Failed to cleanup calendar events for application #{application.id}: {e}")

    def _create_calendar_event(self, application, task, due_date):
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

        payload = {
            "summary": f"[Application #{application.id}] {application.customer.full_name} - {task.name}",
            "description": description,
            "start_date": due_date.isoformat(),
            "end_date": (due_date + timedelta(days=1)).isoformat(),
            "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": reminder_minutes}]},
        }
        client = GoogleClient()
        return client.create_event(payload, calendar_id=getattr(settings, "GOOGLE_CALENDAR_ID", "primary"))

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
