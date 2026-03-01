from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from customer_applications.models import DocApplication
from customers.models import Customer
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from invoices.models import Invoice, InvoiceApplication
from payments.models import Payment
from products.models import Product

User = get_user_model()


class PaymentStatusSignalTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="payment-signal-user", password="testpass")
        self.customer = Customer.objects.create(first_name="Pay", last_name="Signal")
        self.product = Product.objects.create(name="Payment Product", code="PAY-SIGNAL-PROD")
        self.application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=timezone.now().date(),
            created_by=self.user,
        )
        self.invoice = Invoice.objects.create(
            customer=self.customer,
            invoice_date=timezone.now().date(),
            due_date=timezone.now().date() + timedelta(days=10),
            sent=True,
            created_by=self.user,
        )
        self.invoice_application = InvoiceApplication.objects.create(
            invoice=self.invoice,
            customer_application=self.application,
            amount=Decimal("100.00"),
        )
        self.invoice.save()
        self.invoice.refresh_from_db()

    def test_payment_create_updates_invoice_application_and_invoice_status(self):
        self.assertEqual(self.invoice_application.status, InvoiceApplication.PENDING)
        self.assertEqual(self.invoice.status, Invoice.PENDING_PAYMENT)

        Payment.objects.create(
            invoice_application=self.invoice_application,
            from_customer=self.customer,
            amount=Decimal("40.00"),
            payment_type=Payment.CASH,
            created_by=self.user,
        )

        self.invoice_application.refresh_from_db()
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice_application.status, InvoiceApplication.PARTIAL_PAYMENT)
        self.assertEqual(self.invoice.status, Invoice.PARTIAL_PAYMENT)

    def test_payment_create_skips_redundant_status_saves_when_unchanged(self):
        Payment.objects.create(
            invoice_application=self.invoice_application,
            from_customer=self.customer,
            amount=Decimal("40.00"),
            payment_type=Payment.CASH,
            created_by=self.user,
        )
        self.invoice_application.refresh_from_db()
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice_application.status, InvoiceApplication.PARTIAL_PAYMENT)
        self.assertEqual(self.invoice.status, Invoice.PARTIAL_PAYMENT)

        with patch.object(
            InvoiceApplication, "save", autospec=True, wraps=InvoiceApplication.save
        ) as inv_app_save, patch.object(
            Invoice,
            "save",
            autospec=True,
            wraps=Invoice.save,
        ) as invoice_save:
            Payment.objects.create(
                invoice_application=self.invoice_application,
                from_customer=self.customer,
                amount=Decimal("10.00"),
                payment_type=Payment.CASH,
                created_by=self.user,
            )

        self.assertEqual(inv_app_save.call_count, 0)
        self.assertEqual(invoice_save.call_count, 0)

    def test_payment_delete_recomputes_statuses(self):
        payment = Payment.objects.create(
            invoice_application=self.invoice_application,
            from_customer=self.customer,
            amount=Decimal("100.00"),
            payment_type=Payment.CASH,
            created_by=self.user,
        )

        self.invoice_application.refresh_from_db()
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice_application.status, InvoiceApplication.PAID)
        self.assertEqual(self.invoice.status, Invoice.PAID)

        payment.delete()

        self.invoice_application.refresh_from_db()
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice_application.status, InvoiceApplication.PENDING)
        self.assertEqual(self.invoice.status, Invoice.PENDING_PAYMENT)
