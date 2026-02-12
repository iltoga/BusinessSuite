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

        start_date = current_workflow.due_date

        current_workflow.status = current_workflow.STATUS_COMPLETED
        current_workflow.updated_by = user
        current_workflow.save()

        next_task = application.next_task
        if next_task:
            step = DocWorkflow(
                start_date=timezone.now().date(),
                task=next_task,
                doc_application=application,
                created_by=user,
                status=DocWorkflow.STATUS_PENDING,
            )
            step.due_date = step.calculate_workflow_due_date()
            step.save()

        previous_due_date = application.due_date
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

        application.updated_by = user
        application.save(update_fields=["updated_by", "updated_at"])

        invoice_ids = list(application.invoice_applications.values_list("invoice_id", flat=True).distinct())
        with transaction.atomic():
            application.delete(force_delete_invoices=delete_invoices, user=user)
            for invoice_id in invoice_ids:
                invoice = Invoice.objects.filter(pk=invoice_id).first()
                if not invoice:
                    continue
                if invoice.invoice_applications.count() == 0:
                    invoice.delete(force=True)
                else:
                    invoice.save()
