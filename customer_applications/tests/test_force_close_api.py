from datetime import date

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from customer_applications.models import DocApplication
from customers.models import Customer
from products.models import Product


class ForceCloseAPITest(TestCase):
    def setUp(self):
        # Create users
        self.user_with_perm = User.objects.create_user(username="withperm", password="pw")
        perm = Permission.objects.get(codename="change_docapplication")
        self.user_with_perm.user_permissions.add(perm)

        self.user_without_perm = User.objects.create_user(username="noperm", password="pw")

        # Basic data: customer and product
        self.customer = Customer.objects.create(first_name="Test", last_name="Customer")
        self.product = Product.objects.create(name="Test Product", code="TP")
        # Ensure product requires documents so application is not auto-completed on save
        self.product.required_documents = "ID"
        self.product.save()

        # Create application
        self.application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=date.today(),
            created_by=self.user_with_perm,
        )

        self.client = APIClient()

    def test_force_close_success(self):
        self.client.force_authenticate(user=self.user_with_perm)
        url = f"/api/customer-applications/{self.application.id}/force-close/"
        resp = self.client.post(url, {})
        if resp.status_code != status.HTTP_200_OK:
            print("DEBUG force_close response:", resp.status_code, resp.content)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, DocApplication.STATUS_COMPLETED)

    def test_force_close_forbidden(self):
        self.client.force_authenticate(user=self.user_without_perm)
        url = f"/api/customer-applications/{self.application.id}/force-close/"
        resp = self.client.post(url, {})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_force_close_already_completed(self):
        self.application.status = DocApplication.STATUS_COMPLETED
        self.application.save()
        self.client.force_authenticate(user=self.user_with_perm)
        url = f"/api/customer-applications/{self.application.id}/force-close/"
        resp = self.client.post(url, {})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_includes_can_force_close_flag(self):
        # User with permission should see can_force_close True
        self.client.force_authenticate(user=self.user_with_perm)
        list_url = f"/api/customer-applications/"
        resp = self.client.get(list_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        results = data.get("results", [])
        if not any(r.get("canForceClose") is True for r in results):
            print("DEBUG list response for user_with_perm:", data)
        self.assertTrue(any(r.get("canForceClose") is True for r in results))

        # User without permission should see can_force_close False
        self.client.force_authenticate(user=self.user_without_perm)
        resp2 = self.client.get(list_url)
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)
        data2 = resp2.json()
        results2 = data2.get("results", [])
        if not any(r.get("canForceClose") is False for r in results2):
            print("DEBUG list response for user_without_perm:", data2)
        self.assertTrue(any(r.get("canForceClose") is False for r in results2))

    def test_force_closed_app_is_ready_for_invoice(self):
        """Force closed applications should be ready for invoice even if documents are missing."""
        self.client.force_authenticate(user=self.user_with_perm)

        # 1. Force close the app
        url = f"/api/customer-applications/{self.application.id}/force-close/"
        self.client.post(url, {})

        # 2. Check list response for readyForInvoice flag
        list_url = "/api/customer-applications/"
        resp = self.client.get(list_url)
        data = resp.json()
        app_data = next((r for r in data["results"] if r["id"] == self.application.id), None)
        self.assertTrue(
            app_data["readyForInvoice"],
            "Force closed application should be ready for invoice regardless of document status",
        )
