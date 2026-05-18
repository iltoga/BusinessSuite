"""Query-count regression tests for frontend list endpoints."""

from decimal import Decimal

from customer_applications.models import DocApplication
from customers.models import Customer
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from invoices.models import Invoice, InvoiceApplication
from products.models import Product, ProductCategory


class FrontendListQueryPerformanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.user = user_model.objects.create_superuser(
            username="listperf",
            email="listperf@example.com",
            password="password",
        )
        cls.category = ProductCategory.objects.create(name="Perf Visa", product_type="visa")
        cls.product = Product.objects.create(
            name="Performance Visa",
            code="PERF-VISA",
            product_category=cls.category,
            required_documents="",
            uses_customer_app_workflow=True,
            base_price=Decimal("100.00"),
            retail_price=Decimal("100.00"),
        )
        Product.objects.filter(pk=cls.product.pk).update(uses_customer_app_workflow=True)
        cls.product.refresh_from_db()
        cls.today = timezone.now().date()

        cls.customers = [
            Customer.objects.create(
                customer_type="person",
                first_name=f"Perf{i}",
                last_name="Customer",
                email=f"perf{i}@example.com",
                active=True,
            )
            for i in range(5)
        ]
        cls.applications = [
            DocApplication.objects.create(
                customer=customer,
                product=cls.product,
                doc_date=cls.today,
                created_by=cls.user,
            )
            for customer in cls.customers
        ]

        for index, application in enumerate(cls.applications):
            invoice = Invoice.objects.create(
                customer=application.customer,
                invoice_date=cls.today,
                due_date=cls.today,
                total_amount=Decimal("100.00"),
                created_by=cls.user,
            )
            InvoiceApplication.objects.create(
                invoice=invoice,
                customer_application=application,
                product=cls.product,
                quantity=1,
                amount=Decimal("100.00"),
                sort_order=index,
            )

    def setUp(self):
        self.client.force_login(self.user)

    def test_customer_application_list_query_count_does_not_scale_with_rows(self):
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(reverse("customer-applications-list"), {"page_size": 5})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["results"]), 5)
        self.assertLessEqual(len(captured), 12)

    def test_invoice_list_query_count_does_not_scale_with_lines(self):
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(reverse("invoices-list"), {"page_size": 5})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["results"]), 5)
        self.assertTrue(payload["results"][0]["invoiceApplications"])
        self.assertLessEqual(len(captured), 12)
