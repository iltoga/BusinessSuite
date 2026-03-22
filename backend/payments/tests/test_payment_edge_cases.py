"""Tests for payment edge cases: overpayment, negative amounts, and signal atomicity."""

from datetime import timedelta
from decimal import Decimal

from customer_applications.models import DocApplication
from customers.models import Customer
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from invoices.models import Invoice, InvoiceApplication
from payments.models import Payment
from products.models import Product

User = get_user_model()


class PaymentEdgeCasesMixin:
    """Shared setUp for payment edge case tests."""

    def setUp(self):
        self.user = User.objects.create_user(username="edge-user", password="testpass")
        self.customer = Customer.objects.create(first_name="Edge", last_name="Case")
        self.product = Product.objects.create(name="Edge Product", code="EDGE-PROD")
        self.application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=timezone.now().date(),
            created_by=self.user,
        )
        self.invoice = Invoice.objects.create(
            customer=self.customer,
            invoice_date=timezone.now().date(),
            due_date=timezone.now().date() + timedelta(days=30),
            sent=True,
            created_by=self.user,
        )
        self.invoice_application = InvoiceApplication.objects.create(
            invoice=self.invoice,
            product=self.product,
            customer_application=self.application,
            amount=Decimal("100.00"),
        )
        self.invoice.save()
        self.invoice.refresh_from_db()


class OverpaymentTest(PaymentEdgeCasesMixin, TestCase):
    """Verify that overpayment sets OVERPAID status instead of raising ValueError."""

    def test_overpayment_sets_overpaid_status(self):
        """Creating a payment that exceeds the invoice total should mark it OVERPAID."""
        Payment.objects.create(
            invoice_application=self.invoice_application,
            from_customer=self.customer,
            amount=Decimal("150.00"),
            payment_type=Payment.CASH,
            created_by=self.user,
        )

        self.invoice.refresh_from_db()
        self.invoice_application.refresh_from_db()

        self.assertEqual(self.invoice.status, Invoice.OVERPAID)

    def test_exact_payment_sets_paid_status(self):
        """A payment exactly matching the total should mark the invoice as PAID."""
        Payment.objects.create(
            invoice_application=self.invoice_application,
            from_customer=self.customer,
            amount=Decimal("100.00"),
            payment_type=Payment.CASH,
            created_by=self.user,
        )

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.PAID)

    def test_overpayment_then_delete_restores_status(self):
        """Deleting the overpayment should restore the invoice to the correct status."""
        payment = Payment.objects.create(
            invoice_application=self.invoice_application,
            from_customer=self.customer,
            amount=Decimal("200.00"),
            payment_type=Payment.CASH,
            created_by=self.user,
        )

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.OVERPAID)

        payment.delete()

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.PENDING_PAYMENT)


class PartialPaymentFlowTest(PaymentEdgeCasesMixin, TestCase):
    """Test partial → full → over payment transitions."""

    def test_partial_then_full_payment(self):
        """Partial payment followed by a second payment to complete the total."""
        Payment.objects.create(
            invoice_application=self.invoice_application,
            from_customer=self.customer,
            amount=Decimal("40.00"),
            payment_type=Payment.CASH,
            created_by=self.user,
        )
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.PARTIAL_PAYMENT)

        Payment.objects.create(
            invoice_application=self.invoice_application,
            from_customer=self.customer,
            amount=Decimal("60.00"),
            payment_type=Payment.WIRE_TRANSFER,
            created_by=self.user,
        )
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.PAID)

    def test_multiple_small_payments_then_overpay(self):
        """Multiple small payments that cumulatively exceed the total."""
        for _ in range(3):
            Payment.objects.create(
                invoice_application=self.invoice_application,
                from_customer=self.customer,
                amount=Decimal("40.00"),
                payment_type=Payment.CASH,
                created_by=self.user,
            )

        self.invoice.refresh_from_db()
        # 3 x 40 = 120 > 100 → overpaid
        self.assertEqual(self.invoice.status, Invoice.OVERPAID)


class PaymentDeletionCascadeTest(PaymentEdgeCasesMixin, TestCase):
    """Test that payment signal handles cascaded deletes gracefully."""

    def test_invoice_application_delete_does_not_crash_signal(self):
        """Deleting an invoice application (which cascades to payments) should not crash."""
        Payment.objects.create(
            invoice_application=self.invoice_application,
            from_customer=self.customer,
            amount=Decimal("50.00"),
            payment_type=Payment.CASH,
            created_by=self.user,
        )
        # Deleting the invoice (force) cascades to invoice_application and payments.
        # The signal should handle the missing invoice_application gracefully.
        self.invoice.delete(force=True)

        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(InvoiceApplication.objects.count(), 0)
