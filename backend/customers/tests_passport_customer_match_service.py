"""Tests for the passport-to-customer matching service."""

"""Tests for the passport-to-customer matching service."""

from customers.models import Customer
from customers.services import PassportCustomerMatchService
from django.db import connection
from django.db.utils import ProgrammingError
from django.test import TestCase


class PassportCustomerMatchServiceTestCase(TestCase):
    def setUp(self):
        self.service = PassportCustomerMatchService(similarity_threshold=0.2)

    def test_match_returns_passport_found_when_passport_exists(self):
        customer = Customer.objects.create(
            customer_type="person",
            first_name="Mario",
            last_name="Rossi",
            passport_number="YA1234567",
        )

        result = self.service.match(
            {
                "first_name": "Mario",
                "last_name": "Rossi",
                "passport_number": "YA1234567",
            }
        )

        self.assertEqual(result["status"], "passport_found")
        self.assertEqual(result["recommended_action"], "update_customer")
        self.assertEqual(result["exact_matches"][0]["id"], customer.id)

    def test_match_returns_exact_name_found_when_name_matches_and_passport_missing(self):
        customer = Customer.objects.create(
            customer_type="person",
            first_name="Anna",
            last_name="Bianchi",
            passport_number=None,
        )

        result = self.service.match(
            {
                "first_name": "Anna",
                "last_name": "Bianchi",
                "passport_number": "NEW12345",
            }
        )

        self.assertEqual(result["status"], "exact_name_found")
        self.assertEqual(result["recommended_action"], "update_customer")
        self.assertEqual(result["exact_matches"][0]["id"], customer.id)
        self.assertEqual(result["exact_matches"][0]["passport_status"], "missing")

    def test_match_returns_no_match_when_no_passport_or_name_matches(self):
        Customer.objects.create(
            customer_type="person",
            first_name="John",
            last_name="Doe",
            passport_number="P123456",
        )

        result = self.service.match(
            {
                "first_name": "Alice",
                "last_name": "Smith",
                "passport_number": "NOPE123",
            }
        )

        self.assertEqual(result["status"], "no_match")
        self.assertEqual(result["recommended_action"], "create_customer")

    def test_match_returns_insufficient_data_when_names_missing(self):
        result = self.service.match(
            {
                "passport_number": "",
            }
        )
        self.assertEqual(result["status"], "insufficient_data")
        self.assertEqual(result["recommended_action"], "none")

    def test_match_returns_similar_name_found_for_fuzzy_candidates(self):
        if connection.vendor != "postgresql":
            self.skipTest("Trigram fuzzy search requires PostgreSQL.")

        Customer.objects.create(customer_type="person", first_name="Stefano", last_name="Galassi")
        Customer.objects.create(customer_type="person", first_name="Stefania", last_name="Galasso")

        try:
            result = self.service.match(
                {
                    "first_name": "Stefano",
                    "last_name": "Galasy",
                    "passport_number": "",
                }
            )
        except ProgrammingError as exc:
            if "pg_trgm" in str(exc).lower():
                self.skipTest("pg_trgm extension is not enabled in the test database.")
            raise

        self.assertEqual(result["status"], "similar_name_found")
        self.assertGreaterEqual(len(result["similar_matches"]), 1)
