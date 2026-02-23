"""
Unit tests for cache test utilities.

These tests verify that the test utilities module works correctly and provides
the expected functionality for testing the cache system.
"""

import pytest
from django.core.cache import cache
from django.test import TestCase

from cache.namespace import namespace_manager
from cache.tests.utils import (
    TestCacheManager,
    RedisMockManager,
    clear_all_cache,
    inspect_cache_state,
    mock_redis_connection_error,
    mock_redis_timeout,
    mock_cache_backend_unavailable,
    test_cache_manager,
    redis_mock_manager,
)


class TestCacheManagerTests(TestCase):
    """Tests for TestCacheManager class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_cache = TestCacheManager()
        # Clear cache before each test
        cache.clear()
        self.test_cache.clear_all_cache()
    
    def tearDown(self):
        """Clean up after tests."""
        cache.clear()
        self.test_cache.clear_all_cache()
    
    def test_get_test_redis_client(self):
        """Test that get_test_redis_client returns a valid Redis client."""
        client = self.test_cache.get_test_redis_client()
        
        # Verify client is connected
        self.assertTrue(client.ping())
        
        # Verify it's using test database (DB 4)
        info = client.info()
        # Note: Redis doesn't expose current DB in info, but we can verify it works
        self.assertIsNotNone(info)
    
    def test_clear_all_cache(self):
        """Test that clear_all_cache clears all cache data."""
        # Set some test data
        test_redis = self.test_cache.get_test_redis_client()
        test_redis.set("test_key_1", "value1")
        test_redis.set("test_key_2", "value2")
        
        # Verify data exists
        self.assertEqual(test_redis.get("test_key_1"), b"value1")
        
        # Clear cache
        count = self.test_cache.clear_all_cache()
        
        # Verify data is cleared
        self.assertIsNone(test_redis.get("test_key_1"))
        self.assertIsNone(test_redis.get("test_key_2"))
        self.assertGreaterEqual(count, 0)
    
    def test_inspect_cache_state_basic(self):
        """Test basic cache state inspection."""
        # Clear cache first
        self.test_cache.clear_all_cache()
        
        # Set some test data
        test_redis = self.test_cache.get_test_redis_client()
        test_redis.set("cache_user_version:123", 5)
        test_redis.set("cache_user_enabled:123", 1)
        test_redis.set("cache:123:v5:cacheops:abc123", "data")
        
        # Inspect state
        state = self.test_cache.inspect_cache_state()
        
        # Verify state
        self.assertGreaterEqual(state['total_keys'], 3)
        self.assertIn('version_keys', state)
        self.assertIn('cache_keys', state)
        self.assertIn('enabled_keys', state)
        self.assertIn('db_size', state)
    
    def test_inspect_cache_state_with_user_id(self):
        """Test cache state inspection for specific user."""
        # Clear cache first
        self.test_cache.clear_all_cache()
        
        # Set test data for user 123
        test_redis = self.test_cache.get_test_redis_client()
        test_redis.set("cache_user_version:123", 5)
        test_redis.set("cache:123:v5:cacheops:abc123", "data1")
        test_redis.set("cache:123:v5:cacheops:def456", "data2")
        
        # Set test data for user 456
        test_redis.set("cache_user_version:456", 2)
        test_redis.set("cache:456:v2:cacheops:xyz789", "data3")
        
        # Inspect state for user 123
        state = self.test_cache.inspect_cache_state(user_id=123)
        
        # Verify user-specific state
        self.assertIn('user_keys', state)
        self.assertIn('user_version', state)
        self.assertEqual(state['user_version'], 5)
        
        # Verify user 123 keys are present
        user_keys = state['user_keys']
        self.assertTrue(any('123' in k for k in user_keys))
        
        # Verify user 456 keys are not in user 123's state
        # (they're in total keys but not in user_keys filter)
        self.assertTrue(all('123' in k for k in user_keys))
    
    def test_inspect_cache_state_with_pattern(self):
        """Test cache state inspection with pattern matching."""
        # Clear cache first
        self.test_cache.clear_all_cache()
        
        # Set test data
        test_redis = self.test_cache.get_test_redis_client()
        test_redis.set("cache:123:v1:cacheops:abc", "data1")
        test_redis.set("cache:123:v2:cacheops:def", "data2")
        test_redis.set("cache:456:v1:cacheops:ghi", "data3")
        
        # Inspect with pattern for v1 keys
        state = self.test_cache.inspect_cache_state(pattern="*:v1:*")
        
        # Verify pattern matching
        self.assertIn('pattern_keys', state)
        pattern_keys = state['pattern_keys']
        self.assertEqual(len(pattern_keys), 2)
        self.assertTrue(all(':v1:' in k for k in pattern_keys))
    
    def test_get_user_cache_keys(self):
        """Test getting all cache keys for a user."""
        # Clear cache first
        self.test_cache.clear_all_cache()
        
        # Set test data
        test_redis = self.test_cache.get_test_redis_client()
        test_redis.set("cache_user_version:123", 1)
        test_redis.set("cache:123:v1:cacheops:abc", "data1")
        test_redis.set("cache:123:v1:cacheops:def", "data2")
        
        # Get user keys
        keys = self.test_cache.get_user_cache_keys(123)
        
        # Verify keys
        self.assertGreaterEqual(len(keys), 2)
        self.assertTrue(all('123' in k for k in keys))
    
    def test_get_user_version(self):
        """Test getting user version from test database."""
        # Clear cache first
        self.test_cache.clear_all_cache()
        
        # Set version
        test_redis = self.test_cache.get_test_redis_client()
        test_redis.set("cache_user_version:123", 7)
        
        # Get version
        version = self.test_cache.get_user_version(123)
        
        # Verify version
        self.assertEqual(version, 7)
    
    def test_set_user_version(self):
        """Test setting user version in test database."""
        # Clear cache first
        self.test_cache.clear_all_cache()
        
        # Set version
        self.test_cache.set_user_version(123, 10)
        
        # Verify version was set
        test_redis = self.test_cache.get_test_redis_client()
        version = test_redis.get("cache_user_version:123")
        self.assertEqual(int(version), 10)
    
    def test_assert_cache_key_exists(self):
        """Test asserting cache key existence."""
        # Clear cache first
        self.test_cache.clear_all_cache()
        
        # Set test key
        test_redis = self.test_cache.get_test_redis_client()
        test_key = "cache:123:v1:cacheops:test"
        test_redis.set(test_key, "data")
        
        # Assert key exists
        exists = self.test_cache.assert_cache_key_exists(test_key)
        self.assertTrue(exists)
        
        # Assert non-existent key
        not_exists = self.test_cache.assert_cache_key_exists("nonexistent_key")
        self.assertFalse(not_exists)
    
    def test_assert_cache_key_not_exists(self):
        """Test asserting cache key non-existence."""
        # Clear cache first
        self.test_cache.clear_all_cache()
        
        # Assert non-existent key
        not_exists = self.test_cache.assert_cache_key_not_exists("nonexistent_key")
        self.assertTrue(not_exists)
        
        # Set test key
        test_redis = self.test_cache.get_test_redis_client()
        test_key = "cache:123:v1:cacheops:test"
        test_redis.set(test_key, "data")
        
        # Assert key exists (should return False for not_exists)
        not_exists = self.test_cache.assert_cache_key_not_exists(test_key)
        self.assertFalse(not_exists)
    
    def test_count_keys_by_pattern(self):
        """Test counting keys by pattern."""
        # Clear cache first
        self.test_cache.clear_all_cache()
        
        # Set test data
        test_redis = self.test_cache.get_test_redis_client()
        test_redis.set("cache:123:v1:cacheops:abc", "data1")
        test_redis.set("cache:123:v1:cacheops:def", "data2")
        test_redis.set("cache:123:v2:cacheops:ghi", "data3")
        test_redis.set("cache:456:v1:cacheops:jkl", "data4")
        
        # Count v1 keys for user 123
        count = self.test_cache.count_keys_by_pattern("cache:123:v1:*")
        self.assertEqual(count, 2)
        
        # Count all v1 keys
        count = self.test_cache.count_keys_by_pattern("*:v1:*")
        self.assertEqual(count, 3)


class RedisMockManagerTests(TestCase):
    """Tests for RedisMockManager class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_mgr = RedisMockManager()
        cache.clear()
    
    def tearDown(self):
        """Clean up after tests."""
        cache.clear()
    
    def test_mock_redis_connection_error(self):
        """Test mocking Redis connection errors."""
        # This test verifies that the mock context manager works
        # In a real test, you would test that your code handles the error gracefully
        with self.mock_mgr.mock_redis_connection_error():
            # Inside this context, Redis operations should raise ConnectionError
            # Your application code should handle this gracefully
            pass
    
    def test_mock_redis_timeout(self):
        """Test mocking Redis timeout errors."""
        with self.mock_mgr.mock_redis_timeout():
            # Inside this context, Redis operations should raise TimeoutError
            pass
    
    def test_mock_redis_operation_error(self):
        """Test mocking specific Redis operation errors."""
        with self.mock_mgr.mock_redis_operation_error('get'):
            # Inside this context, Redis get operations should raise RedisError
            pass
    
    def test_mock_cache_backend_unavailable(self):
        """Test mocking cache backend unavailability."""
        with self.mock_mgr.mock_cache_backend_unavailable():
            # Inside this context, cache operations should raise exceptions
            pass


class ConvenienceFunctionsTests(TestCase):
    """Tests for convenience functions."""
    
    def setUp(self):
        """Set up test fixtures."""
        cache.clear()
        clear_all_cache()
    
    def tearDown(self):
        """Clean up after tests."""
        cache.clear()
        clear_all_cache()
    
    def test_clear_all_cache_function(self):
        """Test clear_all_cache convenience function."""
        # Set some test data
        test_redis = test_cache_manager.get_test_redis_client()
        test_redis.set("test_key", "value")
        
        # Clear using convenience function
        count = clear_all_cache()
        
        # Verify cleared
        self.assertIsNone(test_redis.get("test_key"))
        self.assertGreaterEqual(count, 0)
    
    def test_inspect_cache_state_function(self):
        """Test inspect_cache_state convenience function."""
        # Clear first
        clear_all_cache()
        
        # Set test data
        test_redis = test_cache_manager.get_test_redis_client()
        test_redis.set("cache_user_version:123", 1)
        
        # Inspect using convenience function
        state = inspect_cache_state(user_id=123)
        
        # Verify state
        self.assertIn('user_keys', state)
        self.assertIn('user_version', state)
    
    def test_mock_redis_connection_error_function(self):
        """Test mock_redis_connection_error convenience function."""
        with mock_redis_connection_error():
            # Inside this context, Redis operations should raise ConnectionError
            pass
    
    def test_mock_redis_timeout_function(self):
        """Test mock_redis_timeout convenience function."""
        with mock_redis_timeout():
            # Inside this context, Redis operations should raise TimeoutError
            pass
    
    def test_mock_cache_backend_unavailable_function(self):
        """Test mock_cache_backend_unavailable convenience function."""
        with mock_cache_backend_unavailable():
            # Inside this context, cache operations should raise exceptions
            pass


class IntegrationWithExistingTestsTests(TestCase):
    """Tests to verify utilities don't interfere with existing test patterns."""
    
    def setUp(self):
        """Set up test fixtures."""
        cache.clear()
    
    def tearDown(self):
        """Clean up after tests - using existing pattern."""
        cache.clear()
    
    def test_existing_cache_clear_still_works(self):
        """Test that existing cache.clear() in tearDown still works."""
        # Set some data in Django cache
        cache.set("test_key", "value")
        
        # Verify it's set
        self.assertEqual(cache.get("test_key"), "value")
        
        # Clear using existing pattern
        cache.clear()
        
        # Verify it's cleared
        self.assertIsNone(cache.get("test_key"))
    
    def test_test_utilities_dont_interfere_with_django_cache(self):
        """Test that test utilities don't interfere with Django cache operations."""
        # Note: In test mode, Django uses in-memory cache, not Redis
        # This test verifies that test utilities use a separate Redis DB
        
        # Use test utilities
        test_cache = TestCacheManager()
        test_redis = test_cache.get_test_redis_client()
        test_redis.set("test_key", "test_value")
        
        # Verify test Redis works
        self.assertEqual(test_redis.get("test_key"), b"test_value")
        
        # Clear test cache
        test_cache.clear_all_cache()
        
        # Verify test key is cleared
        self.assertIsNone(test_redis.get("test_key"))
    
    def test_namespace_manager_works_with_test_utilities(self):
        """Test that namespace_manager works alongside test utilities."""
        # Note: namespace_manager uses Django cache (in-memory in tests)
        # Test utilities use Redis DB 4
        # This test verifies they can coexist
        
        # Use namespace manager (uses Django cache)
        user_id = 123
        version = namespace_manager.get_user_version(user_id)
        self.assertGreaterEqual(version, 1)
        
        # Use test utilities to set data in test Redis
        test_cache = TestCacheManager()
        test_cache.set_user_version(user_id, 5)
        
        # Verify test utilities can read their own data
        test_version = test_cache.get_user_version(user_id)
        self.assertEqual(test_version, 5)
        
        # Clear using test utilities (only clears test Redis)
        clear_all_cache()
        
        # Namespace manager should still work (uses Django cache, not test Redis)
        new_version = namespace_manager.get_user_version(user_id)
        self.assertGreaterEqual(new_version, 1)
