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


class InvoiceApplicationPaymentStatusTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="status-user", password="testpass")
        self.customer = Customer.objects.create(first_name="Status", last_name="Tester")
        self.product = Product.objects.create(name="Status Product", code="STATUS-PROD")
        self.application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=timezone.now().date(),
            created_by=self.user,
        )

    def _create_invoice_application(self, due_date):
        invoice = Invoice.objects.create(
            customer=self.customer,
            invoice_date=timezone.now().date(),
            due_date=due_date,
            created_by=self.user,
        )
        return InvoiceApplication.objects.create(
            invoice=invoice,
            customer_application=self.application,
            amount=Decimal("100.00"),
        )

    def test_unpaid_future_due_date_is_pending(self):
        inv_app = self._create_invoice_application(due_date=timezone.now().date() + timedelta(days=3))

        self.assertEqual(inv_app.status, InvoiceApplication.PENDING)

    def test_unpaid_past_due_date_is_overdue(self):
        inv_app = self._create_invoice_application(due_date=timezone.now().date() - timedelta(days=1))

        self.assertEqual(inv_app.status, InvoiceApplication.OVERDUE)

    def test_partial_and_full_payment_status_transitions(self):
        inv_app = self._create_invoice_application(due_date=timezone.now().date() + timedelta(days=7))

        Payment.objects.create(
            invoice_application=inv_app,
            from_customer=self.customer,
            payment_date=timezone.now().date(),
            amount=Decimal("40.00"),
            payment_type=Payment.CASH,
            created_by=self.user,
        )
        inv_app.refresh_from_db()
        self.assertEqual(inv_app.status, InvoiceApplication.PARTIAL_PAYMENT)

        Payment.objects.create(
            invoice_application=inv_app,
            from_customer=self.customer,
            payment_date=timezone.now().date(),
            amount=Decimal("60.00"),
            payment_type=Payment.CASH,
            created_by=self.user,
        )
        inv_app.refresh_from_db()
        self.assertEqual(inv_app.status, InvoiceApplication.PAID)


class InvoiceStatusOrderingTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="invoice-status-user", password="testpass")
        self.customer = Customer.objects.create(first_name="Invoice", last_name="Status")
        self.product = Product.objects.create(name="Invoice Status Product", code="INV-STATUS-PROD")
        self.application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=timezone.now().date(),
            created_by=self.user,
        )

    def test_unpaid_sent_past_due_invoice_is_overdue(self):
        invoice = Invoice.objects.create(
            customer=self.customer,
            invoice_date=timezone.now().date() - timedelta(days=10),
            due_date=timezone.now().date() - timedelta(days=1),
            sent=True,
            created_by=self.user,
        )
        InvoiceApplication.objects.create(
            invoice=invoice,
            customer_application=self.application,
            amount=Decimal("100.00"),
        )
        invoice.save()
        invoice.refresh_from_db()

        self.assertEqual(invoice.status, Invoice.OVERDUE)

    def test_unpaid_unsent_past_due_invoice_is_overdue(self):
        invoice = Invoice.objects.create(
            customer=self.customer,
            invoice_date=timezone.now().date() - timedelta(days=10),
            due_date=timezone.now().date() - timedelta(days=1),
            sent=False,
            created_by=self.user,
        )
        InvoiceApplication.objects.create(
            invoice=invoice,
            customer_application=self.application,
            amount=Decimal("100.00"),
        )
        invoice.save()
        invoice.refresh_from_db()

        self.assertEqual(invoice.status, Invoice.OVERDUE)
