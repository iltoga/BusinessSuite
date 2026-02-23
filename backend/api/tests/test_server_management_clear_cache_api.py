from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from rest_framework.test import APIClient


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "server-management-clear-cache-tests",
        }
    }
)
class ServerManagementClearCacheApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser(
            username="servermgmt-cache-admin",
            email="servermgmt-cache-admin@example.com",
            password="password",
        )
        admin_group, _ = Group.objects.get_or_create(name="admin")
        self.user.groups.add(admin_group)
        self.client.force_authenticate(user=self.user)

    @patch("api.views_admin._clear_cacheops_query_store")
    @patch("api.views_admin.caches")
    def test_global_clear_purges_default_and_cacheops(self, caches_mock, clear_cacheops_mock):
        default_cache = MagicMock()
        caches_mock.__getitem__.return_value = default_cache

        response = self.client.post("/api/server-management/clear-cache/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        cleared_stores = payload.get("clearedStores", payload.get("cleared_stores"))
        self.assertEqual(cleared_stores, ["default", "cacheops"])
        default_cache.clear.assert_called_once()
        clear_cacheops_mock.assert_called_once()

    @patch("api.views_admin._clear_cacheops_query_store")
    @patch("api.views_admin.caches")
    @patch("cache.namespace.namespace_manager.increment_user_version", return_value=7)
    def test_user_clear_uses_namespace_invalidation_only(
        self, increment_mock, caches_mock, clear_cacheops_mock
    ):
        response = self.client.post("/api/server-management/clear-cache/?user_id=123")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        user_id = payload.get("userId", payload.get("user_id"))
        new_version = payload.get("newVersion", payload.get("new_version"))
        self.assertEqual(user_id, 123)
        self.assertEqual(new_version, 7)
        increment_mock.assert_called_once_with(123)
        caches_mock.__getitem__.assert_not_called()
        clear_cacheops_mock.assert_not_called()

    @patch("api.views_admin._clear_cacheops_query_store", side_effect=RuntimeError("cacheops down"))
    @patch("api.views_admin.caches")
    def test_global_clear_returns_500_when_cacheops_purge_fails(self, caches_mock, _clear_cacheops_mock):
        default_cache = MagicMock()
        caches_mock.__getitem__.return_value = default_cache

        response = self.client.post("/api/server-management/clear-cache/")

        self.assertEqual(response.status_code, 500)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertIn("cacheops down", payload["message"])
        default_cache.clear.assert_called_once()
