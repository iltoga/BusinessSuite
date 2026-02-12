import logging
import traceback
from datetime import datetime, time, timedelta

from core.models.async_job import AsyncJob
from customer_applications.models import DocApplication
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils import timezone
from huey import crontab
from huey.contrib.djhuey import db_periodic_task, db_task

User = get_user_model()
logger = logging.getLogger(__name__)


@db_task()
def create_application_task(job_id, data, user_id):
    """Background task to create a customer application and sync calendar."""
    try:
        job = AsyncJob.objects.get(id=job_id)
        job.update_progress(10, "Starting application creation...", status=AsyncJob.STATUS_PROCESSING)

        user = User.objects.get(pk=user_id)

        # We use the serializer logic but inside the task
        from api.serializers.doc_application_serializer import DocApplicationCreateUpdateSerializer
        from rest_framework.request import Request
        from rest_framework.test import APIRequestFactory

        # Mock request for serializer context
        factory = APIRequestFactory()
        request = factory.post("/")
        request.user = user

        serializer = DocApplicationCreateUpdateSerializer(data=data, context={"request": request})
        if serializer.is_valid():
            job.update_progress(30, "Saving application and documents...")
            application = serializer.save()

            job.update_progress(70, "Syncing with Google Calendar...")
            # Calendar sync is already called in serializer.save(),
            # but we can call it again or make sure it's called here if we want more progress updates.
            # Actually, we might want to refactor the serializer to NOT call it if we are in a task,
            # but for now, it's fine as it runs in the background.

            job.complete(
                result={"id": application.id, "str_field": str(application)}, message="Application created successfully"
            )
        else:
            job.fail(error_message=str(serializer.errors))

    except Exception as e:
        logger.error(f"Error in create_application_task: {str(e)}")
        job = AsyncJob.objects.get(id=job_id)
        job.fail(error_message=str(e), traceback=traceback.format_exc())


@db_task()
def update_application_task(job_id, application_id, data, user_id):
    """Background task to update a customer application and sync calendar."""
    try:
        job = AsyncJob.objects.get(id=job_id)
        job.update_progress(10, "Starting application update...", status=AsyncJob.STATUS_PROCESSING)

        user = User.objects.get(pk=user_id)
        application = DocApplication.objects.get(pk=application_id)

        from api.serializers.doc_application_serializer import DocApplicationCreateUpdateSerializer
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        request = factory.patch("/")
        request.user = user

        serializer = DocApplicationCreateUpdateSerializer(
            application, data=data, partial=True, context={"request": request}
        )
        if serializer.is_valid():
            job.update_progress(40, "Saving changes...")
            serializer.save()

            job.update_progress(80, "Updating Google Calendar...")
            # Calendar sync called in serializer.save()

            job.complete(
                result={"id": application.id, "str_field": str(application)}, message="Application updated successfully"
            )
        else:
            job.fail(error_message=str(serializer.errors))

    except Exception as e:
        logger.error(f"Error in update_application_task: {str(e)}")
        job = AsyncJob.objects.get(id=job_id)
        job.fail(error_message=str(e), traceback=traceback.format_exc())


@db_task()
def delete_application_task(job_id, application_id, user_id, delete_invoices=False):
    """Background task to delete a customer application."""
    try:
        job = AsyncJob.objects.get(id=job_id)
        job.update_progress(10, "Starting application deletion...", status=AsyncJob.STATUS_PROCESSING)

        user = User.objects.get(pk=user_id)
        application = DocApplication.objects.get(pk=application_id)

        # Re-verify deletion permission
        can_delete, msg = application.can_be_deleted(user=user, delete_invoices=delete_invoices)
        if not can_delete:
            job.fail(error_message=msg)
            return

        job.update_progress(50, "Deleting application...")
        # Since we are in background, we can handle the transaction here if needed
        # but CustomerApplicationViewSet already had some complex logic for invoices.
        # We'll replicate it or move it to a service.

        from django.db import transaction
        from invoices.models.invoice import Invoice

        invoice_ids = list(application.invoice_applications.values_list("invoice_id", flat=True).distinct())

        with transaction.atomic():
            application.delete(force_delete_invoices=delete_invoices, user=user)
            # Cleanup invoices
            for inv_id in invoice_ids:
                invoice = Invoice.objects.filter(pk=inv_id).first()
                if invoice and invoice.invoice_applications.count() == 0:
                    invoice.delete(force=True)

        job.complete(message="Application deleted successfully")

    except Exception as e:
        logger.error(f"Error in delete_application_task: {str(e)}")
        job = AsyncJob.objects.get(id=job_id)
        job.fail(error_message=str(e), traceback=traceback.format_exc())


@db_task()
def advance_workflow_task(job_id, application_id, user_id):
    """Background task to advance application workflow."""
    try:
        job = AsyncJob.objects.get(id=job_id)
        job.update_progress(10, "Advancing workflow...", status=AsyncJob.STATUS_PROCESSING)

        user = User.objects.get(pk=user_id)
        application = DocApplication.objects.get(pk=application_id)

        # Logic from advance_workflow view
        from django.utils import timezone

        current_workflow = application.current_workflow
        if not current_workflow:
            job.fail(error_message="No current workflow found")
            return

        job.update_progress(40, "Completing current step...")
        current_workflow.status = current_workflow.STATUS_COMPLETED
        current_workflow.updated_by = user
        current_workflow.save()

        # Create next workflow if exists
        next_task = application.next_task
        if next_task:
            from customer_applications.models.doc_workflow import DocWorkflow

            step = DocWorkflow(
                start_date=timezone.now().date(),
                task=next_task,
                doc_application=application,
                created_by=user,
                status=DocWorkflow.STATUS_PENDING,
            )
            step.due_date = step.calculate_workflow_due_date()
            step.save()

        # Refresh application status
        previous_due_date = application.due_date
        application.save()

        job.update_progress(80, "Syncing Google Calendar...")
        from customer_applications.services.application_calendar_service import ApplicationCalendarService

        ApplicationCalendarService().sync_next_task_deadline(
            application,
            start_date=current_workflow.due_date,
            previous_due_date=previous_due_date,
        )

        job.complete(message="Workflow advanced successfully")

    except Exception as e:
        logger.error(f"Error in advance_workflow_task: {str(e)}")
        job = AsyncJob.objects.get(id=job_id)
        job.fail(error_message=str(e), traceback=traceback.format_exc())


def send_due_tomorrow_customer_notifications(now=None):
    """Send customer reminders for applications whose deadline is tomorrow.

    Conditions:
    - application.notify_customer_too == True
    - due_date is tomorrow
    - next calendar task exists and task.notify_customer == True
    - recipient exists for selected channel
    """
    from customer_applications.models import WorkflowNotification
    from notifications.services.customer_deadline_messages import (
        build_customer_deadline_notification_payload,
    )
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

    dispatcher = NotificationDispatcher()
    sent_count = 0
    failed_count = 0
    skipped_count = 0
    scheduled_for = timezone.make_aware(datetime.combine(today, time(hour=8, minute=0)))

    for application in applications:
        task = application.get_next_calendar_task()
        if not task or not task.notify_customer:
            skipped_count += 1
            continue

        channel = application.notify_customer_channel or application.NOTIFY_CHANNEL_EMAIL
        recipient = application.customer.whatsapp if channel == application.NOTIFY_CHANNEL_WHATSAPP else application.customer.email
        if not recipient:
            skipped_count += 1
            continue

        payload = build_customer_deadline_notification_payload(application, task, application.due_date)
        subject = payload["subject"]
        body = payload["email_text"] if channel == application.NOTIFY_CHANNEL_EMAIL else payload["whatsapp_text"]
        html_body = payload["email_html"] if channel == application.NOTIFY_CHANNEL_EMAIL else None

        duplicate_exists = WorkflowNotification.objects.filter(
            doc_application=application,
            channel=channel,
            subject=subject,
            scheduled_for__date=today,
            status__in=[WorkflowNotification.STATUS_PENDING, WorkflowNotification.STATUS_SENT],
        ).exists()
        if duplicate_exists:
            skipped_count += 1
            continue

        notification = WorkflowNotification.objects.create(
            channel=channel,
            recipient=recipient,
            subject=subject,
            body=body,
            doc_application=application,
            doc_workflow=None,
            status=WorkflowNotification.STATUS_PENDING,
            scheduled_for=scheduled_for,
        )

        try:
            message = dispatcher.send(
                channel=channel,
                recipient=recipient,
                subject=subject,
                body=body,
                html_body=html_body,
            )
            notification.status = WorkflowNotification.STATUS_SENT
            notification.provider_message = message
            notification.external_reference = message if channel == application.NOTIFY_CHANNEL_WHATSAPP else ""
            notification.sent_at = timezone.now()
            sent_count += 1
        except Exception as exc:
            notification.status = WorkflowNotification.STATUS_FAILED
            notification.provider_message = str(exc)
            failed_count += 1

        notification.save(
            update_fields=[
                "status",
                "provider_message",
                "external_reference",
                "sent_at",
                "updated_at",
            ]
        )

    logger.info(
        "Due-tomorrow notification job completed: sent=%s failed=%s skipped=%s target_date=%s",
        sent_count,
        failed_count,
        skipped_count,
        tomorrow.isoformat(),
    )
    return {"sent": sent_count, "failed": failed_count, "skipped": skipped_count}


@db_periodic_task(
    crontab(
        hour=getattr(settings, "CUSTOMER_NOTIFICATIONS_DAILY_HOUR", 8),
        minute=getattr(settings, "CUSTOMER_NOTIFICATIONS_DAILY_MINUTE", 0),
    ),
    name="customer_applications.send_due_tomorrow_customer_notifications",
)
def send_due_tomorrow_customer_notifications_task():
    return send_due_tomorrow_customer_notifications()
