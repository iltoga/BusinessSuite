"""Tests for the stay permit submission window service."""

from datetime import date

from customer_applications.models import DocApplication, Document
from customer_applications.services.stay_permit_submission_window_service import StayPermitSubmissionWindowService
from customers.models import Customer
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from products.models import DocumentType, Product

User = get_user_model()


class StayPermitSubmissionWindowServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("stay-window-user", "stay-window@example.com", "pass")
        self.customer = Customer.objects.create(first_name="Stay", last_name="Window")
        self.product = Product.objects.create(
            name="Stay Permit Product",
            code="SPW-1",
            product_type="visa",
            required_documents="ITAS, Passport",
            optional_documents="KITAS",
            application_window_days=30,
        )
        self.other_product = Product.objects.create(
            name="Other Product",
            code="SPW-2",
            product_type="other",
            required_documents="Passport",
        )
        self.itas = DocumentType.objects.create(
            name="ITAS", is_stay_permit=True, has_expiration_date=True, has_file=True
        )
        self.kitas = DocumentType.objects.create(
            name="KITAS", is_stay_permit=True, has_expiration_date=True, has_file=True
        )
        self.passport = DocumentType.objects.create(name="Passport", has_expiration_date=True, has_file=True)
        self.service = StayPermitSubmissionWindowService()
        self.application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=date(2026, 2, 1),
            created_by=self.user,
        )

    def _create_stay_permit_document(self, *, doc_type: DocumentType, expiration: date) -> Document:
        return Document.objects.create(
            doc_application=self.application,
            doc_type=doc_type,
            expiration_date=expiration,
            required=True,
            created_by=self.user,
            updated_by=self.user,
        )

    def test_split_document_names_ignores_blanks(self):
        self.assertEqual(
            self.service._split_document_names(" ITAS, , Passport ,, KITAS "),
            {"ITAS", "Passport", "KITAS"},
        )
        self.assertEqual(self.service._split_document_names(None), set())
        self.assertEqual(self.service._split_document_names(""), set())

    def test_stay_permit_document_names_for_product_filters_non_stay_permit_types(self):
        self.assertEqual(
            self.service.stay_permit_document_names_for_product(self.product),
            {"ITAS", "KITAS"},
        )
        self.assertTrue(self.service.product_requires_submission_window(self.product))
        self.assertFalse(self.service.product_requires_submission_window(self.other_product))

    def test_get_submission_window_uses_earliest_stay_permit_expiration(self):
        self._create_stay_permit_document(doc_type=self.itas, expiration=date(2026, 4, 1))
        self._create_stay_permit_document(doc_type=self.kitas, expiration=date(2026, 3, 20))
        self._create_stay_permit_document(doc_type=self.passport, expiration=date(2027, 1, 1))

        window = self.service.get_submission_window(product=self.product, application=self.application)

        self.assertIsNotNone(window)
        self.assertEqual(window.first_date, date(2026, 2, 18))
        self.assertEqual(window.last_date, date(2026, 3, 20))

    def test_validate_doc_date_rejects_dates_outside_window(self):
        self._create_stay_permit_document(doc_type=self.itas, expiration=date(2026, 4, 1))

        self.service.validate_doc_date(
            product=self.product,
            doc_date=date(2026, 3, 15),
            application=self.application,
        )

        with self.assertRaises(ValidationError) as ctx:
            self.service.validate_doc_date(
                product=self.product,
                doc_date=date(2026, 2, 1),
                application=self.application,
            )

        self.assertIn("must be between 2026-03-02 and 2026-04-01", str(ctx.exception))

    def test_resolve_submission_date_prefers_preferred_date_inside_window(self):
        self._create_stay_permit_document(doc_type=self.itas, expiration=date(2026, 4, 1))

        self.assertEqual(
            self.service.resolve_submission_date(
                product=self.product,
                application=self.application,
                preferred_date=date(2026, 3, 10),
            ),
            date(2026, 3, 10),
        )
        self.assertEqual(
            self.service.resolve_submission_date(
                product=self.product,
                application=self.application,
                preferred_date=date(2026, 2, 1),
            ),
            date(2026, 3, 2),
        )
