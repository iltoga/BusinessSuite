from django.test import TestCase
from django.utils import timezone

from customers.models import Customer
from invoices.models.invoice import Invoice


class InvoiceNumberLogicTestCase(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        Invoice.objects.all().delete()
        self.customer = Customer.objects.create(
            customer_type="person",
            first_name="Test",
            last_name="User",
            active=True,
        )

    def test_invoice_number_starts_at_0001_for_new_year(self):
        next_no = Invoice.get_next_invoice_no_for_year(2026)
        self.assertEqual(next_no, 20260001)

    def test_invoice_number_increments_within_year(self):
        last_invoice = Invoice.objects.create(
            customer=self.customer,
            invoice_no=20260070,
            invoice_date=timezone.datetime(2026, 1, 10).date(),
            due_date=timezone.datetime(2026, 1, 20).date(),
        )

        next_no = Invoice.get_next_invoice_no_for_year(2026)
        self.assertEqual(next_no, 20260071)
        self.assertNotEqual(next_no, last_invoice.invoice_no)

    def test_invoice_number_resets_when_year_advances(self):
        Invoice.objects.create(
            customer=self.customer,
            invoice_no=20251234,
            invoice_date=timezone.datetime(2025, 12, 31).date(),
            due_date=timezone.datetime(2026, 1, 10).date(),
        )

        next_no = Invoice.get_next_invoice_no_for_year(2026)
        self.assertEqual(next_no, 20260001)

    def test_invoice_number_handles_legacy_short_sequence(self):
        Invoice.objects.create(
            customer=self.customer,
            invoice_no=202612,
            invoice_date=timezone.datetime(2026, 2, 1).date(),
            due_date=timezone.datetime(2026, 2, 10).date(),
        )

        next_no = Invoice.get_next_invoice_no_for_year(2026)
        self.assertEqual(next_no, 20260013)
