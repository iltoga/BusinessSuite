"""Parameterized tests for Document.save() completion logic.

Covers every combination of DocumentType requirement flags
(has_file, has_doc_number, has_expiration_date, has_details) x filled/empty
to ensure the completed field is computed correctly.
"""

from datetime import date

from customer_applications.models import DocApplication, Document
from customers.models import Customer
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from products.models import DocumentType, Product

User = get_user_model()


class DocumentCompletionMixin:
    """Shared setUp for document completion tests."""

    def setUp(self):
        self.user = User.objects.create_user(username="doc-complete-user", password="testpass")
        self.customer = Customer.objects.create(first_name="Doc", last_name="Complete")
        self.product = Product.objects.create(name="Doc Product", code="DOC-COMP")
        self.application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=timezone.now().date(),
            created_by=self.user,
        )

    def _make_doc_type(self, *, has_file=False, has_doc_number=False, has_expiration_date=False, has_details=False):
        # Disable ai_validation to prevent DocumentType.clean() from forcing has_file=True
        return DocumentType.objects.create(
            name=f"DT-f{int(has_file)}n{int(has_doc_number)}e{int(has_expiration_date)}d{int(has_details)}",
            has_file=has_file,
            has_doc_number=has_doc_number,
            has_expiration_date=has_expiration_date,
            has_details=has_details,
            ai_validation=False,
        )

    def _make_document(self, doc_type, *, file=None, doc_number="", expiration_date=None, details=""):
        return Document.objects.create(
            doc_application=self.application,
            doc_type=doc_type,
            file=file or "",
            doc_number=doc_number,
            expiration_date=expiration_date,
            details=details,
            created_by=self.user,
        )

    @staticmethod
    def _dummy_file():
        return SimpleUploadedFile("test.pdf", b"fake-pdf-content", content_type="application/pdf")


class DocumentCompletionSingleFieldTests(DocumentCompletionMixin, TestCase):
    """Test completion when only one requirement flag is set."""

    def test_has_file_only_filled(self):
        dt = self._make_doc_type(has_file=True)
        doc = self._make_document(dt, file=self._dummy_file())
        self.assertTrue(doc.completed)

    def test_has_file_only_empty(self):
        dt = self._make_doc_type(has_file=True)
        doc = self._make_document(dt)
        self.assertFalse(doc.completed)

    def test_has_doc_number_only_filled(self):
        dt = self._make_doc_type(has_doc_number=True)
        doc = self._make_document(dt, doc_number="ABC123")
        self.assertTrue(doc.completed)

    def test_has_doc_number_only_empty(self):
        dt = self._make_doc_type(has_doc_number=True)
        doc = self._make_document(dt)
        self.assertFalse(doc.completed)

    def test_has_expiration_date_only_filled(self):
        dt = self._make_doc_type(has_expiration_date=True)
        doc = self._make_document(dt, expiration_date=date(2027, 1, 1))
        self.assertTrue(doc.completed)

    def test_has_expiration_date_only_empty(self):
        dt = self._make_doc_type(has_expiration_date=True)
        doc = self._make_document(dt)
        self.assertFalse(doc.completed)

    def test_has_details_only_filled(self):
        dt = self._make_doc_type(has_details=True)
        doc = self._make_document(dt, details="Some details")
        self.assertTrue(doc.completed)

    def test_has_details_only_empty(self):
        dt = self._make_doc_type(has_details=True)
        doc = self._make_document(dt)
        self.assertFalse(doc.completed)


class DocumentCompletionMultiFieldTests(DocumentCompletionMixin, TestCase):
    """Test completion when multiple requirement flags are set (all must be filled)."""

    def test_file_and_details_both_filled(self):
        dt = self._make_doc_type(has_file=True, has_details=True)
        doc = self._make_document(dt, file=self._dummy_file(), details="Details")
        self.assertTrue(doc.completed)

    def test_file_and_details_only_file_filled(self):
        """When both file and details required, filling only file is NOT complete."""
        dt = self._make_doc_type(has_file=True, has_details=True)
        doc = self._make_document(dt, file=self._dummy_file())
        self.assertFalse(doc.completed)

    def test_file_and_details_only_details_filled(self):
        """When both file and details required, filling only details is NOT complete."""
        dt = self._make_doc_type(has_file=True, has_details=True)
        doc = self._make_document(dt, details="Details only")
        self.assertFalse(doc.completed)

    def test_file_and_details_neither_filled(self):
        dt = self._make_doc_type(has_file=True, has_details=True)
        doc = self._make_document(dt)
        self.assertFalse(doc.completed)

    def test_all_four_required_all_filled(self):
        dt = self._make_doc_type(has_file=True, has_doc_number=True, has_expiration_date=True, has_details=True)
        doc = self._make_document(
            dt,
            file=self._dummy_file(),
            doc_number="X123",
            expiration_date=date(2027, 6, 15),
            details="All filled",
        )
        self.assertTrue(doc.completed)

    def test_all_four_required_one_missing(self):
        """Missing any single required field should mark document incomplete."""
        dt = self._make_doc_type(has_file=True, has_doc_number=True, has_expiration_date=True, has_details=True)
        # Missing expiration_date
        doc = self._make_document(dt, file=self._dummy_file(), doc_number="X123", details="Partial")
        self.assertFalse(doc.completed)

    def test_file_and_doc_number_required_both_filled(self):
        dt = self._make_doc_type(has_file=True, has_doc_number=True)
        doc = self._make_document(dt, file=self._dummy_file(), doc_number="DOC-001")
        self.assertTrue(doc.completed)

    def test_file_and_doc_number_required_only_number(self):
        dt = self._make_doc_type(has_file=True, has_doc_number=True)
        doc = self._make_document(dt, doc_number="DOC-001")
        self.assertFalse(doc.completed)


class DocumentCompletionNoRequirementsTests(DocumentCompletionMixin, TestCase):
    """Test completion when no requirement flags are set."""

    def test_no_requirements_with_details_is_complete(self):
        dt = self._make_doc_type()
        doc = self._make_document(dt, details="Freeform notes")
        self.assertTrue(doc.completed)

    def test_no_requirements_empty_is_not_complete(self):
        dt = self._make_doc_type()
        doc = self._make_document(dt)
        self.assertFalse(doc.completed)
