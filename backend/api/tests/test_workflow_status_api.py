from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from customer_applications.models import DocApplication, Document
from customer_applications.models.doc_workflow import DocWorkflow
from customers.models import Customer
from products.models import Product
from products.models.document_type import DocumentType


User = get_user_model()


class WorkflowStatusApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("workflow-status-admin", "workflowstatus@example.com", "pass")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.customer = Customer.objects.create(first_name="Workflow", last_name="Tester")
        self.doc_type = DocumentType.objects.create(name="Passport", has_doc_number=True)

    def _create_application_and_workflow(self, *, document_completed: bool):
        product = Product.objects.create(
            name="Workflow Status Product",
            code=f"WSP-{1 if document_completed else 0}",
            product_type="visa",
            required_documents="Passport",
        )
        task = product.tasks.create(
            step=1,
            name="Biometrics",
            duration=1,
            duration_is_business_days=True,
            last_step=True,
        )
        app = DocApplication.objects.create(
            customer=self.customer,
            product=product,
            doc_date=timezone.now().date(),
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
            start_date=timezone.now().date(),
            task=task,
            doc_application=app,
            created_by=self.user,
            status=DocWorkflow.STATUS_PENDING,
        )
        workflow.due_date = workflow.calculate_workflow_due_date()
        workflow.save()
        return app, workflow

    def test_update_workflow_status_allows_completed_with_incomplete_documents(self):
        app, workflow = self._create_application_and_workflow(document_completed=False)

        response = self.client.post(
            f"/api/customer-applications/{app.id}/workflows/{workflow.id}/status/",
            {"status": DocWorkflow.STATUS_COMPLETED},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        workflow.refresh_from_db()
        app.refresh_from_db()
        self.assertEqual(workflow.status, DocWorkflow.STATUS_COMPLETED)
        self.assertEqual(app.status, DocApplication.STATUS_PENDING)
        self.assertFalse(app.is_document_collection_completed)

    def test_update_workflow_status_sets_application_completed_when_documents_are_complete(self):
        app, workflow = self._create_application_and_workflow(document_completed=True)

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
        self.assertTrue(app.is_document_collection_completed)
