from unittest.mock import Mock, patch

from django.db import DatabaseError
from django.test import SimpleTestCase

from api.serializers.auth_serializer import CustomTokenObtainSerializer


class CustomTokenObtainSerializerTests(SimpleTestCase):
    @staticmethod
    def _build_user():
        user = Mock()
        user.id = 42
        user.email = "admin@example.com"
        user.first_name = "Admin"
        user.last_name = "User"
        user.username = "admin"
        user.is_superuser = True
        user.is_staff = True
        user.groups.values_list.return_value = ["admins"]
        return user

    @patch("api.serializers.auth_serializer.UserProfile")
    @patch("api.serializers.auth_serializer.TokenObtainPairSerializer.get_token")
    def test_get_token_handles_profile_schema_errors(self, mock_get_token, mock_user_profile):
        mock_get_token.return_value = {}
        mock_user_profile.objects.filter.side_effect = DatabaseError("column core_userprofile.cache_enabled does not exist")
        user = self._build_user()

        token = CustomTokenObtainSerializer.get_token(user)

        self.assertEqual(token["email"], "admin@example.com")
        self.assertEqual(token["fullName"], "Admin User")
        self.assertEqual(token["roles"], ["admins"])
        self.assertEqual(token["groups"], ["admins"])
        self.assertTrue(token["is_superuser"])
        self.assertTrue(token["is_staff"])
        self.assertIsNone(token["avatar"])

    @patch("api.serializers.auth_serializer.default_storage.url")
    @patch("api.serializers.auth_serializer.UserProfile")
    @patch("api.serializers.auth_serializer.TokenObtainPairSerializer.get_token")
    def test_get_token_includes_avatar_when_available(self, mock_get_token, mock_user_profile, mock_storage_url):
        mock_get_token.return_value = {}
        mock_storage_url.return_value = "/media/avatars/user_42.png"
        mock_user_profile.objects.filter.return_value.values_list.return_value.first.return_value = "avatars/user_42.png"
        user = self._build_user()

        token = CustomTokenObtainSerializer.get_token(user)

        self.assertEqual(token["avatar"], "/media/avatars/user_42.png")
        mock_storage_url.assert_called_once_with("avatars/user_42.png")
