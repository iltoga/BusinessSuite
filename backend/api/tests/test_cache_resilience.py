"""Regression tests for cache resilience helpers and fallbacks."""

from __future__ import annotations

from unittest.mock import Mock, patch

from api.async_controls import acquire_enqueue_guard, increment_guard_counter, release_enqueue_guard
from api.cache_resilience import is_transient_cache_backend_error
from api.views_admin import ServerManagementViewSet
from api.views_shared import ApiErrorHandlingMixin, ResilientAnonRateThrottle
from django.test import SimpleTestCase
from rest_framework import status


class CacheResilienceHelperTests(SimpleTestCase):
    def test_helper_detects_busy_loading_message_in_exception_chain(self):
        root = RuntimeError("Redis is loading the dataset in memory")
        wrapped = RuntimeError("cache get failed")
        wrapped.__cause__ = root

        self.assertTrue(is_transient_cache_backend_error(wrapped))

    def test_helper_ignores_non_cache_failures(self):
        self.assertFalse(is_transient_cache_backend_error(RuntimeError("database constraint violated")))


class ResilientThrottleTests(SimpleTestCase):
    @patch(
        "rest_framework.throttling.AnonRateThrottle.allow_request",
        side_effect=RuntimeError("Redis is loading the dataset in memory"),
    )
    def test_resilient_anon_throttle_fails_open_on_transient_cache_error(self, _allow_request_mock):
        throttle = ResilientAnonRateThrottle()
        request = Mock(method="GET")
        request._request = Mock(path="/api/products/")

        self.assertTrue(throttle.allow_request(request, Mock()))
        self.assertEqual(throttle.history, [])

    @patch("rest_framework.throttling.AnonRateThrottle.allow_request", side_effect=RuntimeError("permission denied"))
    def test_resilient_anon_throttle_reraises_non_cache_errors(self, _allow_request_mock):
        throttle = ResilientAnonRateThrottle()
        request = Mock(method="GET")
        request._request = Mock(path="/api/products/")

        with self.assertRaisesRegex(RuntimeError, "permission denied"):
            throttle.allow_request(request, Mock())


class ApiErrorHandlingMixinTests(SimpleTestCase):
    class _DummyView(ApiErrorHandlingMixin):
        pass

    def test_handle_exception_returns_503_for_transient_cache_failures(self):
        view = self._DummyView()

        response = view.handle_exception(RuntimeError("Redis is loading the dataset in memory"))

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data["error"]["code"], "service_unavailable")
        self.assertEqual(
            response.data["error"]["message"],
            "Service temporarily unavailable while cache services are warming up. Please retry shortly.",
        )


class AsyncControlsCacheResilienceTests(SimpleTestCase):
    @patch("api.async_controls.cache.add", side_effect=RuntimeError("Redis is loading the dataset in memory"))
    def test_acquire_enqueue_guard_bypasses_transient_cache_failures(self, _cache_add_mock):
        token = acquire_enqueue_guard("async:test:guard")

        self.assertIsNotNone(token)
        self.assertTrue(token.startswith("cache-bypass:"))

    @patch("api.async_controls.cache.incr", side_effect=RuntimeError("Redis is loading the dataset in memory"))
    def test_increment_guard_counter_returns_zero_when_cache_is_unavailable(self, _cache_incr_mock):
        self.assertEqual(increment_guard_counter(namespace="products_export_excel", event="deduplicated"), 0)

    @patch("api.async_controls.cache.get", side_effect=RuntimeError("Redis is loading the dataset in memory"))
    def test_release_enqueue_guard_ignores_transient_cache_failures(self, _cache_get_mock):
        release_enqueue_guard("async:test:guard", "real-token")


class ServerManagementThrottlePolicyTests(SimpleTestCase):
    def test_openrouter_status_fails_open_on_throttle_cache_error(self):
        view = ServerManagementViewSet()
        view.action = "openrouter_status"

        self.assertTrue(view._should_fail_open_on_throttle_cache_error())

    def test_media_cleanup_fails_closed_on_throttle_cache_error(self):
        view = ServerManagementViewSet()
        view.action = "media_cleanup"

        self.assertFalse(view._should_fail_open_on_throttle_cache_error())
