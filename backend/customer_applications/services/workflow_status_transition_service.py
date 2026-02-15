from dataclasses import dataclass

from customer_applications.models.doc_workflow import DocWorkflow
from django.db import transaction
from django.utils import timezone


class WorkflowStatusTransitionError(Exception):
    """Raised when a workflow status transition violates business rules."""


@dataclass
class WorkflowStatusTransitionResult:
    workflow: DocWorkflow
    application: object
    previous_due_date: object
    next_start_date: object
    changed: bool


class WorkflowStatusTransitionService:
    """Shared workflow status transition logic used by multiple API surfaces."""

    @staticmethod
    def valid_statuses() -> set[str]:
        return {choice[0] for choice in DocWorkflow.STATUS_CHOICES}

    @staticmethod
    def get_previous_workflow(workflow: DocWorkflow):
        return (
            workflow.doc_application.workflows.filter(task__step__lt=workflow.task.step)
            .order_by("-task__step", "-created_at", "-id")
            .first()
        )

    def transition(self, *, workflow: DocWorkflow, status_value: str, user) -> WorkflowStatusTransitionResult:
        if status_value not in self.valid_statuses():
            raise WorkflowStatusTransitionError("Invalid workflow status")

        application = workflow.doc_application
        if workflow.status == status_value:
            return WorkflowStatusTransitionResult(
                workflow=workflow,
                application=application,
                previous_due_date=application.due_date,
                next_start_date=None,
                changed=False,
            )

        if workflow.status in DocWorkflow.TERMINAL_STATUSES and workflow.status != status_value:
            raise WorkflowStatusTransitionError("Finalized tasks cannot be changed")

        current_workflow = application.current_workflow
        if current_workflow and current_workflow.id != workflow.id and workflow.status != status_value:
            raise WorkflowStatusTransitionError("Only the current task can be updated")

        moving_from_pending = workflow.status == DocWorkflow.STATUS_PENDING
        promoting_status = status_value in {DocWorkflow.STATUS_PROCESSING, DocWorkflow.STATUS_COMPLETED}
        if moving_from_pending and promoting_status and workflow.task.step > 1:
            previous_workflow = self.get_previous_workflow(workflow)
            if previous_workflow and previous_workflow.due_date and timezone.localdate() < previous_workflow.due_date:
                raise WorkflowStatusTransitionError(
                    "Status can move to processing/completed only when system date (GMT+8) is on/after "
                    f"previous task due date ({previous_workflow.due_date.isoformat()})"
                )

        previous_due_date = application.due_date
        next_start_date = None
        with transaction.atomic():
            workflow.status = status_value
            workflow.updated_by = user
            workflow.save()

            # Completing a non-final task automatically creates the next one as pending.
            if status_value == DocWorkflow.STATUS_COMPLETED:
                next_task = workflow.next_task_in_sequence
                if next_task and not application.workflows.filter(task_id=next_task.id).exists():
                    next_workflow = DocWorkflow(
                        start_date=timezone.localdate(),
                        task=next_task,
                        doc_application=application,
                        created_by=user,
                        status=DocWorkflow.STATUS_PENDING,
                    )
                    next_workflow.due_date = next_workflow.calculate_workflow_due_date()
                    next_workflow.save()
                    next_start_date = next_workflow.start_date

            current_after_update = application.current_workflow
            if current_after_update and current_after_update.due_date != application.due_date:
                application.due_date = current_after_update.due_date

            application.updated_by = user
            application.save()

        return WorkflowStatusTransitionResult(
            workflow=workflow,
            application=application,
            previous_due_date=previous_due_date,
            next_start_date=next_start_date,
            changed=True,
        )
