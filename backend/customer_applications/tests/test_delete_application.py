from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from customer_applications.models import DocApplication
from customers.models import Customer
from invoices.models.invoice import Invoice, InvoiceApplication
from products.models import Product

User = get_user_model()


class ApplicationDeletionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user("user", "user@example.com", "pass")
        self.superuser = User.objects.create_superuser("admin", "admin@example.com", "pass")

        self.customer = Customer.objects.create(first_name="Test", last_name="User")
        self.product = Product.objects.create(name="TestProd", code="TP-1")

    def _create_application_with_invoice(self):
        app = DocApplication.objects.create(
            customer=self.customer, product=self.product, doc_date=date(2026, 1, 1), created_by=self.superuser
        )
        invoice = Invoice.objects.create(
            customer=self.customer, due_date=date(2026, 2, 1), invoice_date=date(2026, 1, 1)
        )
        InvoiceApplication.objects.create(invoice=invoice, customer_application=app, amount=100)
        return app, invoice

    def test_non_superuser_cannot_delete_application_with_invoice_via_api(self):
        app, invoice = self._create_application_with_invoice()
        self.client.force_authenticate(self.user)
        url = f"/api/customer-applications/{app.id}/"
        resp = self.client.delete(url)
        self.assertEqual(resp.status_code, 400)  # deletion blocked, message returned
        self.assertTrue(DocApplication.objects.filter(pk=app.pk).exists())
        self.assertTrue(Invoice.objects.filter(pk=invoice.pk).exists())

    def test_superuser_can_delete_application_and_cascade_delete_invoice_via_api(self):
        app, invoice = self._create_application_with_invoice()
        self.client.force_authenticate(self.superuser)
        url = f"/api/customer-applications/{app.id}/?deleteInvoices=true"
        resp = self.client.delete(url)
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(DocApplication.objects.filter(pk=app.pk).exists())
        self.assertFalse(Invoice.objects.filter(pk=invoice.pk).exists())

    def test_superuser_deleting_application_updates_invoice_with_other_apps(self):
        # Invoice with two applications: deleting one app should keep invoice and recalc
        app1, invoice = self._create_application_with_invoice()
        app2 = DocApplication.objects.create(
            customer=self.customer, product=self.product, doc_date="2026-01-02", created_by=self.superuser
        )
        InvoiceApplication.objects.create(invoice=invoice, customer_application=app2, amount=50)

        self.client.force_authenticate(self.superuser)
        url = f"/api/customer-applications/{app1.id}/?deleteInvoices=true"
        resp = self.client.delete(url)
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(DocApplication.objects.filter(pk=app1.pk).exists())
        # invoice should still exist and total_amount should have been recalculated to 50
        invoice.refresh_from_db()
        self.assertEqual(invoice.total_amount, 50)
