"""
FILE_ROLE: Service-layer logic for the customer applications app.

KEY_COMPONENTS:
- ApplicationLifecycleService: Service class.

INTERACTIONS:
- Depends on: nearby Django models, services, serializers, and the app packages imported by this module.

AI_GUIDELINES:
- Keep the module focused on its narrow layer boundary and avoid moving cross-cutting workflow code here.
- Preserve the existing API/model contract because other modules import these symbols directly.
"""

from dataclasses import dataclass

from customer_applications.models import DocApplication
from customer_applications.models.doc_workflow import DocWorkflow
from django.db import transaction
from django.utils import timezone
from invoices.models.invoice import Invoice
from rest_framework.exceptions import ValidationError


@dataclass
class AdvanceWorkflowResult:
    application: DocApplication
    previous_due_date: object
    start_date: object


class ApplicationLifecycleService:
    """Domain logic for application workflow advancement and deletion."""

    def advance_workflow(self, *, application: DocApplication, user) -> AdvanceWorkflowResult:
        current_workflow = application.current_workflow
        if not current_workflow:
            raise ValidationError("No current workflow found")
        if current_workflow.status in DocWorkflow.TERMINAL_STATUSES:
            raise ValidationError("Current task is already finalized")

        start_date = current_workflow.due_date

        current_workflow.status = DocApplication.STATUS_COMPLETED
        current_workflow.updated_by = user
        current_workflow.save()

        next_task = application.next_task
        if next_task and not application.workflows.filter(task_id=next_task.id).exists():
            step = DocWorkflow(
                start_date=timezone.now().date(),
                task=next_task,
                doc_application=application,
                created_by=user,
                status=DocApplication.STATUS_PENDING,
            )
            step.due_date = step.calculate_workflow_due_date()
            step.save()

        previous_due_date = application.due_date
        current_after_update = application.current_workflow
        if current_after_update and current_after_update.due_date != application.due_date:
            application.due_date = current_after_update.due_date
        application.updated_by = user
        application.save()

        return AdvanceWorkflowResult(
            application=application,
            previous_due_date=previous_due_date,
            start_date=start_date,
        )

    def delete_application(self, *, application: DocApplication, user, delete_invoices: bool = False) -> None:
        can_delete, msg = application.can_be_deleted(user=user, delete_invoices=delete_invoices)
        if not can_delete:
            raise ValidationError(msg)

        with transaction.atomic():
            application.updated_by = user
            application.save(update_fields=["updated_by", "updated_at"])

            invoice_ids = list(application.invoice_applications.values_list("invoice_id", flat=True).distinct())
            if delete_invoices:
                application.invoice_applications.all().delete()
            application.delete(force_delete_invoices=delete_invoices, user=user)
            for invoice_id in invoice_ids:
                invoice = Invoice.objects.filter(pk=invoice_id).first()
                if not invoice:
                    continue
                if invoice.invoice_applications.count() == 0:
                    invoice.delete(force=True)
                else:
                    invoice.save()
