import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from customers.models import Customer


class PassportFieldsTestCase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_superuser(username="testadmin", email="admin@example.com", password="password")
        self.client.force_login(self.user)

    def test_passport_fields_model_exist_and_save(self):
        # Create a basic customer
        cust = Customer.objects.create(customer_type="person", first_name="Temp", last_name="Person")

        # Set passport fields
        cust.passport_number = "X1234567"
        cust.passport_issue_date = datetime.date(2020, 1, 1)
        cust.passport_expiration_date = datetime.date(2030, 1, 1)
        cust.save()

        # Refetch from DB to ensure persistence
        stored = Customer.objects.get(pk=cust.pk)
        self.assertEqual(stored.passport_number, "X1234567")
        self.assertEqual(str(stored.passport_issue_date), "2020-01-01")
        self.assertEqual(str(stored.passport_expiration_date), "2030-01-01")

    def test_customer_create_populates_passport_from_session_mrz(self):
        # Prepare session MRZ data (simulating a scan)
        session = self.client.session
        session["mrz_data"] = {
            "number": "X8888888",
            "expiration_date_yyyy_mm_dd": "2035-12-20",
            "date_of_birth_yyyy_mm_dd": "1985-03-20",
            "names": "Alice",
            "surname": "Smith",
        }
        session.save()

        # Post to customer creation endpoint
        url = reverse("customer-create")
        data = {
            "customer_type": "person",
            "first_name": "Alice",
            "last_name": "Smith",
            "title": "Mr",
            "gender": "F",
        }
        response = self.client.post(url, data)

        # Expect redirect to customer list (302)
        self.assertEqual(response.status_code, 302)

        # Verify customer was created with passport data from session
        cust = Customer.objects.filter(first_name="Alice", last_name="Smith").first()
        self.assertIsNotNone(cust)
        self.assertEqual(cust.passport_number, "X8888888")
        self.assertEqual(str(cust.passport_expiration_date), "2035-12-20")

    def test_search_customers_by_partial_passport_number(self):
        # Create a customer with a passport number and ensure search works with partial query
        cust = Customer.objects.create(customer_type="person", first_name="Bob", last_name="Marley")
        cust.passport_number = "P987654321"
        cust.save()

        url = reverse("customer-list")
        # Search by partial passport (middle digits)
        response = self.client.get(url, {"q": "87654"})
        self.assertEqual(response.status_code, 200)
        # The passport number or customer name should appear in the response
        self.assertContains(response, "P987654321")


class CustomerAnalysisViewTestCase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_superuser(username="testadmin", email="admin@example.com", password="password")
        self.client.force_login(self.user)

    def test_nationality_analysis_view_renders_plot(self):
        from core.models.country_code import CountryCode

        # Create countries
        idn = CountryCode.objects.create(country="Indonesia", alpha2_code="ID", alpha3_code="IDN", numeric_code="360")
        usa = CountryCode.objects.create(
            country="United States", alpha2_code="US", alpha3_code="USA", numeric_code="840"
        )

        # Create customers with nationalities
        Customer.objects.create(customer_type="person", first_name="A", last_name="One", nationality=idn)
        Customer.objects.create(customer_type="person", first_name="B", last_name="Two", nationality=usa)

        url = reverse("customer-chart-analysis", args=["nationality"])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data:image/png;base64,")

    def test_age_analysis_view_renders_plot_ignoring_missing_birthdates(self):
        # Create customers with and without birthdates
        Customer.objects.create(
            customer_type="person", first_name="WithBD", last_name="One", birthdate=datetime.date(1990, 1, 1)
        )
        Customer.objects.create(customer_type="person", first_name="NoBD", last_name="Two")

        url = reverse("customer-chart-analysis", args=["age"])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data:image/png;base64,")
