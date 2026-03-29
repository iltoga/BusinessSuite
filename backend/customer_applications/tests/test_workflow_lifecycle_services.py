"""Tests for customer application workflow lifecycle services."""

from contextlib import nullcontext
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from customer_applications.models import DocApplication, Document, DocWorkflow
from customer_applications.services.application_lifecycle_service import ApplicationLifecycleService
from customer_applications.services.stay_permit_workflow_schedule_service import StayPermitWorkflowScheduleService
from customer_applications.services.workflow_status_transition_service import (
    WorkflowStatusTransitionError,
    WorkflowStatusTransitionService,
)
from customers.models import Customer
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from products.models import DocumentType, Product, Task
from rest_framework.exceptions import ValidationError

User = get_user_model()


class ApplicationLifecycleServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("lifecycle-user", "lifecycle@example.com", "pass")
        self.customer = Customer.objects.create(first_name="Lifecycle", last_name="Tester")
        self.product = Product.objects.create(
            name="Lifecycle Product",
            code="LIFE-1",
            product_type="visa",
        )
        self.step1 = Task.objects.create(
            product=self.product,
            step=1,
            name="Collect docs",
            duration=2,
            duration_is_business_days=False,
            add_task_to_calendar=True,
        )
        self.step2 = Task.objects.create(
            product=self.product,
            step=2,
            name="Review docs",
            duration=3,
            duration_is_business_days=False,
            add_task_to_calendar=True,
        )
        self.service = ApplicationLifecycleService()

    def _create_application_with_step_one(self) -> tuple[DocApplication, DocWorkflow]:
        application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=date(2026, 1, 10),
            created_by=self.user,
        )
        workflow = DocWorkflow.objects.create(
            doc_application=application,
            task=self.step1,
            start_date=date(2026, 1, 10),
            due_date=date(2026, 1, 15),
            status=DocApplication.STATUS_PENDING,
            created_by=self.user,
        )
        application.due_date = workflow.due_date
        application.save(update_fields=["due_date", "updated_at"])
        return application, workflow

    def test_advance_workflow_completes_current_step_and_creates_next_step(self):
        application, current_workflow = self._create_application_with_step_one()

        result = self.service.advance_workflow(application=application, user=self.user)

        application.refresh_from_db()
        current_workflow.refresh_from_db()
        next_workflow = application.workflows.get(task__step=2)

        self.assertEqual(current_workflow.status, DocApplication.STATUS_COMPLETED)
        self.assertEqual(next_workflow.status, DocApplication.STATUS_PENDING)
        self.assertEqual(result.previous_due_date, date(2026, 1, 15))
        self.assertEqual(result.start_date, date(2026, 1, 15))
        self.assertEqual(application.updated_by, self.user)
        self.assertEqual(application.due_date, next_workflow.due_date)

    def test_advance_workflow_requires_current_workflow(self):
        application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=date(2026, 1, 10),
            created_by=self.user,
        )

        with self.assertRaises(ValidationError):
            self.service.advance_workflow(application=application, user=self.user)

    def test_delete_application_blocks_when_can_be_deleted_returns_false(self):
        application = MagicMock()
        application.can_be_deleted.return_value = (False, "Related invoices exist.")

        with self.assertRaises(ValidationError):
            self.service.delete_application(application=application, user=self.user, delete_invoices=True)

        application.can_be_deleted.assert_called_once_with(user=self.user, delete_invoices=True)

    def test_delete_application_removes_orphaned_invoices_and_keeps_linked_invoices(self):
        application = MagicMock()
        application.can_be_deleted.return_value = (True, None)
        application.invoice_applications.values_list.return_value.distinct.return_value = [101, 202]
        application.delete = MagicMock()
        application.save = MagicMock()

        orphan_invoice = MagicMock()
        orphan_invoice.invoice_applications.count.return_value = 0
        linked_invoice = MagicMock()
        linked_invoice.invoice_applications.count.return_value = 2

        def _filter_side_effect(*args, **kwargs):
            query = MagicMock()
            if kwargs.get("pk") == 101:
                query.first.return_value = orphan_invoice
            elif kwargs.get("pk") == 202:
                query.first.return_value = linked_invoice
            else:
                query.first.return_value = None
            return query

        with patch(
            "customer_applications.services.application_lifecycle_service.transaction.atomic",
            return_value=nullcontext(),
        ), patch(
            "customer_applications.services.application_lifecycle_service.Invoice.objects.filter",
            side_effect=_filter_side_effect,
        ):
            self.service.delete_application(application=application, user=self.user, delete_invoices=True)

        application.can_be_deleted.assert_called_once_with(user=self.user, delete_invoices=True)
        application.save.assert_called_once_with(update_fields=["updated_by", "updated_at"])
        application.delete.assert_called_once_with(force_delete_invoices=True, user=self.user)
        orphan_invoice.delete.assert_called_once_with(force=True)
        linked_invoice.save.assert_called_once()


class StayPermitWorkflowScheduleServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("schedule-user", "schedule@example.com", "pass")
        self.customer = Customer.objects.create(first_name="Schedule", last_name="Tester")
        self.product = Product.objects.create(
            name="Stay Permit Schedule Product",
            code="SCHED-1",
            product_type="visa",
            required_documents="ITAS",
            application_window_days=30,
        )
        self.task = Task.objects.create(
            product=self.product,
            step=1,
            name="Submit docs",
            duration=2,
            duration_is_business_days=False,
            add_task_to_calendar=True,
        )
        self.stay_doc_type = DocumentType.objects.create(
            name="ITAS",
            is_stay_permit=True,
            has_expiration_date=True,
            has_file=True,
        )
        self.service = StayPermitWorkflowScheduleService()

    def test_sync_creates_step_one_from_submission_window(self):
        application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=date(2026, 2, 1),
            created_by=self.user,
        )

        Document.objects.create(
            doc_application=application,
            doc_type=self.stay_doc_type,
            expiration_date=date(2026, 4, 1),
            required=True,
            created_by=self.user,
            updated_by=self.user,
        )

        step_one = self.service.sync(application=application, actor_user_id=self.user.id)

        application.refresh_from_db()
        self.assertIsNotNone(step_one)
        self.assertEqual(application.doc_date, date(2026, 3, 2))
        self.assertEqual(application.due_date, date(2026, 3, 4))
        self.assertEqual(step_one.start_date, date(2026, 3, 2))
        self.assertEqual(step_one.due_date, date(2026, 3, 4))


class WorkflowStatusTransitionServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("transition-user", "transition@example.com", "pass")
        self.customer = Customer.objects.create(first_name="Transition", last_name="Tester")
        self.product = Product.objects.create(
            name="Workflow Transition Product",
            code="TRN-1",
            product_type="visa",
        )
        self.step1 = Task.objects.create(
            product=self.product,
            step=1,
            name="Step 1",
            duration=2,
            duration_is_business_days=False,
            add_task_to_calendar=True,
        )
        self.step2 = Task.objects.create(
            product=self.product,
            step=2,
            name="Step 2",
            duration=3,
            duration_is_business_days=False,
            add_task_to_calendar=True,
        )
        self.service = WorkflowStatusTransitionService()

    def _create_application_with_step_one(self, *, step_one_status: str = DocApplication.STATUS_PENDING):
        application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=date(2026, 1, 10),
            created_by=self.user,
        )
        workflow = DocWorkflow.objects.create(
            doc_application=application,
            task=self.step1,
            start_date=date(2026, 1, 10),
            due_date=date(2026, 1, 15),
            status=step_one_status,
            created_by=self.user,
        )
        application.due_date = workflow.due_date
        application.save(update_fields=["due_date", "updated_at"])
        return application, workflow

    def test_valid_statuses_matches_application_choices(self):
        self.assertEqual(
            self.service.valid_statuses(),
            {choice[0] for choice in DocApplication.STATUS_CHOICES},
        )

    def test_get_previous_workflow_returns_prior_step(self):
        application, _ = self._create_application_with_step_one(step_one_status=DocApplication.STATUS_COMPLETED)
        step_two = DocWorkflow.objects.create(
            doc_application=application,
            task=self.step2,
            start_date=date(2026, 1, 15),
            due_date=date(2026, 1, 20),
            status=DocApplication.STATUS_PENDING,
            created_by=self.user,
        )

        self.assertEqual(self.service.get_previous_workflow(step_two).task.step, 1)

    def test_transition_rejects_invalid_status(self):
        _, workflow = self._create_application_with_step_one()

        with self.assertRaises(WorkflowStatusTransitionError):
            self.service.transition(workflow=workflow, status_value="not-a-status", user=self.user)

    def test_transition_completes_step_and_creates_next_pending_workflow(self):
        application, workflow = self._create_application_with_step_one()

        result = self.service.transition(
            workflow=workflow,
            status_value=DocApplication.STATUS_COMPLETED,
            user=self.user,
        )

        application.refresh_from_db()
        workflow.refresh_from_db()
        next_workflow = application.workflows.get(task__step=2)

        self.assertTrue(result.changed)
        self.assertEqual(workflow.status, DocApplication.STATUS_COMPLETED)
        self.assertEqual(next_workflow.status, DocApplication.STATUS_PENDING)
        self.assertEqual(result.next_start_date, timezone.localdate())
        self.assertEqual(application.due_date, next_workflow.due_date)

    def test_transition_blocks_processing_before_previous_due_date(self):
        application, workflow = self._create_application_with_step_one(step_one_status=DocApplication.STATUS_COMPLETED)
        workflow_one = workflow
        workflow_one.due_date = timezone.localdate() + timedelta(days=3)
        workflow_one.save(update_fields=["due_date", "updated_at"])

        step_two = DocWorkflow.objects.create(
            doc_application=application,
            task=self.step2,
            start_date=date(2026, 1, 15),
            due_date=date(2026, 1, 20),
            status=DocApplication.STATUS_PENDING,
            created_by=self.user,
        )
        application.due_date = step_two.due_date
        application.save(update_fields=["due_date", "updated_at"])

        with self.assertRaises(WorkflowStatusTransitionError) as ctx:
            self.service.transition(
                workflow=step_two,
                status_value=DocApplication.STATUS_PROCESSING,
                user=self.user,
            )

        self.assertIn("system date (GMT+8)", str(ctx.exception))
