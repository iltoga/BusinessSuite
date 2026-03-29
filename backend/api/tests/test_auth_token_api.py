"""Regression tests for token authentication and refresh endpoints."""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

User = get_user_model()


@override_settings(MOCK_AUTH_ENABLED=False)
class AuthTokenApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="auth-user",
            email="auth-user@example.com",
            password="password123",
            first_name="Auth",
            last_name="User",
        )

    def test_login_returns_canonical_envelope_and_refresh_cookie(self):
        response = self.client.post(
            "/api/api-token-auth/",
            {"username": self.user.username, "password": "password123"},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()

        self.assertIn("data", body)
        self.assertIn("meta", body)
        self.assertEqual(body["meta"]["api_version"], settings.API_VERSION)
        self.assertIn("request_id", body["meta"])
        self.assertEqual(body["data"]["user"]["username"], self.user.username)
        self.assertEqual(body["data"]["user"]["email"], self.user.email)
        self.assertIn("access_token", body["data"])

        refresh_cookie = response.cookies.get(settings.JWT_REFRESH_COOKIE_NAME)
        self.assertIsNotNone(refresh_cookie)
        if refresh_cookie is not None:
            self.assertTrue(refresh_cookie.value)
            self.assertTrue(refresh_cookie["httponly"])

        session_hint_cookie = response.cookies.get(
            getattr(settings, "JWT_REFRESH_SESSION_HINT_COOKIE_NAME", "bs_refresh_session_hint")
        )
        self.assertIsNotNone(session_hint_cookie)
        if session_hint_cookie is not None:
            self.assertEqual(session_hint_cookie.value, "1")
            self.assertFalse(session_hint_cookie["httponly"])

    def test_refresh_uses_http_only_cookie_and_returns_new_access_token(self):
        login_response = self.client.post(
            "/api/api-token-auth/",
            {"username": self.user.username, "password": "password123"},
            format="json",
        )
        refresh_cookie = login_response.cookies.get(settings.JWT_REFRESH_COOKIE_NAME)
        self.assertIsNotNone(refresh_cookie)
        if refresh_cookie is not None:
            self.client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = refresh_cookie.value

        response = self.client.post("/api/token/refresh/", {}, format="json")

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertIn("data", body)
        self.assertIn("access_token", body["data"])
        self.assertEqual(body["data"]["user"]["username"], self.user.username)
        self.assertIn(settings.JWT_REFRESH_COOKIE_NAME, response.cookies)
        self.assertIn(
            getattr(settings, "JWT_REFRESH_SESSION_HINT_COOKIE_NAME", "bs_refresh_session_hint"),
            response.cookies,
        )

    def test_logout_clears_refresh_cookie(self):
        login_response = self.client.post(
            "/api/api-token-auth/",
            {"username": self.user.username, "password": "password123"},
            format="json",
        )
        login_body = login_response.json()
        access_token = login_body["data"]["access_token"]
        refresh_cookie = login_response.cookies.get(settings.JWT_REFRESH_COOKIE_NAME)
        self.assertIsNotNone(refresh_cookie)
        if refresh_cookie is not None:
            self.client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = refresh_cookie.value

        response = self.client.post(
            "/api/user-profile/logout/",
            {},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )

        self.assertEqual(response.status_code, 204, response.content)
        cleared_cookie = response.cookies.get(settings.JWT_REFRESH_COOKIE_NAME)
        self.assertIsNotNone(cleared_cookie)
        if cleared_cookie is not None:
            self.assertEqual(str(cleared_cookie["max-age"]), "0")

        cleared_hint_cookie = response.cookies.get(
            getattr(settings, "JWT_REFRESH_SESSION_HINT_COOKIE_NAME", "bs_refresh_session_hint")
        )
        self.assertIsNotNone(cleared_hint_cookie)
        if cleared_hint_cookie is not None:
            self.assertEqual(str(cleared_hint_cookie["max-age"]), "0")
