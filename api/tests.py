import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from customers.models import Customer


class CustomerQuickCreateAPITestCase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_superuser(username="testadmin", email="admin@example.com", password="password")
        self.client.force_login(self.user)

    def test_customer_quick_create_accepts_passport_fields(self):
        url = reverse("api-customer-quick-create")
        data = {
            "title": "Mr",
            "customer_type": "person",
            "first_name": "John",
            "last_name": "Doe",
            "birthdate": "1990-01-01",
            "email": "john@example.com",
            "telephone": "081234567",
            "passport_number": "P12345678",
            "passport_issue_date": "2018-05-10",
            "passport_expiration_date": "2028-05-10",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 201)
        cust = Customer.objects.filter(first_name="John", last_name="Doe").first()
        self.assertIsNotNone(cust)
        self.assertEqual(cust.passport_number, "P12345678")
        self.assertEqual(str(cust.passport_issue_date), "2018-05-10")
        self.assertEqual(str(cust.passport_expiration_date), "2028-05-10")

    def test_customer_detail_returns_gender_display(self):
        from django.urls import reverse

        # Create a customer with a gender and fetch the detail view
        cust = Customer.objects.create(customer_type="person", first_name="Jane", last_name="Roe", gender="F")
        url = reverse("api-customer-detail", args=[cust.pk])
        # Default language
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("gender_display", data)
        self.assertIsInstance(data["gender_display"], str)

        # Indonesian (document_lang) - if translations compiled, expect Indonesian translation
        url_id = f"{url}?document_lang=id"
        response_id = self.client.get(url_id)
        self.assertEqual(response_id.status_code, 200)
        data_id = response_id.json()
        self.assertIn("gender_display", data_id)
        gender_display = data_id["gender_display"]
        self.assertIsInstance(gender_display, str)
        if gender_display != "Female":
            self.assertEqual(gender_display, "Perempuan")
