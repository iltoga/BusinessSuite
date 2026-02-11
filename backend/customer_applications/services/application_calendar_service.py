from datetime import datetime, time

from django.conf import settings
from django.utils import timezone

from core.utils.google_client import GoogleClient
from customer_applications.models import WorkflowNotification
from notifications.services.providers import NotificationDispatcher


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
            "all_day": True,
            "start_time": due_date,
            "end_time": due_date,
            "reminders": {
                "useDefault": False,
                "overrides": [{"method": "email", "minutes": reminder_minutes}],
            },
        }
        client = GoogleClient()
        return client.create_event(payload, calendar_id=getattr(settings, "GOOGLE_CALENDAR_ID", "primary"))

    def _get_notify_at(self, due_date, notify_days_before: int):
        notify_date = due_date - timezone.timedelta(days=notify_days_before or 0)
        return timezone.make_aware(datetime.combine(notify_date, time(hour=9, minute=0)))

    def _create_notification(self, application, task, due_date, event):
        if not application.notify_customer_too:
            return None

        channel = application.notification_channel or ""
        recipient = (
            application.customer.whatsapp
            if channel == "whatsapp"
            else application.customer.email or getattr(settings, "DEFAULT_CUSTOMER_EMAIL", "sample_email@gmail.com")
        )
        if not recipient:
            return None

        subject = f"Upcoming deadline: {task.name}"
        body = (
            f"Dear {application.customer.full_name},\n\n"
            f"Your next step for application #{application.id} is '{task.name}'.\n"
            f"Due date: {due_date}\n\n"
            f"Notes: {application.notes or '-'}"
        )

        notify_at = self._get_notify_at(due_date, task.notify_days_before or 0)

        notification = WorkflowNotification.objects.create(
            channel=channel,
            recipient=recipient,
            subject=subject,
            body=body,
            doc_application=application,
            status=WorkflowNotification.STATUS_PENDING,
            scheduled_for=due_date,
            notify_at=notify_at,
            external_reference=(event or {}).get("id", ""),
        )

        if notify_at <= timezone.now():
            self.send_notification(notification)
        return notification

    def send_notification(self, notification: WorkflowNotification):
        try:
            message = NotificationDispatcher().send(
                notification.channel,
                notification.recipient,
                notification.subject,
                notification.body,
            )
            notification.status = WorkflowNotification.STATUS_SENT
            notification.provider_message = message
            notification.sent_at = timezone.now()
        except Exception as exc:
            notification.status = WorkflowNotification.STATUS_FAILED
            notification.provider_message = str(exc)

        notification.save(update_fields=["status", "provider_message", "sent_at", "updated_at"])
        return notification

    def dispatch_pending_notifications(self):
        pending = WorkflowNotification.objects.filter(
            status=WorkflowNotification.STATUS_PENDING,
            notify_at__isnull=False,
            notify_at__lte=timezone.now(),
        )
        for notification in pending:
            self.send_notification(notification)
        return pending.count()
