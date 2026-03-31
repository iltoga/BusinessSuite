"""Regression tests for the letters app service behavior."""

from datetime import date
from tempfile import TemporaryDirectory

from core.models import CountryCode
from customers.models import Customer
from django.test import TestCase, override_settings

from .services.LetterService import LetterService


class LetterServiceTests(TestCase):
    def setUp(self):
        self.country = CountryCode.objects.create(alpha3_code="IDN", country="Indonesia", country_idn="Indonesia")
        self.customer = Customer.objects.create(
            first_name="Letter",
            last_name="Tester",
            nationality=self.country,
            birthdate=date(1990, 1, 2),
            passport_number="P1234567",
            passport_expiration_date=date(2030, 12, 31),
            address_bali="Line 1\nLine 2",
            notify_by="Email",
        )

    def test_generate_letter_data_normalizes_overrides_and_address_lines(self):
        service = LetterService(self.customer)

        data = service.generate_letter_data(
            {
                "visa_type": "voa",
                "address_bali": "Override 1\nOverride 2",
                "country": "IDN",
            }
        )

        self.assertEqual(data["visa_type"], "VOA")
        self.assertEqual(data["country"], "Indonesia")
        self.assertEqual(data["address_bali"], "Override 1\nOverride 2")
        self.assertEqual(data["address_bali_line_1"], "Override 1")
        self.assertEqual(data["address_bali_line_2"], "Override 2")

    def test_generate_letter_document_raises_for_missing_template(self):
        service = LetterService(self.customer, template_name="missing-template.docx")

        with TemporaryDirectory() as static_root:
            with override_settings(STATIC_SOURCE_ROOT=static_root):
                with self.assertRaises(FileNotFoundError):
                    service.generate_letter_document(service.generate_letter_data())
