from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from products.models import Product

TEST_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test-default-cache",
    },
    "select2": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test-select2-cache",
    },
}


@override_settings(CACHES=TEST_CACHES)
class ProductAndReportRolePermissionsTests(TestCase):
    def setUp(self):
        user_model = get_user_model()

        self.regular_user = user_model.objects.create_user(
            username="regular-products-user",
            email="regular-products-user@example.com",
            password="password",
        )

        self.manager_user = user_model.objects.create_user(
            username="manager-products-user",
            email="manager-products-user@example.com",
            password="password",
        )
        manager_group, _ = Group.objects.get_or_create(name="manager")
        self.manager_user.groups.add(manager_group)

        self.admin_group_user = user_model.objects.create_user(
            username="admin-group-products-user",
            email="admin-group-products-user@example.com",
            password="password",
        )
        admin_group, _ = Group.objects.get_or_create(name="admin")
        self.admin_group_user.groups.add(admin_group)

        self.regular_client = APIClient()
        self.regular_client.force_authenticate(user=self.regular_user)

        self.manager_client = APIClient()
        self.manager_client.force_authenticate(user=self.manager_user)

        self.admin_group_client = APIClient()
        self.admin_group_client.force_authenticate(user=self.admin_group_user)

        self.product = Product.objects.create(
            name="Visa Extension Product",
            code="VISA-EXT-100",
            product_type="visa",
            description="Product used for permission tests",
        )

    def test_regular_user_can_list_products_for_combobox_queries(self):
        response = self.regular_client.get(reverse("products-list"))
        self.assertEqual(response.status_code, 200)
        rows = response.data.get("results", [])
        self.assertTrue(any(row.get("id") == self.product.id for row in rows))

    def test_regular_user_can_use_product_lookup_endpoint_for_comboboxes(self):
        response = self.regular_client.get(reverse("api-product-by-id", kwargs={"product_id": self.product.id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["product"]["id"], self.product.id)
        self.assertIn("required_documents", response.data)
        self.assertIn("optional_documents", response.data)

    def test_regular_user_cannot_retrieve_product_detail(self):
        response = self.regular_client.get(reverse("products-detail", kwargs={"pk": self.product.id}))
        self.assertEqual(response.status_code, 403)

    def test_regular_user_cannot_create_products(self):
        response = self.regular_client.post(
            reverse("products-list"),
            data={"name": "Blocked", "code": "BLOCKED-1", "productType": "visa"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_regular_user_cannot_quick_create_products(self):
        response = self.regular_client.post(reverse("api-product-quick-create"), data={}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_manager_group_user_can_retrieve_product_detail(self):
        response = self.manager_client.get(reverse("products-detail", kwargs={"pk": self.product.id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], self.product.id)

    def test_admin_group_user_can_retrieve_product_detail(self):
        response = self.admin_group_client.get(reverse("products-detail", kwargs={"pk": self.product.id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], self.product.id)

    def test_regular_user_cannot_access_reports_api(self):
        response = self.regular_client.get(reverse("api-reports-index"))
        self.assertEqual(response.status_code, 403)

    def test_manager_group_user_can_access_reports_api(self):
        response = self.manager_client.get(reverse("api-reports-index"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("reports", response.data)
