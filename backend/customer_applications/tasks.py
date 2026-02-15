import logging
from datetime import datetime, time, timedelta

from customer_applications.models import DocApplication
from django.contrib.auth import get_user_model
from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone
from huey import crontab
from huey.contrib.djhuey import db_periodic_task, db_task

User = get_user_model()
logger = logging.getLogger(__name__)

SYNC_ACTION_UPSERT = "upsert"
SYNC_ACTION_DELETE = "delete"


def _build_manual_calendar_copy(application):
    task = application.get_next_calendar_task()
    due_date = application.due_date or application.calculate_next_calendar_due_date(start_date=application.doc_date)
    task_name = task.name if task else "Follow-up"
    reminder_days_before = task.notify_days_before if task else 0

    summary = f"[Application #{application.id}] {application.customer.full_name} - {task_name}"
    description = (
        f"Application #{application.id}\n"
        f"Customer: {application.customer.full_name}\n"
        f"Product: {application.product.name}\n"
        f"Task: {task_name}\n"
        f"Application Notes: {application.notes or '-'}"
    )
    copy_text = (
        f"Summary: {summary}\n"
        f"Due date: {due_date}\n"
        f"Reminder days before: {reminder_days_before}\n"
        f"Description:\n{description}"
    )
    return {
        "applicationId": application.id,
        "summary": summary,
        "dueDate": due_date.isoformat() if hasattr(due_date, "isoformat") else str(due_date),
        "reminderDaysBefore": reminder_days_before,
        "description": description,
        "copyText": copy_text,
    }


def _notify_calendar_sync_failure(user, *, application, action, error_message):
    if not user:
        return

    try:
        from core.services.push_notifications import PushNotificationService

        manual_copy = _build_manual_calendar_copy(application)
        PushNotificationService().send_to_user(
            user=user,
            title="Calendar Sync Failed",
            body=f"Application #{application.id}: {error_message}",
            data={
                "type": "calendar_sync_failed",
                "action": action,
                "applicationId": application.id,
                "error": error_message,
                "calendarTaskCopy": manual_copy,
            },
            link=f"/applications/{application.id}",
        )
    except Exception:
        logger.exception("Failed to push calendar sync error notification to user #%s", getattr(user, "id", None))


@db_task()
def sync_application_calendar_task(
    *,
    application_id: int,
    user_id: int | None = None,
    action: str = SYNC_ACTION_UPSERT,
    previous_due_date: str | None = None,
    start_date: str | None = None,
    known_event_ids: list[str] | None = None,
):
    from customer_applications.services.application_calendar_service import ApplicationCalendarService

    application = (
        DocApplication.objects.select_related("customer", "product")
        .prefetch_related("product__tasks", "workflows__task")
        .filter(pk=application_id)
        .first()
    )

    user = User.objects.filter(pk=user_id).first() if user_id else None
    if not application and action != SYNC_ACTION_DELETE:
        logger.info("Skipping calendar sync: application #%s no longer exists", application_id)
        return {"status": "skipped", "reason": "application_missing"}

    if action == SYNC_ACTION_DELETE:
        try:
            deleted = ApplicationCalendarService().delete_events_for_application_id(
                application_id=application_id,
                known_event_ids=known_event_ids or [],
            )
            return {"status": "ok", "deleted": deleted}
        except Exception as exc:
            logger.exception("Calendar cleanup failed for application #%s", application_id)
            return {"status": "failed", "error": str(exc)}

    parsed_previous_due_date = None
    parsed_start_date = None
    if previous_due_date:
        parsed_previous_due_date = datetime.fromisoformat(previous_due_date).date()
    if start_date:
        parsed_start_date = datetime.fromisoformat(start_date).date()

    calendar_error = None
    try:
        ApplicationCalendarService().sync_next_task_deadline(
            application,
            start_date=parsed_start_date,
            previous_due_date=parsed_previous_due_date,
        )
    except Exception as exc:
        logger.exception("Calendar sync failed for application #%s", application_id)
        calendar_error = exc
        if application and user:
            _notify_calendar_sync_failure(
                user,
                application=application,
                action=action,
                error_message=str(exc),
            )

    notification_result = send_due_tomorrow_customer_notifications(
        application_ids=[application.id],
        immediate=True,
    )

    if calendar_error is not None:
        return {"status": "failed", "error": str(calendar_error), "notifications": notification_result}
    return {"status": "ok", "notifications": notification_result}


def _send_due_tomorrow_notification_for_application(
    *,
    application,
    dispatcher,
    scheduled_for,
):
    from customer_applications.models import WorkflowNotification
    from notifications.services.customer_deadline_messages import (
        build_customer_deadline_notification_payload,
    )
    from notifications.services.providers import is_queued_provider_result

    task = application.get_next_calendar_task()
    if not task or not task.notify_customer:
        return "skipped"

    channel = application.notify_customer_channel or application.NOTIFY_CHANNEL_EMAIL
    recipient = (
        application.customer.whatsapp if channel == application.NOTIFY_CHANNEL_WHATSAPP else application.customer.email
    )
    if not recipient:
        return "skipped"

    payload = build_customer_deadline_notification_payload(application, task, application.due_date)
    subject = payload["subject"]
    body = payload["email_text"] if channel == application.NOTIFY_CHANNEL_EMAIL else payload["whatsapp_text"]
    html_body = payload["email_html"] if channel == application.NOTIFY_CHANNEL_EMAIL else None

    try:
        notification, created = WorkflowNotification.objects.get_or_create(
            doc_application=application,
            channel=channel,
            notification_type=WorkflowNotification.TYPE_DUE_TOMORROW,
            target_date=application.due_date,
            defaults={
                "recipient": recipient,
                "subject": subject,
                "body": body,
                "doc_workflow": None,
                "status": WorkflowNotification.STATUS_PENDING,
                "scheduled_for": scheduled_for,
            },
        )
    except IntegrityError:
        return "skipped"

    if not created:
        # Keep stored payload aligned with latest application data for manual retries.
        update_fields = []
        if notification.recipient != recipient:
            notification.recipient = recipient
            update_fields.append("recipient")
        if notification.subject != subject:
            notification.subject = subject
            update_fields.append("subject")
        if notification.body != body:
            notification.body = body
            update_fields.append("body")
        if update_fields:
            notification.save(update_fields=[*update_fields, "updated_at"])
        return "skipped"

    try:
        message = dispatcher.send(
            channel=channel,
            recipient=recipient,
            subject=subject,
            body=body,
            html_body=html_body,
        )
        notification.provider_message = str(message)
        if is_queued_provider_result(channel, message):
            # Provider accepted queueing placeholder but did not send to recipient yet.
            notification.status = WorkflowNotification.STATUS_PENDING
            notification.external_reference = ""
            notification.sent_at = None
            result = "pending"
        else:
            notification.status = WorkflowNotification.STATUS_SENT
            notification.external_reference = str(message) if channel == application.NOTIFY_CHANNEL_WHATSAPP else ""
            notification.sent_at = timezone.now()
            result = "sent"
    except Exception as exc:
        logger.error(
            "Failed to deliver due-tomorrow customer notification: application_id=%s channel=%s recipient=%s "
            "target_date=%s error_type=%s error=%s",
            application.id,
            channel,
            recipient,
            application.due_date.isoformat() if application.due_date else None,
            type(exc).__name__,
            str(exc),
        )
        notification.status = WorkflowNotification.STATUS_FAILED
        notification.provider_message = str(exc)
        notification.external_reference = ""
        notification.sent_at = None
        result = "failed"

    notification.save(
        update_fields=[
            "status",
            "provider_message",
            "external_reference",
            "sent_at",
            "updated_at",
        ]
    )
    return result


def send_due_tomorrow_customer_notifications(now=None, application_ids=None, immediate=False):
    """Send customer reminders for applications whose deadline is tomorrow.

    Conditions:
    - application.notify_customer_too == True
    - due_date is tomorrow
    - next calendar task exists and task.notify_customer == True
    - recipient exists for selected channel
    """
    from notifications.services.providers import NotificationDispatcher

    current_time = timezone.now() if now is None else now
    today = timezone.localtime(current_time).date()
    tomorrow = today + timedelta(days=1)

    applications = (
        DocApplication.objects.select_related("customer", "product")
        .prefetch_related("product__tasks", "workflows__task")
        .filter(
            due_date=tomorrow,
            notify_customer_too=True,
            status__in=[DocApplication.STATUS_PENDING, DocApplication.STATUS_PROCESSING],
        )
    )
    if application_ids is not None:
        applications = applications.filter(id__in=list(application_ids))

    dispatcher = NotificationDispatcher()
    sent_count = 0
    failed_count = 0
    pending_count = 0
    skipped_count = 0
    scheduled_for = (
        current_time
        if immediate
        else timezone.make_aware(
            datetime.combine(
                today,
                time(
                    hour=getattr(settings, "CUSTOMER_NOTIFICATIONS_DAILY_HOUR", 8),
                    minute=getattr(settings, "CUSTOMER_NOTIFICATIONS_DAILY_MINUTE", 0),
                ),
            )
        )
    )

    for application in applications:
        result = _send_due_tomorrow_notification_for_application(
            application=application,
            dispatcher=dispatcher,
            scheduled_for=scheduled_for,
        )
        if result == "sent":
            sent_count += 1
        elif result == "failed":
            failed_count += 1
        elif result == "pending":
            pending_count += 1
        else:
            skipped_count += 1

    logger.info(
        "Due-tomorrow notification job completed: sent=%s pending=%s failed=%s skipped=%s target_date=%s",
        sent_count,
        pending_count,
        failed_count,
        skipped_count,
        tomorrow.isoformat(),
    )
    return {"sent": sent_count, "pending": pending_count, "failed": failed_count, "skipped": skipped_count}


@db_periodic_task(
    crontab(
        hour=getattr(settings, "CUSTOMER_NOTIFICATIONS_DAILY_HOUR", 8),
        minute=getattr(settings, "CUSTOMER_NOTIFICATIONS_DAILY_MINUTE", 0),
    ),
    name="customer_applications.send_due_tomorrow_customer_notifications",
)
def send_due_tomorrow_customer_notifications_task():
    return send_due_tomorrow_customer_notifications()
