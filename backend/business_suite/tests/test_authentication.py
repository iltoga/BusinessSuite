"""
FILE_ROLE: Test coverage for business_suite.

KEY_COMPONENTS:
- EnsureMockUserTests: Module symbol.
- JwtOrMockAuthenticationTests: Module symbol.

INTERACTIONS:
- Depends on: Django settings/bootstrap and adjacent app services or middleware in this module.

AI_GUIDELINES:
- Keep the file focused on its narrow responsibility and avoid mixing in unrelated business logic.
- Preserve existing runtime contracts for middleware, scripts, or migrations because other code depends on them.
"""

from unittest.mock import patch

from business_suite.authentication import JwtOrMockAuthentication, ensure_mock_user
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import RequestFactory, TestCase, override_settings

User = get_user_model()


class EnsureMockUserTests(TestCase):
    @override_settings(
        MOCK_AUTH_USERNAME="mock-user",
        MOCK_AUTH_EMAIL="mock@example.com",
        MOCK_AUTH_IS_STAFF=False,
        MOCK_AUTH_IS_SUPERUSER=False,
        MOCK_AUTH_GROUPS=["admin", "manager"],
    )
    def test_ensure_mock_user_updates_existing_user_and_groups(self):
        legacy_group = Group.objects.create(name="legacy")
        user = User.objects.create_user(
            username="mock-user",
            email="old@example.com",
            password="pass",
            is_staff=True,
            is_superuser=True,
        )
        user.groups.add(legacy_group)

        resolved_user = ensure_mock_user()

        user.refresh_from_db()
        self.assertEqual(resolved_user.id, user.id)
        self.assertEqual(user.email, "mock@example.com")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(set(user.groups.values_list("name", flat=True)), {"admin", "manager"})


class JwtOrMockAuthenticationTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.mock_user = User.objects.create_user("mock-user", "mock@example.com", "pass")
        self.authentication = JwtOrMockAuthentication()

    @patch("business_suite.authentication.update_last_login")
    @patch("business_suite.authentication.ensure_mock_user")
    @patch("core.services.app_setting_service.AppSettingService.get_effective_raw", return_value=True)
    @patch("core.services.app_setting_service.AppSettingService.parse_bool", return_value=True)
    def test_authenticates_mock_token_from_query_params(
        self, parse_bool_mock, get_effective_raw_mock, ensure_mock_user_mock, update_last_login_mock
    ):
        ensure_mock_user_mock.return_value = self.mock_user
        request = self.factory.get("/api/resource/?token=mock-token")

        result = self.authentication.authenticate(request)

        self.assertEqual(result, (self.mock_user, None))
        ensure_mock_user_mock.assert_called_once()
        update_last_login_mock.assert_called_once_with(None, self.mock_user)
        get_effective_raw_mock.assert_called_once_with("MOCK_AUTH_ENABLED", False)
        parse_bool_mock.assert_called_once_with(True, False)

    @patch("business_suite.authentication.update_last_login")
    @patch("business_suite.authentication.ensure_mock_user")
    @patch("core.services.app_setting_service.AppSettingService.get_effective_raw", return_value=True)
    @patch("core.services.app_setting_service.AppSettingService.parse_bool", return_value=True)
    def test_authenticates_mock_token_from_authorization_header(
        self, parse_bool_mock, get_effective_raw_mock, ensure_mock_user_mock, update_last_login_mock
    ):
        ensure_mock_user_mock.return_value = self.mock_user
        request = self.factory.get("/api/resource/", HTTP_AUTHORIZATION="Bearer mock-token")

        result = self.authentication.authenticate(request)

        self.assertEqual(result, (self.mock_user, None))
        ensure_mock_user_mock.assert_called_once()
        update_last_login_mock.assert_called_once_with(None, self.mock_user)
        get_effective_raw_mock.assert_called_once_with("MOCK_AUTH_ENABLED", False)
        parse_bool_mock.assert_called_once_with(True, False)

    @patch("business_suite.authentication.JWTAuthentication.authenticate", return_value=("jwt-user", "jwt-token"))
    @patch("core.services.app_setting_service.AppSettingService.get_effective_raw", return_value=False)
    @patch("core.services.app_setting_service.AppSettingService.parse_bool", return_value=False)
    def test_falls_back_to_jwt_authentication_when_mock_auth_is_disabled(
        self, parse_bool_mock, get_effective_raw_mock, jwt_authenticate_mock
    ):
        request = self.factory.get("/api/resource/", HTTP_AUTHORIZATION="Bearer jwt-token")

        result = self.authentication.authenticate(request)

        self.assertEqual(result, ("jwt-user", "jwt-token"))
        get_effective_raw_mock.assert_called_once_with("MOCK_AUTH_ENABLED", False)
        parse_bool_mock.assert_called_once_with(False, False)
        jwt_authenticate_mock.assert_called_once_with(request)
