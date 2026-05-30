"""Regression tests for the shared customer search backend behavior."""

from customers.models import Customer
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class CustomerSearchApiTestCase(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser(
            username="customersearchadmin",
            email="customersearchadmin@example.com",
            password="password",
        )
        self.client.force_login(self.user)

    def test_customer_list_search_supports_contact_fields_without_double_filtering(self):
        searchable_customer = Customer.objects.create(
            customer_type="person",
            first_name="Wayan",
            last_name="Searchable",
            whatsapp="+628123456789",
            active=True,
        )
        Customer.objects.create(
            customer_type="person",
            first_name="Other",
            last_name="Customer",
            whatsapp="+628987654321",
            active=True,
        )

        response = self.client.get(reverse("customers-list"), {"search": "8123456789"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["id"], searchable_customer.id)

    def test_customer_search_action_matches_list_results_for_search_alias(self):
        active_company = Customer.objects.create(
            customer_type="company",
            company_name="Acme Bali",
            active=True,
        )
        Customer.objects.create(
            customer_type="company",
            company_name="Acme Disabled",
            active=False,
        )

        list_response = self.client.get(reverse("customers-list"), {"search": "Acme"})
        search_response = self.client.get(reverse("customers-search"), {"search": "Acme"})

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(search_response.status_code, 200)

        list_ids = {item["id"] for item in list_response.json()["results"]}
        search_ids = {item["id"] for item in search_response.json()["results"]}

        self.assertEqual(list_ids, search_ids)
        self.assertEqual(search_ids, {active_company.id})
