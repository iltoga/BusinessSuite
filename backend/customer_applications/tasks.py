import logging
import os
import posixpath
from datetime import datetime, time, timedelta

from customer_applications.models import DocApplication
from core.queue import enqueue_job
from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.files.storage import FileSystemStorage, default_storage
from django.db import IntegrityError, transaction
from django.utils import timezone

User = get_user_model()
logger = logging.getLogger(__name__)

SYNC_ACTION_UPSERT = "upsert"
SYNC_ACTION_DELETE = "delete"
WHATSAPP_POLL_UNSUPPORTED_MARKER = "Meta poll unsupported: waiting for webhook status updates."
ENTRYPOINT_CLEANUP_DOCUMENT_STORAGE_TASK = "customer_applications.cleanup_document_storage"
ENTRYPOINT_CLEANUP_APPLICATION_STORAGE_FOLDER_TASK = "customer_applications.cleanup_application_storage_folder"
ENTRYPOINT_SYNC_APPLICATION_CALENDAR_TASK = "customer_applications.sync_application_calendar"
ENTRYPOINT_POLL_WHATSAPP_DELIVERY_STATUSES_TASK = "customer_applications.poll_whatsapp_delivery_statuses"
ENTRYPOINT_SEND_DUE_TOMORROW_CUSTOMER_NOTIFICATIONS_TASK = (
    "customer_applications.send_due_tomorrow_customer_notifications"
)


def _normalize_storage_prefix(path: str | None) -> str:
    return str(path or "").strip().strip("/")


def _delete_storage_file_if_exists(file_path: str) -> None:
    try:
        if default_storage.exists(file_path):
            default_storage.delete(file_path)
    except Exception as exc:
        logger.error(
            "Failed deleting storage object '%s': error_type=%s error=%s",
            file_path,
            type(exc).__name__,
            str(exc),
        )


def _delete_empty_storage_folder(folder_path: str | None) -> None:
    folder = _normalize_storage_prefix(folder_path)
    if not folder:
        return

    try:
        directories, files = default_storage.listdir(folder)
    except FileNotFoundError:
        return
    except Exception as exc:
        logger.error(
            "Failed listing folder '%s' while checking emptiness: error_type=%s error=%s",
            folder,
            type(exc).__name__,
            str(exc),
        )
        return

    if directories or files:
        return

    # S3-style storages can use directory marker objects; deleting is best-effort.
    folder_marker = f"{folder}/"
    try:
        if default_storage.exists(folder_marker):
            default_storage.delete(folder_marker)
    except Exception as exc:
        logger.error(
            "Failed deleting folder marker '%s': error_type=%s error=%s",
            folder_marker,
            type(exc).__name__,
            str(exc),
        )

    # Local storage may still have an empty physical directory to remove.
    try:
        if isinstance(default_storage, FileSystemStorage):
            local_folder = default_storage.path(folder)
            if os.path.isdir(local_folder):
                os.rmdir(local_folder)
    except FileNotFoundError:
        return
    except OSError:
        # Ignore race conditions or non-empty directories created in the meantime.
        return
    except Exception as exc:
        logger.error(
            "Failed deleting local folder '%s': error_type=%s error=%s",
            folder,
            type(exc).__name__,
            str(exc),
        )


def _delete_storage_prefix_tree(folder_path: str | None) -> None:
    folder = _normalize_storage_prefix(folder_path)
    if not folder:
        return

    pending_paths = [folder]
    visited = set()

    while pending_paths:
        current = pending_paths.pop()
        if current in visited:
            continue
        visited.add(current)

        try:
            directories, files = default_storage.listdir(current)
        except FileNotFoundError:
            continue
        except Exception as exc:
            logger.error(
                "Failed listing folder '%s' while deleting tree: error_type=%s error=%s",
                current,
                type(exc).__name__,
                str(exc),
            )
            continue

        for filename in files:
            file_path = posixpath.join(current, filename) if current else filename
            _delete_storage_file_if_exists(file_path)

        for dirname in directories:
            subfolder_path = posixpath.join(current, dirname) if current else dirname
            pending_paths.append(subfolder_path)

    for current in sorted(visited, key=lambda path: path.count("/"), reverse=True):
        _delete_empty_storage_folder(current)


def cleanup_document_storage_task(*, file_path: str, folder_path: str | None = None) -> None:
    """Delete a document object from storage, then remove its folder when empty."""
    normalized_file_path = str(file_path or "").strip()
    if not normalized_file_path:
        return

    try:
        _delete_storage_file_if_exists(normalized_file_path)
        _delete_empty_storage_folder(folder_path)
    except Exception as exc:
        logger.error(
            "Unexpected error in cleanup_document_storage_task: file_path=%s folder_path=%s error_type=%s error=%s",
            normalized_file_path,
            folder_path,
            type(exc).__name__,
            str(exc),
        )


def cleanup_application_storage_folder_task(*, folder_path: str) -> None:
    """Delete all storage objects for one application folder."""
    normalized_folder_path = _normalize_storage_prefix(folder_path)
    if not normalized_folder_path:
        return

    try:
        _delete_storage_prefix_tree(normalized_folder_path)
    except Exception as exc:
        logger.error(
            "Unexpected error in cleanup_application_storage_folder_task: folder_path=%s error_type=%s error=%s",
            normalized_folder_path,
            type(exc).__name__,
            str(exc),
        )


def _append_provider_message(existing: str, new_line: str) -> str:
    if existing:
        return f"{existing}\n{new_line}"
    return new_line


def _is_meta_status_lookup_unsupported(exc: Exception) -> bool:
    text = str(exc or "")
    lowered = text.lower()
    return (
        "unsupported get request" in lowered
        and "graphmethodexception" in lowered
        and (
            '"error_subcode":33' in lowered
            or "'error_subcode': 33" in lowered
            or "subcode\":33" in lowered
            or "subcode=33" in lowered
        )
    )


def schedule_whatsapp_status_poll(*, notification_id: int, delay_seconds: int = 5) -> None:
    if not notification_id:
        return

    def _enqueue():
        enqueue_poll_whatsapp_delivery_statuses_task(
            notification_ids=[notification_id],
            delay_seconds=delay_seconds,
        )

    try:
        transaction.on_commit(_enqueue)
    except Exception as exc:
        logger.error(
            "Failed to enqueue WhatsApp status poll: notification_id=%s delay_seconds=%s error_type=%s error=%s",
            notification_id,
            delay_seconds,
            type(exc).__name__,
            str(exc),
        )


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
            if channel == application.NOTIFY_CHANNEL_WHATSAPP:
                # Cloud API acceptance does not guarantee recipient delivery.
                notification.status = WorkflowNotification.STATUS_PENDING
                notification.external_reference = str(message)
                notification.sent_at = None
                result = "pending"
            else:
                notification.status = WorkflowNotification.STATUS_SENT
                notification.external_reference = ""
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
    if channel == application.NOTIFY_CHANNEL_WHATSAPP and notification.external_reference:
        schedule_whatsapp_status_poll(notification_id=notification.id, delay_seconds=5)
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


def poll_whatsapp_delivery_statuses(*, notification_ids=None, limit=None):
    from customer_applications.models import WorkflowNotification
    from notifications.services.providers import (
        MetaWhatsAppStatusLookupUnsupported,
        WhatsappNotificationProvider,
        process_whatsapp_webhook_payload,
    )

    provider = WhatsappNotificationProvider()
    poll_limit = int(getattr(settings, "WHATSAPP_STATUS_POLL_LIMIT", 500)) if limit is None else int(limit)
    cutoff = timezone.now() - timedelta(days=1)
    notifications = WorkflowNotification.objects.filter(
        channel=WorkflowNotification.CHANNEL_WHATSAPP,
        status__in=[WorkflowNotification.STATUS_PENDING, WorkflowNotification.STATUS_SENT],
        created_at__gte=cutoff,
    ).exclude(provider_message__contains=WHATSAPP_POLL_UNSUPPORTED_MARKER).order_by("id")

    if notification_ids is not None:
        notifications = notifications.filter(id__in=list(notification_ids))

    checked = 0
    updated = 0
    skipped = 0
    failed = 0

    for notification in notifications[:poll_limit]:
        message_id = str(notification.external_reference or "").strip()
        if not message_id:
            skipped += 1
            continue

        try:
            result = provider.get_message_status(message_id=message_id)
            status_value = str(result.get("status") or "").strip().lower()
            if not status_value:
                skipped += 1
                continue

            handled = process_whatsapp_webhook_payload(
                {
                    "object": "whatsapp_business_account",
                    "entry": [
                        {
                            "changes": [
                                {
                                    "field": "messages",
                                    "value": {
                                        "statuses": [
                                            {
                                                "id": message_id,
                                                "status": status_value,
                                                "recipient_id": notification.recipient,
                                            }
                                        ]
                                    },
                                }
                            ]
                        }
                    ],
                }
            )
            checked += 1
            updated += int(handled.get("status_updates", 0) or 0)
        except Exception as exc:
            if isinstance(exc, MetaWhatsAppStatusLookupUnsupported) or _is_meta_status_lookup_unsupported(exc):
                skipped += 1
                logger.info(
                    "WhatsApp status poll unsupported: notification_id=%s message_id=%s detail=%s",
                    notification.id,
                    message_id,
                    str(exc),
                )
                if WHATSAPP_POLL_UNSUPPORTED_MARKER not in (notification.provider_message or ""):
                    notification.provider_message = _append_provider_message(
                        notification.provider_message,
                        WHATSAPP_POLL_UNSUPPORTED_MARKER,
                    )
                    notification.save(update_fields=["provider_message", "updated_at"])
                continue

            failed += 1
            logger.error(
                "WhatsApp status poll failed: notification_id=%s message_id=%s error_type=%s error=%s",
                notification.id,
                message_id,
                type(exc).__name__,
                str(exc),
            )
            notification.provider_message = _append_provider_message(
                notification.provider_message,
                f"Meta poll error: {type(exc).__name__}: {exc}",
            )
            notification.save(update_fields=["provider_message", "updated_at"])

    logger.info(
        "WhatsApp status poll completed: checked=%s updated=%s skipped=%s failed=%s",
        checked,
        updated,
        skipped,
        failed,
    )
    return {"checked": checked, "updated": updated, "skipped": skipped, "failed": failed}


def poll_whatsapp_delivery_statuses_task(*, notification_ids=None, limit=None):
    return poll_whatsapp_delivery_statuses(notification_ids=notification_ids, limit=limit)


def send_due_tomorrow_customer_notifications_task():
    return send_due_tomorrow_customer_notifications()


def enqueue_cleanup_document_storage_task(
    *,
    file_path: str,
    folder_path: str | None = None,
    delay_seconds: int | float | None = None,
) -> str | None:
    return enqueue_job(
        entrypoint=ENTRYPOINT_CLEANUP_DOCUMENT_STORAGE_TASK,
        payload={"file_path": file_path, "folder_path": folder_path},
        delay_seconds=delay_seconds,
        run_local=cleanup_document_storage_task,
    )


def enqueue_cleanup_application_storage_folder_task(
    *,
    folder_path: str,
    delay_seconds: int | float | None = None,
) -> str | None:
    return enqueue_job(
        entrypoint=ENTRYPOINT_CLEANUP_APPLICATION_STORAGE_FOLDER_TASK,
        payload={"folder_path": folder_path},
        delay_seconds=delay_seconds,
        run_local=cleanup_application_storage_folder_task,
    )


def enqueue_sync_application_calendar_task(
    *,
    application_id: int,
    user_id: int | None = None,
    action: str = SYNC_ACTION_UPSERT,
    previous_due_date: str | None = None,
    start_date: str | None = None,
    known_event_ids: list[str] | None = None,
    delay_seconds: int | float | None = None,
) -> str | None:
    return enqueue_job(
        entrypoint=ENTRYPOINT_SYNC_APPLICATION_CALENDAR_TASK,
        payload={
            "application_id": int(application_id),
            "user_id": user_id,
            "action": action,
            "previous_due_date": previous_due_date,
            "start_date": start_date,
            "known_event_ids": known_event_ids,
        },
        delay_seconds=delay_seconds,
        run_local=sync_application_calendar_task,
    )


def enqueue_poll_whatsapp_delivery_statuses_task(
    *,
    notification_ids=None,
    limit=None,
    delay_seconds: int | float | None = None,
) -> str | None:
    return enqueue_job(
        entrypoint=ENTRYPOINT_POLL_WHATSAPP_DELIVERY_STATUSES_TASK,
        payload={"notification_ids": notification_ids, "limit": limit},
        delay_seconds=delay_seconds,
        run_local=poll_whatsapp_delivery_statuses_task,
    )


def enqueue_send_due_tomorrow_customer_notifications_task(
    *,
    delay_seconds: int | float | None = None,
) -> str | None:
    return enqueue_job(
        entrypoint=ENTRYPOINT_SEND_DUE_TOMORROW_CUSTOMER_NOTIFICATIONS_TASK,
        payload={},
        delay_seconds=delay_seconds,
        run_local=send_due_tomorrow_customer_notifications_task,
    )
