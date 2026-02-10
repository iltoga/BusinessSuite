from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from core.services.invoice_service import create_invoice
from customers.models import Customer
from invoices.models import Invoice

User = get_user_model()


class CreateInvoiceDuplicateNoTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.customer = Customer.objects.create(customer_type="person", first_name="Alice", last_name="Test")

    def test_create_invoice_with_duplicate_invoice_no_gets_new_number(self):
        # Arrange: create an existing invoice with a specific invoice_no
        invoice_date = timezone.now().date()
        year_prefix = invoice_date.year
        existing_no = int(f"{year_prefix}10")
        Invoice.objects.create(
            customer=self.customer,
            invoice_no=existing_no,
            invoice_date=invoice_date,
            due_date=invoice_date,
            created_by=self.user,
        )

        data = {
            "customer": self.customer,
            "invoice_no": existing_no,  # duplicate
            "invoice_date": invoice_date,
            "due_date": invoice_date,
            "notes": "Duplicate test",
            "sent": False,
            "invoice_applications": [],
        }

        # Act
        invoice = create_invoice(data=data, user=self.user)

        # Assert: created invoice has a different invoice_no (not duplicate)
        self.assertNotEqual(invoice.invoice_no, existing_no)
        self.assertTrue(Invoice.objects.filter(invoice_no=invoice.invoice_no).exists())
