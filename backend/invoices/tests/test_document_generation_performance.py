"""Performance tests for invoice document generation."""

from datetime import timedelta
from decimal import Decimal

from customers.models import Customer
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from invoices.models import Invoice, InvoiceApplication
from invoices.services.InvoiceService import InvoiceService
from payments.models import Payment
from products.models import Product

User = get_user_model()


class InvoiceDocumentGenerationPerformanceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="invoice-doc-perf", password="testpass")
        self.customer = Customer.objects.create(first_name="Batch", last_name="Perf")
        self.product = Product.objects.create(
            name="Visa Service",
            code="VISA-SVC",
            product_type="visa",
            description="Main service",
        )
        self.today = timezone.localdate()

    def _create_partially_paid_invoice(self, sequence: int) -> Invoice:
        invoice = Invoice.objects.create(
            customer=self.customer,
            invoice_date=self.today - timedelta(days=sequence + 10),
            due_date=self.today + timedelta(days=10),
            sent=True,
            created_by=self.user,
            updated_by=self.user,
        )

        for offset in range(2):
            invoice_application = InvoiceApplication.objects.create(
                invoice=invoice,
                product=self.product,
                amount=Decimal("100.00") + Decimal(str(offset * 25)),
            )
            Payment.objects.create(
                invoice_application=invoice_application,
                from_customer=self.customer,
                payment_date=invoice.invoice_date + timedelta(days=offset + 1),
                amount=Decimal("25.00"),
                created_by=self.user,
                updated_by=self.user,
            )

        invoice.refresh_from_db()
        return invoice

    def _render_invoice_payloads(self, queryset):
        rendered = []
        for invoice in queryset.order_by("id"):
            service = InvoiceService(invoice)
            if invoice.total_paid_amount == 0 or invoice.is_payment_complete:
                rendered.append(service.generate_invoice_data())
            else:
                rendered.append(service.generate_partial_invoice_data())
        return rendered

    def test_document_generation_queryset_materially_reduces_queries_for_batches(self):
        invoices = [self._create_partially_paid_invoice(index) for index in range(5)]
        invoice_ids = [invoice.id for invoice in invoices]

        with CaptureQueriesContext(connection) as legacy_queries:
            legacy_payloads = self._render_invoice_payloads(Invoice.objects.filter(id__in=invoice_ids))

        with CaptureQueriesContext(connection) as optimized_queries:
            optimized_payloads = self._render_invoice_payloads(
                Invoice.objects.for_document_generation().filter(id__in=invoice_ids)
            )

        self.assertEqual(len(legacy_payloads), len(optimized_payloads))
        self.assertGreater(len(legacy_queries), len(optimized_queries))
        self.assertLessEqual(len(optimized_queries), 4)
