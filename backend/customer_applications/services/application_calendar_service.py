from datetime import datetime, time, timedelta

from django.conf import settings
from django.utils import timezone

from core.utils.google_client import GoogleClient
from customer_applications.models import WorkflowNotification


class ApplicationCalendarService:
    def sync_next_task_deadline(self, application, start_date=None):
        if not application.add_deadlines_to_calendar:
            return None

        task = application.get_next_calendar_task()
        if not task:
            return None

        due_date = application.calculate_next_calendar_due_date(start_date=start_date or application.doc_date)
        application.due_date = due_date
        application.save(update_fields=["due_date", "updated_at"])

        event = None
        try:
            event = self._create_calendar_event(application, task, due_date)
        except Exception:
            event = None

        self._create_notification(application, task, due_date, event)
        return event

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

    def _create_notification(self, application, task, due_date, event):
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
            status=WorkflowNotification.STATUS_PENDING,
            scheduled_for=scheduled_for,
            external_reference=(event or {}).get("id", ""),
        )
        return notification
