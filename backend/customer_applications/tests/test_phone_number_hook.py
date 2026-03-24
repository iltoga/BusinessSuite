"""Tests for the Phone Number document type hook."""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from customer_applications.hooks.phone_number import PhoneNumberHook
from customer_applications.hooks import hook_registry
from customer_applications.models import DocApplication, Document
from customers.models import Customer
from products.models import DocumentType, Product

User = get_user_model()


class PhoneNumberHookTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("phone-admin", "phoneadmin@example.com", "pass")
        self.customer = Customer.objects.create(
            first_name="Phone",
            last_name="Tester",
            telephone="+1234567890",
            whatsapp="",
        )
        self.product = Product.objects.create(name="Test Product", code="PHONE-HOOK-1", required_documents="")
        self.doc_type = DocumentType.objects.create(name="Phone Number", has_details=True)
        self.application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=date(2026, 2, 24),
            created_by=self.user,
        )
        hook_registry.register(PhoneNumberHook())

    def test_phone_pre_filled_on_creation_telephone(self):
        document = Document.objects.create(
            doc_application=self.application,
            doc_type=self.doc_type,
            required=True,
            created_by=self.user,
        )
        
        self.assertEqual(document.details, "+1234567890")

    def test_phone_pre_filled_on_creation_whatsapp_fallback(self):
        self.customer.telephone = None
        self.customer.whatsapp = "+0987654321"
        self.customer.save()
        
        document = Document.objects.create(
            doc_application=self.application,
            doc_type=self.doc_type,
            required=True,
            created_by=self.user,
        )
        
        self.assertEqual(document.details, "+0987654321")

    def test_customer_phone_updated_on_document_details_update(self):
        document = Document.objects.create(
            doc_application=self.application,
            doc_type=self.doc_type,
            required=True,
            created_by=self.user,
        )
        
        # Now update the document details
        document.details = "+1122334455"
        document.save()
        
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.telephone, "+1122334455")

    def test_customer_phone_and_whatsapp_updated_on_document_details_update(self):
        self.customer.whatsapp = "+0987654321"
        self.customer.save()
        
        document = Document.objects.create(
            doc_application=self.application,
            doc_type=self.doc_type,
            required=True,
            created_by=self.user,
        )
        
        # Now update the document details
        document.details = "+1122334455"
        document.save()
        
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.telephone, "+1122334455")
        self.assertEqual(self.customer.whatsapp, "+1122334455")
