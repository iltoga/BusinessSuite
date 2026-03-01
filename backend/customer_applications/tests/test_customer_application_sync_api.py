from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from customer_applications.models import DocApplication, DocWorkflow
from customers.models import Customer
from products.models import Product, Task
from products.models.document_type import DocumentType

User = get_user_model()


class CustomerApplicationSyncApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user("sync-user", "sync@example.com", "pass")
        self.client.force_authenticate(self.user)

        self.customer = Customer.objects.create(first_name="Sync", last_name="Customer")
        self.product = Product.objects.create(
            name="Sync Product",
            code="SYNC-1",
            required_documents="",
        )
        self.task_step_1 = Task.objects.create(
            product=self.product,
            step=1,
            name="Collect docs",
            duration=2,
            duration_is_business_days=False,
            add_task_to_calendar=True,
        )
        self.task_step_2 = Task.objects.create(
            product=self.product,
            step=2,
            name="Final review",
            duration=3,
            duration_is_business_days=False,
            add_task_to_calendar=True,
        )

    def test_create_query_budget_with_many_document_types(self):
        document_types = [
            DocumentType.objects.create(name=f"Perf Doc Type {index}")
            for index in range(1, 13)
        ]
        payload = {
            "customer": self.customer.id,
            "product": self.product.id,
            "docDate": "2026-01-10",
            "dueDate": "2026-01-12",
            "addDeadlinesToCalendar": True,
            "notifyCustomerToo": False,
            "notifyCustomerChannel": None,
            "notes": "Query budget test",
            "documentTypes": [{"id": item.id, "required": True} for item in document_types],
        }

        with CaptureQueriesContext(connection) as captured:
            response = self.client.post("/api/customer-applications/", payload, format="json")

        self.assertEqual(response.status_code, 201)
        query_count = len(captured)
        self.assertLessEqual(
            query_count,
            45,
            f"POST /api/customer-applications/ query budget exceeded: {query_count} queries",
        )

    @patch("customer_applications.tasks.send_due_tomorrow_customer_notifications")
    @patch("customer_applications.tasks.enqueue_sync_application_calendar_task")
    def test_create_is_synchronous_and_queues_calendar_sync(self, sync_task_mock, send_due_mock):
        payload = {
            "customer": self.customer.id,
            "product": self.product.id,
            "docDate": "2026-01-10",
            "dueDate": "2026-01-12",
            "addDeadlinesToCalendar": True,
            "notifyCustomer": False,
            "notifyCustomerChannel": None,
            "notes": "Created sync",
            "documentTypes": [],
        }

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post("/api/customer-applications/", payload, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertIn("id", response.data)
        application_id = response.data["id"]
        self.assertTrue(DocApplication.objects.filter(pk=application_id).exists())
        first_workflow = DocWorkflow.objects.get(doc_application_id=application_id, task__step=1)
        self.assertEqual(first_workflow.due_date, date(2026, 1, 12))

        sync_task_mock.assert_called_once()
        kwargs = sync_task_mock.call_args.kwargs
        self.assertEqual(kwargs["application_id"], application_id)
        self.assertEqual(kwargs["user_id"], self.user.id)
        self.assertEqual(kwargs["action"], "upsert")
        send_due_mock.assert_not_called()

    @patch("customer_applications.tasks.send_due_tomorrow_customer_notifications")
    @patch("customer_applications.tasks.enqueue_sync_application_calendar_task")
    def test_update_is_synchronous_and_queues_calendar_sync_with_previous_due_date(self, sync_task_mock, send_due_mock):
        application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=date(2026, 1, 10),
            due_date=date(2026, 1, 20),
            created_by=self.user,
        )

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.patch(
                f"/api/customer-applications/{application.id}/",
                {"notes": "Updated sync"},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        application.refresh_from_db()
        self.assertEqual(application.notes, "Updated sync")

        sync_task_mock.assert_called_once()
        kwargs = sync_task_mock.call_args.kwargs
        self.assertEqual(kwargs["application_id"], application.id)
        self.assertEqual(kwargs["user_id"], self.user.id)
        self.assertEqual(kwargs["action"], "upsert")
        self.assertEqual(kwargs["previous_due_date"], "2026-01-20")
        send_due_mock.assert_not_called()

    @patch("customer_applications.tasks.enqueue_sync_application_calendar_task")
    def test_advance_workflow_is_synchronous_and_queues_calendar_sync(self, sync_task_mock):
        application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=date(2026, 1, 10),
            due_date=date(2026, 1, 20),
            created_by=self.user,
        )
        current_workflow = DocWorkflow.objects.create(
            doc_application=application,
            task=self.task_step_1,
            start_date=timezone.localdate(),
            due_date=date(2026, 1, 15),
            status=DocWorkflow.STATUS_PENDING,
            created_by=self.user,
        )

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                f"/api/customer-applications/{application.id}/advance-workflow/",
                {},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        current_workflow.refresh_from_db()
        self.assertEqual(current_workflow.status, DocWorkflow.STATUS_COMPLETED)

        sync_task_mock.assert_called_once()
        kwargs = sync_task_mock.call_args.kwargs
        self.assertEqual(kwargs["application_id"], application.id)
        self.assertEqual(kwargs["user_id"], self.user.id)
        self.assertEqual(kwargs["action"], "upsert")
        self.assertEqual(kwargs["previous_due_date"], "2026-01-20")
        self.assertEqual(kwargs["start_date"], "2026-01-15")
