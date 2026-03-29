"""Regression tests for application document-date synchronization APIs."""

import json
from datetime import date

from customer_applications.models import DocApplication, DocWorkflow
from customers.models import Customer
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from products.models import Product, Task


class ApplicationDocDateSyncApiTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser(
            username="application-doc-date-admin",
            email="application-doc-date@example.com",
            password="password",
        )
        self.client.force_login(self.user)

        self.customer = Customer.objects.create(
            customer_type="person",
            first_name="Application",
            last_name="Tester",
            active=True,
        )
        self.product = Product.objects.create(
            name="Visa Extension",
            code="VX-1",
            product_type="visa",
        )
        self.task = Task.objects.create(
            product=self.product,
            step=1,
            name="Biometrics",
            duration=2,
            duration_is_business_days=False,
            add_task_to_calendar=True,
        )

    def _create_application_with_step_one(self, *, workflow_status: str = DocApplication.STATUS_PENDING):
        application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=date(2026, 3, 9),
            created_by=self.user,
        )
        workflow = DocWorkflow.objects.create(
            doc_application=application,
            task=self.task,
            start_date=application.doc_date,
            due_date=application.due_date,
            status=workflow_status,
            created_by=self.user,
        )
        return application, workflow

    def test_create_sets_step_one_start_date_to_application_date(self):
        response = self.client.post(
            reverse("customer-applications-list"),
            data=json.dumps(
                {
                    "customer": self.customer.id,
                    "product": self.product.id,
                    "doc_date": "2026-03-09",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        application = DocApplication.objects.get(pk=response.json()["id"])
        workflow = application.workflows.get(task__step=1)

        self.assertEqual(workflow.start_date, application.doc_date)
        self.assertEqual(workflow.due_date, application.due_date)

    def test_partial_update_recalculates_step_one_and_application_due_date(self):
        application, workflow = self._create_application_with_step_one()

        response = self.client.patch(
            reverse("customer-applications-detail", kwargs={"pk": application.pk}),
            data=json.dumps({"doc_date": "2026-03-13"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        application.refresh_from_db()
        workflow.refresh_from_db()

        self.assertEqual(application.doc_date, date(2026, 3, 13))
        self.assertEqual(application.due_date, date(2026, 3, 15))
        self.assertEqual(workflow.start_date, date(2026, 3, 13))
        self.assertEqual(workflow.due_date, date(2026, 3, 15))

    def test_partial_update_blocks_doc_date_change_after_step_one_completed(self):
        application, workflow = self._create_application_with_step_one(workflow_status=DocApplication.STATUS_COMPLETED)

        response = self.client.patch(
            reverse("customer-applications-detail", kwargs={"pk": application.pk}),
            data=json.dumps({"doc_date": "2026-03-13"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "Application submission date cannot be changed after step 1 is completed.",
            json.dumps(response.json()),
        )

        application.refresh_from_db()
        workflow.refresh_from_db()
        self.assertEqual(application.doc_date, date(2026, 3, 9))
        self.assertEqual(workflow.start_date, date(2026, 3, 9))

    def test_compute_doc_workflow_due_date_returns_camelcase_payload(self):
        response = self.client.get(
            reverse(
                "api-compute-docworkflow-due-date",
                kwargs={"task_id": self.task.id, "start_date": "2026-03-09"},
            )
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()["data"]
        self.assertEqual(body["dueDate"], "2026-03-11")
        self.assertNotIn("due_date", body)
