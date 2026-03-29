"""Tests for document application status when documents are missing."""

from datetime import date, timedelta

from customer_applications.models import DocApplication
from customers.models import Customer
from django.contrib.auth import get_user_model
from django.test import TestCase
from products.models import Product, Task

User = get_user_model()


class DocApplicationStatusWithoutDocumentsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="doc-status-user", password="pw")
        self.customer = Customer.objects.create(first_name="Doc", last_name="Status")

    def test_new_application_is_auto_completed_when_product_has_no_required_and_optional_documents(self):
        product = Product.objects.create(
            name="No Docs Product",
            code="NO-DOCS-1",
            required_documents="",
            optional_documents="",
        )

        application = DocApplication.objects.create(
            customer=self.customer,
            product=product,
            doc_date=date.today(),
            created_by=self.user,
        )

        self.assertEqual(application.status, DocApplication.STATUS_COMPLETED)

    def test_new_application_is_not_auto_completed_when_product_has_only_optional_documents(self):
        product = Product.objects.create(
            name="Optional Docs Product",
            code="OPT-DOCS-1",
            required_documents="",
            optional_documents="Passport",
        )

        application = DocApplication.objects.create(
            customer=self.customer,
            product=product,
            doc_date=date.today(),
            created_by=self.user,
        )

        self.assertEqual(application.status, DocApplication.STATUS_PENDING)

    def test_new_application_is_not_auto_completed_when_product_has_tasks_but_no_documents(self):
        product = Product.objects.create(
            name="Task Only Product",
            code="TASK-ONLY-1",
            required_documents="",
            optional_documents="",
        )
        Task.objects.create(
            product=product,
            step=1,
            name="Start Workflow",
            duration=1,
            duration_is_business_days=False,
        )

        application = DocApplication.objects.create(
            customer=self.customer,
            product=product,
            doc_date=date.today(),
            created_by=self.user,
        )

        self.assertEqual(application.status, DocApplication.STATUS_PENDING)

    def test_due_date_is_cleared_when_product_has_no_tasks(self):
        product = Product.objects.create(
            name="No Task Product",
            code="NO-TASK-1",
            required_documents="Passport",
            optional_documents="",
        )

        explicit_due_date = date.today() + timedelta(days=3)
        application = DocApplication.objects.create(
            customer=self.customer,
            product=product,
            doc_date=date.today(),
            due_date=explicit_due_date,
            created_by=self.user,
        )

        self.assertIsNone(application.due_date)

    def test_due_date_is_kept_when_product_has_tasks(self):
        product = Product.objects.create(
            name="Tasked Product",
            code="TASK-1",
            required_documents="Passport",
            optional_documents="",
        )
        Task.objects.create(
            product=product,
            step=1,
            name="Collect Documents",
            duration=2,
            duration_is_business_days=False,
        )

        application = DocApplication.objects.create(
            customer=self.customer,
            product=product,
            doc_date=date.today(),
            created_by=self.user,
        )

        self.assertIsNotNone(application.due_date)
