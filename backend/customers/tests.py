import datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

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


class CustomerModelTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_superuser(username="testadmin", email="admin@example.com", password="password")
        self.client.force_login(self.user)

    def test_get_gender_display_returns_choice_label(self):
        # Create a customer with gender set
        cust = Customer.objects.create(customer_type="person", first_name="G", last_name="T", gender="M")
        # Default language should follow configured document language
        default_lang = settings.DEFAULT_DOCUMENT_LANGUAGE_CODE or "en"
        self.assertEqual(cust.get_gender_display(), cust.get_gender_display(lang=default_lang))
        # Explicit language should return the expected string when coerced
        self.assertEqual(str(cust.get_gender_display(lang="en")), "Male")
        if default_lang == "en":
            self.assertEqual(cust.get_gender_display(), "Male")
        # If Indonesian translations exist and messages are compiled, expect the correct translation.
        id_display = str(cust.get_gender_display(lang="id"))
        # Always ensure it's a string and not empty
        self.assertIsInstance(id_display, str)
        self.assertNotEqual(id_display, "")
        # If the PO/MO files are compiled, we expect the official Indonesian translations.
        if id_display != "Male":
            self.assertEqual(id_display, "Laki-laki")
