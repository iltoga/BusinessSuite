from django.contrib.auth import get_user_model
from django.test import TestCase

from core.models import UserSettings


class UserSettingsModelTests(TestCase):
    def test_user_settings_created_on_user_creation(self):
        User = get_user_model()
        user = User.objects.create_user(username="u1", email="u1@example.com", password="pass")
        # Should auto-create settings via signal
        self.assertTrue(hasattr(user, "settings"))
        settings_obj = user.settings
        self.assertIsInstance(settings_obj, UserSettings)
        self.assertEqual(settings_obj.theme, "starlight")
        self.assertFalse(settings_obj.dark_mode)

    def test_existing_users_populated_by_migration(self):
        # This test simulates that migration RunPython will create settings for existing users.
        # Create a user and then manually call get_or_create
        User = get_user_model()
        user = User.objects.create_user(username="u2", email="u2@example.com", password="pass")
        settings_obj, created = UserSettings.objects.get_or_create(user=user)
        # Ensure get_or_create did not create a new settings object (signal should have created it)
        self.assertFalse(created)
        self.assertIsNotNone(settings_obj)
