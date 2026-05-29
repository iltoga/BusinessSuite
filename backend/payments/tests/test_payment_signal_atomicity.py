"""Tests for payment signal atomicity and paid-invoice application startup."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from customer_applications.models import DocApplication, DocWorkflow
from customers.models import Customer
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from invoices.models import Invoice, InvoiceApplication
from payments.models import Payment
from products.models import Product, Task

User = get_user_model()


class PaymentSignalAtomicityMixin:
    """Shared setUp for signal atomicity tests."""

    def setUp(self):
        self.user = User.objects.create_user(username="atomic-user", password="testpass")
        self.customer = Customer.objects.create(first_name="Atomic", last_name="Test")
        self.product = Product.objects.create(name="Atomic Product", code="ATOM-PROD")
        self.task = Task.objects.create(
            product=self.product,
            step=1,
            name="Start processing",
            duration=1,
            duration_is_business_days=False,
            add_task_to_calendar=True,
        )
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


class PaymentSignalSelectForUpdateTest(PaymentSignalAtomicityMixin, TestCase):
    """Verify that the payment signal uses select_for_update for safe concurrent access."""

    def test_two_sequential_payments_consistent_final_state(self):
        """Two payments created sequentially should produce consistent totals."""
        Payment.objects.create(
            invoice_application=self.invoice_application,
            from_customer=self.customer,
            amount=Decimal("50.00"),
            payment_type=Payment.CASH,
            created_by=self.user,
        )
        Payment.objects.create(
            invoice_application=self.invoice_application,
            from_customer=self.customer,
            amount=Decimal("50.00"),
            payment_type=Payment.WIRE_TRANSFER,
            created_by=self.user,
        )
        self.invoice_application.refresh_from_db()
        self.invoice.refresh_from_db()

        self.assertEqual(self.invoice_application.paid_amount, Decimal("100.00"))
        self.assertEqual(self.invoice_application.status, InvoiceApplication.PAID)
        self.assertEqual(self.invoice.status, Invoice.PAID)

    def test_payment_then_delete_restores_partial(self):
        """Full payment followed by partial delete restores PARTIAL_PAYMENT."""
        p1 = Payment.objects.create(
            invoice_application=self.invoice_application,
            from_customer=self.customer,
            amount=Decimal("60.00"),
            payment_type=Payment.CASH,
            created_by=self.user,
        )
        Payment.objects.create(
            invoice_application=self.invoice_application,
            from_customer=self.customer,
            amount=Decimal("40.00"),
            payment_type=Payment.CASH,
            created_by=self.user,
        )
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.PAID)

        p1.delete()

        self.invoice_application.refresh_from_db()
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice_application.status, InvoiceApplication.PARTIAL_PAYMENT)
        self.assertEqual(self.invoice.status, Invoice.PARTIAL_PAYMENT)

    def test_zero_amount_payment_keeps_pending(self):
        """A zero-amount payment should not change the status from PENDING."""
        Payment.objects.create(
            invoice_application=self.invoice_application,
            from_customer=self.customer,
            amount=Decimal("0.00"),
            payment_type=Payment.CASH,
            created_by=self.user,
        )
        self.invoice_application.refresh_from_db()
        self.invoice.refresh_from_db()

        self.assertEqual(self.invoice_application.status, InvoiceApplication.PENDING)
        self.assertEqual(self.invoice.status, Invoice.PENDING_PAYMENT)


class StartPaidInvoiceApplicationsTest(PaymentSignalAtomicityMixin, TestCase):
    """Verify paid invoices start linked application workflows."""

    def test_fully_paid_starts_step_one_and_does_not_complete_application(self):
        """Application starts processing when invoice is PAID and is not completed."""
        self.application.status = DocApplication.STATUS_PENDING
        self.application.save(skip_status_calculation=True)

        with patch.object(
            DocApplication, "is_document_collection_completed", new_callable=lambda: property(lambda self: True)
        ):
            Payment.objects.create(
                invoice_application=self.invoice_application,
                from_customer=self.customer,
                amount=Decimal("100.00"),
                payment_type=Payment.CASH,
                created_by=self.user,
            )

        self.application.refresh_from_db()
        workflow = DocWorkflow.objects.get(doc_application=self.application, task=self.task)
        self.assertEqual(workflow.status, DocApplication.STATUS_PROCESSING)
        self.assertEqual(self.application.status, DocApplication.STATUS_PROCESSING)
        self.assertNotEqual(self.application.status, DocApplication.STATUS_COMPLETED)

    def test_fully_paid_starts_processing_even_when_docs_are_incomplete(self):
        """Payment starts processing; document completeness does not complete the app."""
        self.application.status = DocApplication.STATUS_PENDING
        self.application.save(skip_status_calculation=True)

        with patch.object(
            DocApplication, "is_document_collection_completed", new_callable=lambda: property(lambda self: False)
        ):
            Payment.objects.create(
                invoice_application=self.invoice_application,
                from_customer=self.customer,
                amount=Decimal("100.00"),
                payment_type=Payment.CASH,
                created_by=self.user,
            )

        self.application.refresh_from_db()
        workflow = DocWorkflow.objects.get(doc_application=self.application, task=self.task)
        self.assertEqual(workflow.status, DocApplication.STATUS_PROCESSING)
        self.assertEqual(self.application.status, DocApplication.STATUS_PROCESSING)

    def test_fully_paid_keeps_rejected_application_rejected(self):
        self.application.status = DocApplication.STATUS_REJECTED
        self.application.save(skip_status_calculation=True)

        Payment.objects.create(
            invoice_application=self.invoice_application,
            from_customer=self.customer,
            amount=Decimal("100.00"),
            payment_type=Payment.CASH,
            created_by=self.user,
        )

        self.application.refresh_from_db()
        self.assertEqual(self.application.status, DocApplication.STATUS_REJECTED)
        self.assertFalse(DocWorkflow.objects.filter(doc_application=self.application, task=self.task).exists())
