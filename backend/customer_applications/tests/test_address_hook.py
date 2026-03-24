"""Tests for the Address document type hook."""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from customer_applications.hooks.address import AddressHook
from customer_applications.hooks import hook_registry
from customer_applications.models import DocApplication, Document
from customers.models import Customer
from products.models import DocumentType, Product

User = get_user_model()


class AddressHookTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("address-admin", "addressadmin@example.com", "pass")
        self.customer = Customer.objects.create(
            first_name="Address",
            last_name="Tester",
            address_bali="Denpasar, Bali",
        )
        self.product = Product.objects.create(name="Test Product", code="ADDRESS-HOOK-1", required_documents="")
        self.doc_type = DocumentType.objects.create(name="Address", has_details=True)
        self.application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=date(2026, 2, 24),
            created_by=self.user,
        )
        hook_registry.register(AddressHook())

    def test_address_pre_filled_on_creation(self):
        document = Document.objects.create(
            doc_application=self.application,
            doc_type=self.doc_type,
            required=True,
            created_by=self.user,
        )
        
        self.assertEqual(document.details, "Denpasar, Bali")

    def test_customer_address_updated_on_document_details_update(self):
        document = Document.objects.create(
            doc_application=self.application,
            doc_type=self.doc_type,
            required=True,
            created_by=self.user,
        )
        
        # Now update the document details
        document.details = "Ubud, Bali"
        document.save()
        
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.address_bali, "Ubud, Bali")

    def test_customer_address_not_updated_if_details_not_changed(self):
        document = Document.objects.create(
            doc_application=self.application,
            doc_type=self.doc_type,
            required=True,
            created_by=self.user,
        )
        
        # Update something else
        document.required = False
        document.save()
        
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.address_bali, "Denpasar, Bali")
