import logging
import traceback

from core.models.async_job import AsyncJob
from customer_applications.models import DocApplication
from django.contrib.auth import get_user_model
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


@db_periodic_task(crontab(minute="*/5"), name="customer_applications.send_pending_notifications")
def send_pending_notifications_task():
    """Send due notifications that were scheduled by application calendar sync."""
    from customer_applications.models import WorkflowNotification
    from notifications.services.providers import NotificationDispatcher

    now = timezone.now()
    notifications = WorkflowNotification.objects.filter(
        status=WorkflowNotification.STATUS_PENDING,
        scheduled_for__isnull=False,
        scheduled_for__lte=now,
    )[:100]

    dispatcher = NotificationDispatcher()
    for notification in notifications:
        try:
            message = dispatcher.send(
                channel=notification.channel,
                recipient=notification.recipient,
                subject=notification.subject,
                body=notification.body,
            )
            notification.status = WorkflowNotification.STATUS_SENT
            notification.provider_message = message
            notification.sent_at = timezone.now()
        except Exception as exc:
            notification.status = WorkflowNotification.STATUS_FAILED
            notification.provider_message = str(exc)
        notification.save(update_fields=["status", "provider_message", "sent_at", "updated_at"])
