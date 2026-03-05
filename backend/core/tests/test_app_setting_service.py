from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from core.models import AppSetting
from core.services.app_setting_service import AppSettingService


@override_settings(TESTING=False)
class AppSettingServiceCacheTests(TestCase):
    def setUp(self):
        AppSettingService.invalidate_cache()

    def test_get_raw_uses_cache_and_invalidates_on_update(self):
        user = get_user_model().objects.create_user(username="setting-cache-user")
        setting = AppSetting.objects.create(
            name="CACHE_TEST_KEY",
            value="one",
            scope=AppSetting.SCOPE_BACKEND,
            updated_by=user,
        )

        with self.assertNumQueries(1):
            self.assertEqual(AppSettingService.get_raw("CACHE_TEST_KEY", require_override=True), "one")

        with self.assertNumQueries(0):
            self.assertEqual(AppSettingService.get_raw("CACHE_TEST_KEY", require_override=True), "one")

        setting.value = "two"
        setting.save(update_fields=["value", "updated_at"])

        with self.assertNumQueries(1):
            self.assertEqual(AppSettingService.get_raw("CACHE_TEST_KEY", require_override=True), "two")

    def test_get_raw_invalidates_on_delete(self):
        user = get_user_model().objects.create_user(username="setting-cache-user-delete")
        setting = AppSetting.objects.create(
            name="CACHE_DELETE_KEY",
            value="to-delete",
            scope=AppSetting.SCOPE_BACKEND,
            updated_by=user,
        )
        self.assertEqual(AppSettingService.get_raw("CACHE_DELETE_KEY", require_override=True), "to-delete")

        setting.delete()
        self.assertIsNone(AppSettingService.get_raw("CACHE_DELETE_KEY", default=None, require_override=True))
