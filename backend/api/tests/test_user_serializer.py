from unittest.mock import Mock, patch

from django.db import DatabaseError
from django.test import SimpleTestCase

from api.serializers.user_serializer import UserProfileSerializer


class UserProfileSerializerTests(SimpleTestCase):
    @staticmethod
    def _build_user():
        user = Mock()
        user.id = 42
        return user

    @patch("api.serializers.user_serializer.UserProfile")
    def test_get_avatar_handles_profile_schema_errors(self, mock_user_profile):
        mock_user_profile.objects.filter.side_effect = DatabaseError("column core_userprofile.cache_enabled does not exist")
        serializer = UserProfileSerializer(context={})

        avatar = serializer.get_avatar(self._build_user())

        self.assertIsNone(avatar)

    @patch("api.serializers.user_serializer.default_storage.url")
    @patch("api.serializers.user_serializer.UserProfile")
    def test_get_avatar_builds_absolute_url_when_request_present(self, mock_user_profile, mock_storage_url):
        mock_user_profile.objects.filter.return_value.values_list.return_value.first.return_value = "avatars/user_42.png"
        mock_storage_url.return_value = "/media/avatars/user_42.png"
        request = Mock()
        request.build_absolute_uri.return_value = "http://localhost:8000/media/avatars/user_42.png"
        serializer = UserProfileSerializer(context={"request": request})

        avatar = serializer.get_avatar(self._build_user())

        self.assertEqual(avatar, "http://localhost:8000/media/avatars/user_42.png")
        mock_storage_url.assert_called_once_with("avatars/user_42.png")
        request.build_absolute_uri.assert_called_once_with("/media/avatars/user_42.png")
