import datetime
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from customer_applications.models import DocApplication, Document
from customers.models import Customer
from products.models import Product
from products.models.document_type import DocumentType


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


class CustomerListAPITestCase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_superuser(username="testadmin", email="admin@example.com", password="password")
        self.client.force_login(self.user)

    def test_customer_list_includes_passport_flags(self):
        today = timezone.now().date()
        expired = Customer.objects.create(
            customer_type="person",
            first_name="Expired",
            last_name="Customer",
            passport_expiration_date=today - datetime.timedelta(days=1),
        )
        expiring = Customer.objects.create(
            customer_type="person",
            first_name="Soon",
            last_name="Customer",
            passport_expiration_date=today + datetime.timedelta(days=30),
        )

        url = reverse("customers-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        expired_item = next(item for item in data["results"] if item["id"] == expired.id)
        expiring_item = next(item for item in data["results"] if item["id"] == expiring.id)

        self.assertTrue(expired_item["passportExpired"])
        self.assertFalse(expired_item["passportExpiringSoon"])
        self.assertTrue(expiring_item["passportExpiringSoon"])

    def test_toggle_active_endpoint(self):
        customer = Customer.objects.create(customer_type="person", first_name="Active", last_name="User")
        url = reverse("customers-toggle-active", args=[customer.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        customer.refresh_from_db()
        self.assertFalse(customer.active)


class CustomerApplicationDetailAPITestCase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_superuser(username="appadmin", email="app@example.com", password="password")
        self.client.force_login(self.user)

        self.customer = Customer.objects.create(
            customer_type="person",
            first_name="Ana",
            last_name="Doe",
            active=True,
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )
        self.product = Product.objects.create(
            name="Visa Extension",
            code="VISA-EXT",
            product_type="visa",
            required_documents="Passport",
        )
        self.application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=timezone.now().date(),
            created_by=self.user,
        )
        self.doc_type = DocumentType.objects.create(
            name="Passport",
            has_ocr_check=True,
            has_doc_number=True,
            has_expiration_date=True,
            has_file=True,
        )
        self.document = Document.objects.create(
            doc_application=self.application,
            doc_type=self.doc_type,
            created_by=self.user,
        )

    def test_application_detail_includes_documents(self):
        url = reverse("customer-applications-detail", kwargs={"pk": self.application.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["id"], self.application.id)
        self.assertEqual(len(payload["documents"]), 1)
        self.assertEqual(payload["documents"][0]["docType"]["name"], "Passport")

    def test_document_update_accepts_metadata(self):
        url = reverse("documents-detail", kwargs={"pk": self.document.pk})
        payload = {
            "doc_number": "A123456",
            "metadata": {"number": "A123456"},
        }
        response = self.client.patch(url, payload, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.document.refresh_from_db()
        self.assertEqual(self.document.doc_number, "A123456")
        self.assertEqual(self.document.metadata.get("number"), "A123456")


class ProductApiTestCase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_superuser(
            username="productadmin", email="product@example.com", password="password"
        )
        self.client.force_login(self.user)
        self.required_doc = DocumentType.objects.create(name="Passport", is_in_required_documents=True)
        self.optional_doc = DocumentType.objects.create(name="Bank Statement", is_in_required_documents=False)

    def test_product_create_with_tasks_and_documents(self):
        url = reverse("products-list")
        payload = {
            "name": "Visa Extension",
            "code": "VISA-EXT",
            "description": "Extension service",
            "productType": "visa",
            "basePrice": "1500000.00",
            "validity": 30,
            "documentsMinValidity": 180,
            "requiredDocumentIds": [self.required_doc.id],
            "optionalDocumentIds": [self.optional_doc.id],
            "tasks": [
                {
                    "step": 1,
                    "name": "Collect Documents",
                    "description": "Gather required docs",
                    "cost": "0.00",
                    "duration": 5,
                    "durationIsBusinessDays": True,
                    "notifyDaysBefore": 2,
                    "lastStep": False,
                },
                {
                    "step": 2,
                    "name": "Submit Application",
                    "description": "Submit to immigration",
                    "cost": "500000.00",
                    "duration": 3,
                    "durationIsBusinessDays": True,
                    "notifyDaysBefore": 1,
                    "lastStep": True,
                },
            ],
        }

        response = self.client.post(url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 201)
        product = Product.objects.get(code="VISA-EXT")
        self.assertEqual(product.required_documents, "Passport")
        self.assertEqual(product.optional_documents, "Bank Statement")
        self.assertEqual(product.tasks.count(), 2)

    def test_product_update_reconciles_tasks(self):
        product = Product.objects.create(
            name="Tourist Visa",
            code="TOUR-1",
            product_type="visa",
            required_documents="Passport",
        )
        task_one = product.tasks.create(
            step=1,
            name="Collect Documents",
            description="",
            cost=0,
            duration=2,
            duration_is_business_days=True,
            notify_days_before=1,
            last_step=False,
        )
        product.tasks.create(
            step=2,
            name="Submit",
            description="",
            cost=0,
            duration=1,
            duration_is_business_days=True,
            notify_days_before=0,
            last_step=True,
        )

        url = reverse("products-detail", kwargs={"pk": product.id})
        payload = {
            "name": "Tourist Visa Updated",
            "code": "TOUR-1",
            "productType": "visa",
            "requiredDocumentIds": [self.required_doc.id],
            "optionalDocumentIds": [],
            "tasks": [
                {
                    "id": task_one.id,
                    "step": 1,
                    "name": "Collect Docs",
                    "description": "Updated",
                    "cost": "0.00",
                    "duration": 4,
                    "durationIsBusinessDays": True,
                    "notifyDaysBefore": 1,
                    "lastStep": True,
                }
            ],
        }
        response = self.client.put(url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        product.refresh_from_db()
        self.assertEqual(product.tasks.count(), 1)
        self.assertEqual(product.tasks.first().name, "Collect Docs")

    def test_product_can_delete_endpoint(self):
        product = Product.objects.create(name="Simple", code="S-1", product_type="other")
        url = reverse("products-can-delete", kwargs={"pk": product.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("can_delete", payload)
