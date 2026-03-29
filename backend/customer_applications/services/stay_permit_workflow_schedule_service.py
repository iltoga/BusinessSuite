"""
FILE_ROLE: Service-layer logic for the customer applications app.

KEY_COMPONENTS:
- StayPermitWorkflowScheduleService: Service class.

INTERACTIONS:
- Depends on: nearby Django models, services, serializers, and the app packages imported by this module.

AI_GUIDELINES:
- Keep the module focused on its narrow layer boundary and avoid moving cross-cutting workflow code here.
- Preserve the existing API/model contract because other modules import these symbols directly.
"""

from __future__ import annotations

from core.utils.dateutils import calculate_due_date
from customer_applications.models import DocApplication
from customer_applications.models.doc_workflow import DocWorkflow
from django.db import transaction


class StayPermitWorkflowScheduleService:
    """Create or reschedule step 1 when a stay-permit submission window becomes available."""

    def sync(self, *, application, actor_user_id: int | None = None) -> DocWorkflow | None:
        product = getattr(application, "product", None)
        if not product:
            return None

        if not product.tasks.exists():
            if application.due_date is not None:
                application.due_date = None
                application.save(update_fields=["due_date", "updated_at"])
            return None

        from customer_applications.services.stay_permit_submission_window_service import (
            StayPermitSubmissionWindowService,
        )

        window_service = StayPermitSubmissionWindowService()
        if not window_service.product_requires_submission_window(product):
            return None

        first_task = product.tasks.order_by("step").first()
        if not first_task:
            return None

        step_one = (
            application.workflows.select_related("task")
            .filter(task__step=1)
            .order_by("task__step", "created_at", "id")
            .first()
        )
        submission_date = window_service.resolve_submission_date(product=product, application=application)

        with transaction.atomic():
            if not submission_date:
                if step_one and step_one.status == DocApplication.STATUS_PENDING:
                    step_one.delete()
                if application.due_date is not None:
                    application.due_date = None
                    application.save(update_fields=["due_date", "updated_at"])
                return None

            if application.doc_date != submission_date:
                application.doc_date = submission_date
                application.save(update_fields=["doc_date", "updated_at"])

            start_date = submission_date
            due_date = calculate_due_date(
                start_date=start_date,
                days_to_complete=first_task.duration,
                business_days_only=first_task.duration_is_business_days,
            )

            if step_one is None:
                step_one = DocWorkflow.objects.create(
                    doc_application=application,
                    task=first_task,
                    start_date=start_date,
                    due_date=due_date or start_date,
                    status=DocApplication.STATUS_PENDING,
                    created_by_id=actor_user_id or application.updated_by_id or application.created_by_id,
                    updated_by_id=actor_user_id,
                )
            elif step_one.status == DocApplication.STATUS_PENDING:
                update_fields: list[str] = []
                if step_one.start_date != start_date:
                    step_one.start_date = start_date
                    update_fields.append("start_date")
                if due_date and step_one.due_date != due_date:
                    step_one.due_date = due_date
                    update_fields.append("due_date")
                if actor_user_id and step_one.updated_by_id != actor_user_id:
                    step_one.updated_by_id = actor_user_id
                    update_fields.append("updated_by")
                if update_fields:
                    step_one.save(update_fields=update_fields + ["updated_at"])

            if application.due_date != due_date:
                application.due_date = due_date
                application.save(update_fields=["due_date", "updated_at"])

        return step_one
