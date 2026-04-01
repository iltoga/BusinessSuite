"""Regression tests for customer application list search behavior."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from customer_applications.models import DocApplication
from customers.models import Customer
from products.models import Product


class CustomerApplicationListApiTestCase(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser(
            username="applicationadmin",
            email="applicationadmin@example.com",
            password="password",
        )
        self.client.force_login(self.user)

        self.customer = Customer.objects.create(
            customer_type="person",
            first_name="Application",
            last_name="Customer",
            active=True,
        )
        self.product = Product.objects.create(
            name="VOA Extension",
            code="VOA-EXT",
            product_type="visa",
            required_documents="Passport",
        )

    def create_application(self) -> DocApplication:
        return DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=timezone.now().date(),
            created_by=self.user,
        )

    def test_application_list_search_matches_primary_key_with_hash_prefix(self):
        target_application = self.create_application()
        self.create_application()

        response = self.client.get(reverse("customer-applications-list"), {"search": f"#{target_application.id}"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["id"], target_application.id)

    def test_application_list_search_matches_primary_key_without_hash_prefix(self):
        target_application = self.create_application()
        self.create_application()

        response = self.client.get(reverse("customer-applications-list"), {"search": str(target_application.id)})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["id"], target_application.id)
