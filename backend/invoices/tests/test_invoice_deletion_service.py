from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from customers.models import Customer
from customer_applications.models import DocApplication
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from invoices.models import Invoice, InvoiceApplication
from invoices.services.invoice_deletion import bulk_delete_invoices, build_invoice_delete_preview, force_delete_invoice
from payments.models import Payment
from products.models import Product, ProductCategory

User = get_user_model()


class InvoiceDeletionServiceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="invoice-delete-user", password="testpass")
        self.customer = Customer.objects.create(first_name="Delete", last_name="Case")
        self.category = ProductCategory.objects.create(name="Deletion Test", product_type="other")
        self.product = Product.objects.create(
            name="Deletion Service",
            code="DEL-SVC",
            product_category=self.category,
            base_price=Decimal("100.00"),
            retail_price=Decimal("100.00"),
        )

    def _create_invoice_bundle(self, *, paid: bool, amount: Decimal = Decimal("100.00")):
        invoice = Invoice.objects.create(
            customer=self.customer,
            invoice_date=timezone.localdate() - timedelta(days=7),
            due_date=timezone.localdate() + timedelta(days=7),
            sent=True,
            created_by=self.user,
            updated_by=self.user,
        )
        doc_application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=timezone.localdate() - timedelta(days=1),
            created_by=self.user,
            updated_by=self.user,
        )
        invoice_application = InvoiceApplication.objects.create(
            invoice=invoice,
            product=self.product,
            customer_application=doc_application,
            amount=amount,
        )

        if paid:
            with patch("core.services.invoice_service.sync_paid_invoice_applications"):
                Payment.objects.create(
                    invoice_application=invoice_application,
                    from_customer=self.customer,
                    payment_date=timezone.localdate(),
                    amount=amount,
                    created_by=self.user,
                    updated_by=self.user,
                )
            invoice.refresh_from_db()
        else:
            Invoice.objects.filter(pk=invoice.pk).update(
                total_amount=amount,
                status=Invoice.PENDING_PAYMENT,
                sent=True,
            )
            invoice.refresh_from_db()

        return invoice, invoice_application, doc_application

    def test_build_invoice_delete_preview_counts_related_records(self):
        invoice, _, _ = self._create_invoice_bundle(paid=True)

        preview = build_invoice_delete_preview(invoice)

        self.assertEqual(preview.invoice_applications_count, 1)
        self.assertEqual(preview.customer_applications_count, 1)
        self.assertEqual(preview.payments_count, 1)

    def test_force_delete_invoice_deletes_related_doc_applications_when_requested(self):
        invoice, _, doc_application = self._create_invoice_bundle(paid=True)

        result = force_delete_invoice(invoice, delete_customer_apps=True)

        self.assertEqual(result["invoice_applications_count"], 1)
        self.assertEqual(result["customer_applications_count"], 1)
        self.assertEqual(result["payments_count"], 1)
        self.assertEqual(result["deleted_customer_applications"], 1)
        self.assertFalse(Invoice.objects.filter(pk=invoice.pk).exists())
        self.assertFalse(DocApplication.objects.filter(pk=doc_application.pk).exists())
        self.assertFalse(Payment.objects.filter(invoice_application__invoice_id=invoice.pk).exists())

    def test_bulk_delete_invoices_respects_hide_paid_and_deletes_linked_doc_applications(self):
        paid_invoice, _, paid_doc_application = self._create_invoice_bundle(paid=True)
        unpaid_invoice, _, unpaid_doc_application = self._create_invoice_bundle(paid=False)

        result = bulk_delete_invoices(hide_paid=True, delete_customer_apps=True)

        self.assertEqual(result["deleted_invoices"], 1)
        self.assertEqual(result["deleted_customer_applications"], 1)
        self.assertTrue(Invoice.objects.filter(pk=paid_invoice.pk).exists())
        self.assertFalse(Invoice.objects.filter(pk=unpaid_invoice.pk).exists())
        self.assertTrue(DocApplication.objects.filter(pk=paid_doc_application.pk).exists())
        self.assertFalse(DocApplication.objects.filter(pk=unpaid_doc_application.pk).exists())
