from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from core.models.country_code import CountryCode
from customer_applications.models import DocApplication, Document
from customers.models import Customer
from products.models import DocumentType, Product


class DocApplicationTestDocumentCompleted(TestCase):
    def setUp(self):
        self.country_code = CountryCode.objects.create(
            country="United States of America", alpha2_code="US", alpha3_code="USA", numeric_code="840"
        )
        self.customer = Customer.objects.create(
            first_name="John",
            last_name="Doe",
            email="john.doe@test.com",
            telephone="1234567890",
            whatsapp="0987654321",
            telegram="1122334455",
            facebook="john.doe",
            instagram="john.doe",
            twitter="john.doe",
            title="Mr.",
            nationality=self.country_code,
            birthdate=date(1990, 1, 1),
            gender="M",
            address_bali="123 Bali Street",
            address_abroad="123 Abroad Street",
            notify_documents_expiration=True,
            notify_by="email",
            notification_sent=False,
        )
        self.doc_type = DocumentType.objects.create(name="Test Doc Type", is_in_required_documents=True)
        self.product = Product.objects.create(name="Test Product", code="TP1", product_type="Type A")
        self.user = User.objects.create_user(username="johndoe", email="john.doe@test.com", password="password123!")
        self.doc_app = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=timezone.now(),
            created_by=self.user,
        )
        self.doc1 = Document.objects.create(
            doc_application=self.doc_app,
            doc_type=self.doc_type,
            required=True,
            created_by=self.user,
        )
        self.doc2 = Document.objects.create(
            doc_application=self.doc_app,
            doc_type=self.doc_type,
            required=True,
            details="Test Document 2",
            created_by=self.user,
        )
        self.doc3 = Document.objects.create(
            doc_application=self.doc_app,
            doc_type=self.doc_type,
            required=False,
            details="Test Document 3",
            created_by=self.user,
        )

    def test_filter_by_document_collection_completed(self):
        completed_docs = DocApplication.objects.filter_by_document_collection_completed()
        self.assertEqual(completed_docs.count(), 0)
        self.assertFalse(self.doc_app.is_document_collection_completed)

        for doc_app in DocApplication.objects.all():
            self.assertEqual(doc_app in completed_docs, doc_app.is_document_collection_completed)

        self.doc1.details = "Test Document 1"
        self.doc1.save()
        self.assertTrue(self.doc1.completed)

        # Force re-evaluation of the queryset after updating self.doc2
        completed_docs = DocApplication.objects.filter_by_document_collection_completed()

        self.assertEqual(completed_docs.count(), 1)
        self.assertTrue(self.doc_app.is_document_collection_completed)
        self.assertEqual(completed_docs.first(), self.doc_app)

        for doc_app in DocApplication.objects.all():
            self.assertEqual(doc_app in completed_docs, doc_app.is_document_collection_completed)
