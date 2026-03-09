from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from core.models import AppSetting
from core.services.app_setting_service import AppSettingService


@override_settings(TESTING=False)
class AppSettingServiceCacheTests(TestCase):
    def setUp(self):
        AppSettingService.invalidate_cache()
