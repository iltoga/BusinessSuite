"""Property-based tests for the CacheMiddleware class.

**Feature: hybrid-cache-system, Property 13: Cache disabled bypass**

This module tests that the CacheMiddleware correctly bypasses caching when
cache is disabled for a user, ensuring queries execute directly against the
database without any caching operations.
"""

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import models
from django.test import RequestFactory, TestCase
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase

from cache.middleware import CacheMiddleware
from cache.namespace import namespace_manager


# Test model for cache bypass testing
class TestCacheBypassModel(models.Model):
    """Test model for cache bypass property testing."""
    name = models.CharField(max_length=200)
    value = models.IntegerField(default=0)
    
    class Meta:
        app_label = 'cache'


# Strategy for generating valid user IDs
user_id_strategy = st.integers(min_value=1, max_value=1000)

# Strategy for generating test data
test_name_strategy = st.text(min_size=1, max_size=50, alphabet=st.characters(blacklist_characters='\x00'))
test_value_strategy = st.integers(min_value=0, max_value=10000)


class TestCacheDisabledBypass(HypothesisTestCase):
    """Property-based tests for cache disabled bypass.

    **Feature: hybrid-cache-system, Property 13: Cache disabled bypass**
    **Validates: Requirements 4.5**

    Property: When cache_enabled is set to False for a user, all cache operations
    must be bypassed and queries must execute directly against the database.
    The middleware must set request.cache_enabled to False, preventing any
    caching operations from occurring.
    """

    def setUp(self):
        """Set up test fixtures."""
        self.middleware = CacheMiddleware(get_response=lambda r: None)
        self.factory = RequestFactory()
        # Clear cache before each test
        cache.clear()

    def tearDown(self):
        """Clean up after tests."""
        cache.clear()
        # Clean up test users
        User.objects.all().delete()

    @given(
        user_id=user_id_strategy,
        test_name=test_name_strategy,
        test_value=test_value_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_cache_disabled_sets_request_attribute_false(
        self, user_id: int, test_name: str, test_value: int
    ):
        """
        **Feature: hybrid-cache-system, Property 13: Cache disabled bypass**
        **Validates: Requirements 4.5**

        Test that when caching is disabled for a user, the middleware sets
        request.cache_enabled to False.

        This property verifies that:
        1. When cache is disabled via namespace_manager.set_cache_enabled(user_id, False)
        2. The middleware processes the request
        3. request.cache_enabled is set to False
        4. This signals to other components to bypass caching
        """
        # Create a test user with the given user_id
        # Use get_or_create to handle hypothesis retries
        user, _ = User.objects.get_or_create(
            id=user_id,
            defaults={
                'username': f'testuser_{user_id}',
                'email': f'test_{user_id}@example.com',
            }
        )

        # Disable caching for this user
        namespace_manager.set_cache_enabled(user_id, False)

        # Verify cache is disabled
        assert not namespace_manager.is_cache_enabled(user_id), (
            f"Cache should be disabled for user {user_id}"
        )

        # Create a mock request with authenticated user
        request = self.factory.get('/api/test/')
        request.user = user

        # Process request through middleware
        self.middleware.process_request(request)

        # Verify request.cache_enabled is False
        assert hasattr(request, 'cache_enabled'), (
            "Middleware should set cache_enabled attribute on request"
        )
        assert request.cache_enabled is False, (
            f"request.cache_enabled should be False when cache is disabled, "
            f"got: {request.cache_enabled}"
        )

        # Verify cache_version is still set (for potential re-enabling)
        assert hasattr(request, 'cache_version'), (
            "Middleware should set cache_version attribute even when disabled"
        )
        assert isinstance(request.cache_version, int), (
            f"cache_version should be an integer, got: {type(request.cache_version)}"
        )

    @given(user_id=user_id_strategy)
    @settings(max_examples=50, deadline=None)
    def test_cache_enabled_sets_request_attribute_true(self, user_id: int):
        """
        **Feature: hybrid-cache-system, Property 13: Cache disabled bypass (inverse)**
        **Validates: Requirements 4.5**

        Test that when caching is enabled for a user, the middleware sets
        request.cache_enabled to True.

        This property verifies the inverse case:
        1. When cache is enabled (default or explicitly set)
        2. The middleware processes the request
        3. request.cache_enabled is set to True
        4. This signals to other components to use caching
        """
        # Create a test user
        user, _ = User.objects.get_or_create(
            id=user_id,
            defaults={
                'username': f'testuser_{user_id}',
                'email': f'test_{user_id}@example.com',
            }
        )

        # Explicitly enable caching for this user (should be default)
        namespace_manager.set_cache_enabled(user_id, True)

        # Verify cache is enabled
        assert namespace_manager.is_cache_enabled(user_id), (
            f"Cache should be enabled for user {user_id}"
        )

        # Create a mock request with authenticated user
        request = self.factory.get('/api/test/')
        request.user = user

        # Process request through middleware
        self.middleware.process_request(request)

        # Verify request.cache_enabled is True
        assert hasattr(request, 'cache_enabled'), (
            "Middleware should set cache_enabled attribute on request"
        )
        assert request.cache_enabled is True, (
            f"request.cache_enabled should be True when cache is enabled, "
            f"got: {request.cache_enabled}"
        )

        # Verify cache_version is set
        assert hasattr(request, 'cache_version'), (
            "Middleware should set cache_version attribute"
        )
        assert isinstance(request.cache_version, int), (
            f"cache_version should be an integer, got: {type(request.cache_version)}"
        )
        assert request.cache_version >= 1, (
            f"cache_version should be >= 1, got: {request.cache_version}"
        )

    def test_unauthenticated_request_bypasses_cache(self):
        """
        **Feature: hybrid-cache-system, Property 13: Cache disabled bypass**
        **Validates: Requirements 1.5, 4.5**

        Test that unauthenticated requests always bypass caching.

        This test verifies that:
        1. When request.user is not authenticated
        2. The middleware processes the request
        3. request.cache_enabled is set to False
        4. request.cache_version is set to None
        """
        # Create a mock unauthenticated request
        request = self.factory.get('/api/test/')
        
        # Create an anonymous user (not authenticated)
        from django.contrib.auth.models import AnonymousUser
        request.user = AnonymousUser()

        # Process request through middleware
        self.middleware.process_request(request)

        # Verify caching is bypassed
        assert hasattr(request, 'cache_enabled'), (
            "Middleware should set cache_enabled attribute on request"
        )
        assert request.cache_enabled is False, (
            f"request.cache_enabled should be False for unauthenticated requests, "
            f"got: {request.cache_enabled}"
        )

        # Verify cache_version is None for unauthenticated requests
        assert hasattr(request, 'cache_version'), (
            "Middleware should set cache_version attribute"
        )
        assert request.cache_version is None, (
            f"cache_version should be None for unauthenticated requests, "
            f"got: {request.cache_version}"
        )

    @given(user_id=user_id_strategy)
    @settings(max_examples=30, deadline=None)
    def test_cache_toggle_updates_request_attribute(self, user_id: int):
        """
        **Feature: hybrid-cache-system, Property 13: Cache disabled bypass**
        **Validates: Requirements 4.5**

        Test that toggling cache enabled/disabled correctly updates the
        request.cache_enabled attribute across multiple requests.

        This property verifies that:
        1. Cache can be toggled on/off for a user
        2. Each request reflects the current cache state
        3. The middleware correctly reads the updated state
        """
        # Create a test user
        user, _ = User.objects.get_or_create(
            id=user_id,
            defaults={
                'username': f'testuser_{user_id}',
                'email': f'test_{user_id}@example.com',
            }
        )

        # Test sequence: enabled -> disabled -> enabled
        states = [True, False, True]

        for expected_state in states:
            # Set cache state
            namespace_manager.set_cache_enabled(user_id, expected_state)

            # Create a new request
            request = self.factory.get('/api/test/')
            request.user = user

            # Process request through middleware
            self.middleware.process_request(request)

            # Verify request reflects current state
            assert request.cache_enabled == expected_state, (
                f"request.cache_enabled should be {expected_state}, "
                f"got: {request.cache_enabled}"
            )


class TestCacheMiddlewareHeaders(TestCase):
    """Unit tests for cache middleware response headers.

    Tests that the middleware correctly adds cache version and enabled
    headers to responses.
    """

    def setUp(self):
        """Set up test fixtures."""
        self.middleware = CacheMiddleware(get_response=lambda r: None)
        self.factory = RequestFactory()
        cache.clear()

    def tearDown(self):
        """Clean up after tests."""
        cache.clear()
        User.objects.all().delete()

    def test_response_headers_added_for_authenticated_user(self):
        """Test that cache headers are added to response for authenticated users."""
        # Create a test user
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

        # Create request and set cache context
        request = self.factory.get('/api/test/')
        request.user = user
        self.middleware.process_request(request)

        # Create a mock response
        from django.http import HttpResponse
        response = HttpResponse()

        # Process response through middleware
        response = self.middleware.process_response(request, response)

        # Verify headers are present
        self.assertIn('X-Cache-Version', response)
        self.assertIn('X-Cache-Enabled', response)

        # Verify header values
        self.assertEqual(response['X-Cache-Version'], str(request.cache_version))
        self.assertEqual(response['X-Cache-Enabled'], 'true')

    def test_response_headers_reflect_disabled_cache(self):
        """Test that X-Cache-Enabled header is 'false' when cache is disabled."""
        # Create a test user
        user = User.objects.create_user(
            username='testuser2',
            email='test2@example.com',
            password='testpass123'
        )

        # Disable cache for user
        namespace_manager.set_cache_enabled(user.id, False)

        # Create request and set cache context
        request = self.factory.get('/api/test/')
        request.user = user
        self.middleware.process_request(request)

        # Create a mock response
        from django.http import HttpResponse
        response = HttpResponse()

        # Process response through middleware
        response = self.middleware.process_response(request, response)

        # Verify X-Cache-Enabled is 'false'
        self.assertEqual(response['X-Cache-Enabled'], 'false')

    def test_response_headers_not_added_for_unauthenticated_user(self):
        """Test that cache version header is not added for unauthenticated users."""
        # Create unauthenticated request
        from django.contrib.auth.models import AnonymousUser
        request = self.factory.get('/api/test/')
        request.user = AnonymousUser()
        self.middleware.process_request(request)

        # Create a mock response
        from django.http import HttpResponse
        response = HttpResponse()

        # Process response through middleware
        response = self.middleware.process_response(request, response)

        # Verify X-Cache-Version is not present (cache_version is None)
        self.assertNotIn('X-Cache-Version', response)
        # X-Cache-Enabled should still be present and 'false'
        self.assertEqual(response['X-Cache-Enabled'], 'false')
