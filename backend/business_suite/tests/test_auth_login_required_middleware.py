"""
FILE_ROLE: Test coverage for business_suite.

KEY_COMPONENTS:
- AuthLoginRequiredMiddlewareTests: Module symbol.

INTERACTIONS:
- Depends on: Django settings/bootstrap and adjacent app services or middleware in this module.

AI_GUIDELINES:
- Keep the file focused on its narrow responsibility and avoid mixing in unrelated business logic.
- Preserve existing runtime contracts for middleware, scripts, or migrations because other code depends on them.
"""

from unittest.mock import Mock, patch

from business_suite.middlewares.auth_login_required import AuthLoginRequiredMiddleware
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase


class AuthLoginRequiredMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @patch("business_suite.authentication.ensure_mock_user")
    @patch("core.services.app_setting_service.AppSettingService.get_effective_raw", return_value=True)
    @patch("core.services.app_setting_service.AppSettingService.parse_bool", return_value=True)
    def test_injects_mock_user_for_public_path_when_mock_auth_is_enabled(
        self,
        parse_bool_mock,
        get_effective_raw_mock,
        ensure_mock_user_mock,
    ):
        request = self.factory.get("/dashboard/")
        request.user = AnonymousUser()
        mock_user = Mock(is_authenticated=True)
        ensure_mock_user_mock.return_value = mock_user
        get_response = Mock(return_value=HttpResponse("ok"))

        response = AuthLoginRequiredMiddleware(get_response)(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "ok")
        self.assertIs(request.user, mock_user)
        ensure_mock_user_mock.assert_called_once()
        get_response.assert_called_once_with(request)
        get_effective_raw_mock.assert_called_once_with("MOCK_AUTH_ENABLED", False)
        parse_bool_mock.assert_called_once_with(True, False)

    @patch("business_suite.authentication.ensure_mock_user")
    @patch("core.services.app_setting_service.AppSettingService.get_effective_raw", return_value=True)
    @patch("core.services.app_setting_service.AppSettingService.parse_bool", return_value=True)
    def test_redirects_protected_admin_paths_even_when_mock_auth_is_enabled(
        self,
        parse_bool_mock,
        get_effective_raw_mock,
        ensure_mock_user_mock,
    ):
        request = self.factory.get("/admin/dashboard/")
        request.user = AnonymousUser()
        get_response = Mock(return_value=HttpResponse("ok"))

        response = AuthLoginRequiredMiddleware(get_response)(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, settings.LOGIN_URL)
        ensure_mock_user_mock.assert_not_called()
        get_response.assert_not_called()
        get_effective_raw_mock.assert_called_once_with("MOCK_AUTH_ENABLED", False)
        parse_bool_mock.assert_called_once_with(True, False)

    @patch("business_suite.authentication.ensure_mock_user")
    @patch("core.services.app_setting_service.AppSettingService.get_effective_raw", return_value=False)
    @patch("core.services.app_setting_service.AppSettingService.parse_bool", return_value=False)
    def test_allows_login_exempt_paths_without_redirect_when_mock_auth_is_disabled(
        self,
        parse_bool_mock,
        get_effective_raw_mock,
        ensure_mock_user_mock,
    ):
        request = self.factory.get("/login/")
        request.user = AnonymousUser()
        get_response = Mock(return_value=HttpResponse("ok"))

        response = AuthLoginRequiredMiddleware(get_response)(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "ok")
        ensure_mock_user_mock.assert_not_called()
        get_response.assert_called_once_with(request)
        get_effective_raw_mock.assert_called_once_with("MOCK_AUTH_ENABLED", False)
        parse_bool_mock.assert_called_once_with(False, False)
