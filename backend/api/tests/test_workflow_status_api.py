from customer_applications.models import DocApplication, Document
from customer_applications.models.doc_workflow import DocWorkflow
from customers.models import Customer
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from products.models import Product
from products.models.document_type import DocumentType
from rest_framework.test import APIClient

User = get_user_model()


class WorkflowStatusApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("workflow-status-admin", "workflowstatus@example.com", "pass")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.customer = Customer.objects.create(first_name="Workflow", last_name="Tester")
        self.doc_type = DocumentType.objects.create(name="Passport", has_doc_number=True)

    def _create_application_and_workflow(self, *, document_completed: bool, task_count: int = 1):
        product = Product.objects.create(
            name="Workflow Status Product",
            code=f"WSP-{task_count}-{1 if document_completed else 0}",
            product_type="visa",
            required_documents="Passport",
        )

        first_task = None
        for step in range(1, task_count + 1):
            task = product.tasks.create(
                step=step,
                name=f"Step {step}",
                duration=1,
                duration_is_business_days=True,
                # Keep this False on purpose: final step is inferred by sequence.
                last_step=False,
            )
            if first_task is None:
                first_task = task

        app = DocApplication.objects.create(
            customer=self.customer,
            product=product,
            doc_date=timezone.localdate(),
            created_by=self.user,
        )
        Document.objects.create(
            doc_application=app,
            doc_type=self.doc_type,
            required=True,
            doc_number="P123456" if document_completed else "",
            created_by=self.user,
        )
        workflow = DocWorkflow(
            start_date=timezone.localdate(),
            task=first_task,
            doc_application=app,
            created_by=self.user,
            status=DocWorkflow.STATUS_PENDING,
        )
        workflow.due_date = workflow.calculate_workflow_due_date()
        workflow.save()
        return app, workflow

    def test_update_workflow_status_creates_next_pending_workflow_for_non_last_step(self):
        app, workflow = self._create_application_and_workflow(document_completed=False, task_count=3)

        response = self.client.post(
            f"/api/customer-applications/{app.id}/workflows/{workflow.id}/status/",
            {"status": DocWorkflow.STATUS_COMPLETED},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        workflow.refresh_from_db()
        app.refresh_from_db()
        self.assertEqual(workflow.status, DocWorkflow.STATUS_COMPLETED)

        next_workflow = app.workflows.filter(task__step=2).first()
        self.assertIsNotNone(next_workflow)
        self.assertEqual(next_workflow.status, DocWorkflow.STATUS_PENDING)
        self.assertEqual(app.status, DocApplication.STATUS_PENDING)

    def test_update_workflow_status_sets_application_rejected(self):
        app, workflow = self._create_application_and_workflow(document_completed=True, task_count=3)

        response = self.client.post(
            f"/api/customer-applications/{app.id}/workflows/{workflow.id}/status/",
            {"status": DocWorkflow.STATUS_REJECTED},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        workflow.refresh_from_db()
        app.refresh_from_db()
        self.assertEqual(workflow.status, DocWorkflow.STATUS_REJECTED)
        self.assertEqual(app.status, DocApplication.STATUS_REJECTED)

    def test_update_workflow_status_sets_application_completed_on_last_step_even_if_documents_incomplete(self):
        app, workflow = self._create_application_and_workflow(document_completed=False, task_count=1)

        response = self.client.post(
            f"/api/customer-applications/{app.id}/workflows/{workflow.id}/status/",
            {"status": DocWorkflow.STATUS_COMPLETED},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        workflow.refresh_from_db()
        app.refresh_from_db()
        self.assertEqual(workflow.status, DocWorkflow.STATUS_COMPLETED)
        self.assertEqual(app.status, DocApplication.STATUS_COMPLETED)
        self.assertFalse(app.is_document_collection_completed)

    def test_update_workflow_status_disallows_changes_after_terminal_status(self):
        app, workflow = self._create_application_and_workflow(document_completed=True, task_count=1)

        response = self.client.post(
            f"/api/customer-applications/{app.id}/workflows/{workflow.id}/status/",
            {"status": DocWorkflow.STATUS_REJECTED},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            f"/api/customer-applications/{app.id}/workflows/{workflow.id}/status/",
            {"status": DocWorkflow.STATUS_PROCESSING},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Finalized tasks cannot be changed", str(response.data))

        workflow.refresh_from_db()
        self.assertEqual(workflow.status, DocWorkflow.STATUS_REJECTED)

    def test_rejected_application_stays_rejected_after_document_updates(self):
        app, workflow = self._create_application_and_workflow(document_completed=False, task_count=1)

        response = self.client.post(
            f"/api/customer-applications/{app.id}/workflows/{workflow.id}/status/",
            {"status": DocWorkflow.STATUS_REJECTED},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        document = app.documents.first()
        document.doc_number = "NOW-COMPLETE"
        document.save()

        app.refresh_from_db()
        self.assertEqual(app.status, DocApplication.STATUS_REJECTED)

    def test_update_workflow_status_blocks_pending_to_processing_until_previous_due_date(self):
        app, step1 = self._create_application_and_workflow(document_completed=True, task_count=2)

        response = self.client.post(
            f"/api/customer-applications/{app.id}/workflows/{step1.id}/status/",
            {"status": DocWorkflow.STATUS_COMPLETED},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        step2 = app.workflows.filter(task__step=2).first()
        self.assertIsNotNone(step2)

        blocked = self.client.post(
            f"/api/customer-applications/{app.id}/workflows/{step2.id}/status/",
            {"status": DocWorkflow.STATUS_PROCESSING},
            format="json",
        )
        self.assertEqual(blocked.status_code, 400)
        self.assertIn("system date (GMT+8)", str(blocked.data))

        allowed_rejected = self.client.post(
            f"/api/customer-applications/{app.id}/workflows/{step2.id}/status/",
            {"status": DocWorkflow.STATUS_REJECTED},
            format="json",
        )
        self.assertEqual(allowed_rejected.status_code, 200)

    def test_update_workflow_due_date_updates_application_due_date(self):
        app, step1 = self._create_application_and_workflow(document_completed=True, task_count=2)

        complete_step1 = self.client.post(
            f"/api/customer-applications/{app.id}/workflows/{step1.id}/status/",
            {"status": DocWorkflow.STATUS_COMPLETED},
            format="json",
        )
        self.assertEqual(complete_step1.status_code, 200)

        step2 = app.workflows.filter(task__step=2).first()
        self.assertIsNotNone(step2)

        response = self.client.post(
            f"/api/customer-applications/{app.id}/workflows/{step2.id}/due-date/",
            {"dueDate": "2030-01-20"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        step2.refresh_from_db()
        app.refresh_from_db()
        self.assertEqual(step2.due_date.isoformat(), "2030-01-20")
        self.assertEqual(app.due_date.isoformat(), "2030-01-20")

    def test_rollback_workflow_removes_current_step_and_reopens_previous_step(self):
        app, step1 = self._create_application_and_workflow(document_completed=True, task_count=2)

        complete_step1 = self.client.post(
            f"/api/customer-applications/{app.id}/workflows/{step1.id}/status/",
            {"status": DocWorkflow.STATUS_COMPLETED},
            format="json",
        )
        self.assertEqual(complete_step1.status_code, 200)

        step2 = app.workflows.filter(task__step=2).first()
        self.assertIsNotNone(step2)

        response = self.client.post(
            f"/api/customer-applications/{app.id}/workflows/{step2.id}/rollback/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        app.refresh_from_db()
        step1.refresh_from_db()
        self.assertFalse(app.workflows.filter(id=step2.id).exists())
        self.assertEqual(step1.status, DocWorkflow.STATUS_PENDING)
        self.assertEqual(app.current_workflow.id, step1.id)
        self.assertEqual(app.due_date, step1.due_date)
