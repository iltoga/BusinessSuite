"""
Test utilities for the hybrid cache system.

This module provides utilities for testing the cache system including:
- Test mode using Redis database 4 (separate from prod DBs)
- clear_all_cache utility for tests
- inspect_cache_state utility for tests
- Redis operation mocking utilities

Redis Database Allocation:
- DB 0: PgQueuer task queue
- DB 1: Django cache (default)
- DB 2: Cacheops
- DB 3: Benchmark system
- DB 4: Test utilities (this module)

These utilities are designed to work with the namespace layer and cacheops wrapper
without interfering with existing test tearDown cache.clear() calls.

Requirements: 19.1, 19.2, 19.3, 19.4
"""

import logging
import os
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Set
from unittest.mock import MagicMock, patch

import redis
from django.conf import settings
from django.core.cache import cache
from django.test import override_settings

logger = logging.getLogger(__name__)

# Test Redis database number (separate from production)
TEST_REDIS_DB = 4


class TestCacheManager:
    """
    Manager for test cache operations using Redis database 4.

    This class provides utilities for:
    - Switching to test Redis database
    - Clearing all cache data in tests
    - Inspecting cache state for assertions
    - Mocking Redis operations

    The test database is completely isolated from production databases to ensure
    tests don't interfere with production data or other test infrastructure.

    Example Usage:
        >>> test_cache = TestCacheManager()
        >>> test_cache.clear_all_cache()
        >>> state = test_cache.inspect_cache_state()
        >>> print(state['total_keys'])
    """

    def __init__(self):
        """Initialize the test cache manager."""
        self._test_redis_client: Optional[redis.Redis] = None
        self._original_cache_backend = None

    def get_test_redis_client(self) -> redis.Redis:
        """
        Get Redis client connected to test database (DB 4).

        This creates a separate Redis connection to database 4, ensuring complete
        isolation from production databases.

        Returns:
            Redis client connected to test database

        Example:
            >>> test_cache = TestCacheManager()
            >>> client = test_cache.get_test_redis_client()
            >>> client.ping()
            True
        """
        if self._test_redis_client is None:
            # Parse Redis URL from settings
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/1")

            # Replace database number with test DB
            if redis_url.rfind("/") > redis_url.rfind(":"):
                # URL has a database number, replace it
                test_redis_url = redis_url.rsplit("/", 1)[0] + f"/{TEST_REDIS_DB}"
            else:
                # URL doesn't have a database number, append test DB
                test_redis_url = redis_url.rstrip("/") + f"/{TEST_REDIS_DB}"

            # Create Redis client
            self._test_redis_client = redis.from_url(
                test_redis_url,
                socket_connect_timeout=5,
                socket_timeout=5,
                decode_responses=False,  # Keep binary for compatibility
            )

            logger.info(f"Connected to test Redis database {TEST_REDIS_DB}")

        return self._test_redis_client

    def clear_all_cache(self) -> int:
        """
        Clear all cache data in the test Redis database.

        This utility:
        1. Clears all keys in test Redis database (DB 4)
        2. Clears Django cache (which may use DB 1)
        3. Clears namespace version keys
        4. Clears cache enabled status keys
        5. Returns count of keys cleared

        This is safe to use in tests and won't interfere with existing
        test tearDown cache.clear() calls.

        Returns:
            Number of keys cleared

        Example:
            >>> test_cache = TestCacheManager()
            >>> count = test_cache.clear_all_cache()
            >>> print(f"Cleared {count} keys")
        """
        total_cleared = 0

        try:
            # Clear test Redis database
            test_redis = self.get_test_redis_client()

            # Get all keys in test database
            keys = test_redis.keys("*")
            if keys:
                # Delete all keys
                deleted = test_redis.delete(*keys)
                # Ensure deleted is an int
                try:
                    deleted_count = int(deleted)
                except Exception:
                    deleted_count = 0
                total_cleared += deleted_count
                logger.debug(f"Cleared {deleted_count} keys from test Redis DB {TEST_REDIS_DB}")

            # Also clear Django cache (may be in different DB)
            try:
                cache.clear()
                logger.debug("Cleared Django cache")
            except Exception as e:
                logger.warning(f"Error clearing Django cache: {e}")

            logger.info(f"Test cache cleared - total_keys={total_cleared}")

        except Exception as e:
            logger.error(f"Error clearing test cache: {e}", exc_info=True)
            raise

        return total_cleared

    def inspect_cache_state(self, user_id: Optional[int] = None, pattern: Optional[str] = None) -> Dict[str, Any]:
        """
        Inspect current cache state for testing and assertions.

        This utility provides detailed information about cache state including:
        - Total number of keys
        - Keys by type (version keys, cache keys, enabled keys)
        - User-specific keys if user_id provided
        - Keys matching pattern if pattern provided
        - Memory usage information

        Args:
            user_id: Optional user ID to filter keys
            pattern: Optional pattern to match keys (Redis pattern syntax)

        Returns:
            Dictionary with cache state information:
            {
                'total_keys': int,
                'version_keys': List[str],
                'cache_keys': List[str],
                'enabled_keys': List[str],
                'user_keys': List[str],  # if user_id provided
                'pattern_keys': List[str],  # if pattern provided
                'memory_usage': int,  # bytes
                'db_size': int,
            }

        Example:
            >>> test_cache = TestCacheManager()
            >>> # Inspect all cache state
            >>> state = test_cache.inspect_cache_state()
            >>> print(f"Total keys: {state['total_keys']}")
            >>>
            >>> # Inspect specific user's cache
            >>> user_state = test_cache.inspect_cache_state(user_id=123)
            >>> print(f"User 123 has {len(user_state['user_keys'])} keys")
            >>>
            >>> # Inspect keys matching pattern
            >>> pattern_state = test_cache.inspect_cache_state(pattern="cache:*:v1:*")
            >>> print(f"Found {len(pattern_state['pattern_keys'])} v1 keys")
        """
        try:
            test_redis = self.get_test_redis_client()

            # Get all keys
            all_keys = [key.decode() if isinstance(key, bytes) else key for key in test_redis.keys("*")]

            # Categorize keys
            version_keys = [k for k in all_keys if k.startswith("cache_user_version:")]
            enabled_keys = [k for k in all_keys if k.startswith("cache_user_enabled:")]
            cache_keys = [k for k in all_keys if k.startswith("cache:") and "cacheops" in k]

            # Build state dictionary
            state = {
                "total_keys": len(all_keys),
                "version_keys": version_keys,
                "cache_keys": cache_keys,
                "enabled_keys": enabled_keys,
                "db_size": test_redis.dbsize(),
            }

            # Add user-specific keys if user_id provided
            if user_id is not None:
                user_pattern = f"*{user_id}*"
                user_keys = [k for k in all_keys if str(user_id) in k]
                state["user_keys"] = user_keys
                state["user_version_key"] = f"cache_user_version:{user_id}"
                state["user_enabled_key"] = f"cache_user_enabled:{user_id}"

                # Get user version if exists
                version_key = f"cache_user_version:{user_id}"
                if version_key in all_keys:
                    version = test_redis.get(version_key)
                    state["user_version"] = int(version) if version else None

                # Get user enabled status if exists
                enabled_key = f"cache_user_enabled:{user_id}"
                if enabled_key in all_keys:
                    enabled = test_redis.get(enabled_key)
                    state["user_enabled"] = bool(int(enabled)) if enabled else None

            # Add pattern-matched keys if pattern provided
            if pattern is not None:
                pattern_keys = [key.decode() if isinstance(key, bytes) else key for key in test_redis.keys(pattern)]
                state["pattern_keys"] = pattern_keys

            # Get memory usage (approximate)
            try:
                info = test_redis.info("memory")
                state["memory_usage"] = info.get("used_memory", 0)
            except Exception as e:
                logger.warning(f"Could not get memory info: {e}")
                state["memory_usage"] = 0

            logger.debug(f"Cache state inspected - total_keys={state['total_keys']}")

            return state

        except Exception as e:
            logger.error(f"Error inspecting cache state: {e}", exc_info=True)
            raise

    def get_user_cache_keys(self, user_id: int) -> List[str]:
        """
        Get all cache keys for a specific user.

        Args:
            user_id: User ID to get keys for

        Returns:
            List of cache keys for the user

        Example:
            >>> test_cache = TestCacheManager()
            >>> keys = test_cache.get_user_cache_keys(123)
            >>> print(f"User 123 has {len(keys)} cache keys")
        """
        state = self.inspect_cache_state(user_id=user_id)
        return state.get("user_keys", [])

    def get_user_version(self, user_id: int) -> Optional[int]:
        """
        Get the current cache version for a user from test database.

        Args:
            user_id: User ID to get version for

        Returns:
            User's cache version or None if not set

        Example:
            >>> test_cache = TestCacheManager()
            >>> version = test_cache.get_user_version(123)
            >>> print(f"User 123 version: {version}")
        """
        try:
            test_redis = self.get_test_redis_client()
            version_key = f"cache_user_version:{user_id}"
            version = test_redis.get(version_key)
            return int(version) if version else None
        except Exception as e:
            logger.error(f"Error getting user version: {e}", exc_info=True)
            return None

    def set_user_version(self, user_id: int, version: int) -> None:
        """
        Set the cache version for a user in test database.

        Args:
            user_id: User ID to set version for
            version: Version number to set

        Example:
            >>> test_cache = TestCacheManager()
            >>> test_cache.set_user_version(123, 5)
        """
        try:
            test_redis = self.get_test_redis_client()
            version_key = f"cache_user_version:{user_id}"
            test_redis.set(version_key, version)
            logger.debug(f"Set user {user_id} version to {version}")
        except Exception as e:
            logger.error(f"Error setting user version: {e}", exc_info=True)
            raise

    def assert_cache_key_exists(self, cache_key: str) -> bool:
        """
        Assert that a cache key exists in test database.

        Args:
            cache_key: Cache key to check

        Returns:
            True if key exists, False otherwise

        Example:
            >>> test_cache = TestCacheManager()
            >>> exists = test_cache.assert_cache_key_exists("cache:123:v1:cacheops:abc123")
            >>> assert exists, "Cache key should exist"
        """
        try:
            test_redis = self.get_test_redis_client()
            # ``redis.exists`` has a generic return type in typings which can
            # confuse static checkers (ResponseT).  We just care about truthiness
            # so coerce to bool instead of comparing to an integer.  This also
            # works across redis-py versions where the return value may already
            # be a bool.
            return bool(test_redis.exists(cache_key))
        except Exception as e:
            logger.error(f"Error checking cache key existence: {e}", exc_info=True)
            return False

    def assert_cache_key_not_exists(self, cache_key: str) -> bool:
        """
        Assert that a cache key does not exist in test database.

        Args:
            cache_key: Cache key to check

        Returns:
            True if key does not exist, False otherwise

        Example:
            >>> test_cache = TestCacheManager()
            >>> not_exists = test_cache.assert_cache_key_not_exists("cache:123:v1:cacheops:xyz")
            >>> assert not_exists, "Cache key should not exist"
        """
        return not self.assert_cache_key_exists(cache_key)

    def count_keys_by_pattern(self, pattern: str) -> int:
        """
        Count keys matching a pattern in test database.

        Args:
            pattern: Redis pattern to match (e.g., "cache:123:*")

        Returns:
            Number of keys matching pattern

        Example:
            >>> test_cache = TestCacheManager()
            >>> count = test_cache.count_keys_by_pattern("cache:123:v1:*")
            >>> print(f"Found {count} v1 keys for user 123")
        """
        try:
            test_redis = self.get_test_redis_client()
            keys = test_redis.keys(pattern)
            return len(keys)
        except Exception as e:
            logger.error(f"Error counting keys by pattern: {e}", exc_info=True)
            return 0


class RedisMockManager:
    """
    Manager for mocking Redis operations in tests.

    This class provides utilities for:
    - Mocking Redis connection failures
    - Mocking Redis operation errors
    - Simulating Redis timeouts
    - Testing error handling and fallback behavior

    Example Usage:
        >>> mock_mgr = RedisMockManager()
        >>> with mock_mgr.mock_redis_connection_error():
        ...     # Test code that should handle Redis connection failure
        ...     result = some_cache_operation()
        >>> assert result is not None  # Should fallback to database
    """

    @contextmanager
    def mock_redis_connection_error(self):
        """
        Context manager to mock Redis connection errors.

        This simulates Redis being unavailable and tests that the application
        gracefully falls back to database queries.

        Yields:
            None

        Example:
            >>> mock_mgr = RedisMockManager()
            >>> with mock_mgr.mock_redis_connection_error():
            ...     # This should handle the error gracefully
            ...     result = namespace_manager.get_user_version(123)
            >>> assert result == 1  # Should return default version
        """
        with patch("redis.Redis.get", side_effect=redis.ConnectionError("Connection refused")):
            with patch("redis.Redis.set", side_effect=redis.ConnectionError("Connection refused")):
                with patch("redis.Redis.incr", side_effect=redis.ConnectionError("Connection refused")):
                    yield

    @contextmanager
    def mock_redis_timeout(self):
        """
        Context manager to mock Redis timeout errors.

        This simulates Redis operations timing out and tests that the application
        handles timeouts gracefully.

        Yields:
            None

        Example:
            >>> mock_mgr = RedisMockManager()
            >>> with mock_mgr.mock_redis_timeout():
            ...     # This should handle the timeout gracefully
            ...     result = namespace_manager.increment_user_version(123)
        """
        with patch("redis.Redis.get", side_effect=redis.TimeoutError("Operation timed out")):
            with patch("redis.Redis.set", side_effect=redis.TimeoutError("Operation timed out")):
                with patch("redis.Redis.incr", side_effect=redis.TimeoutError("Operation timed out")):
                    yield

    @contextmanager
    def mock_redis_operation_error(self, operation: str = "get"):
        """
        Context manager to mock specific Redis operation errors.

        Args:
            operation: Redis operation to mock ('get', 'set', 'incr', 'delete', etc.)

        Yields:
            None

        Example:
            >>> mock_mgr = RedisMockManager()
            >>> with mock_mgr.mock_redis_operation_error('incr'):
            ...     # This should handle the incr error gracefully
            ...     result = namespace_manager.increment_user_version(123)
        """
        error = redis.RedisError(f"Redis {operation} operation failed")
        with patch(f"redis.Redis.{operation}", side_effect=error):
            yield

    @contextmanager
    def mock_cache_backend_unavailable(self):
        """
        Context manager to mock Django cache backend being unavailable.

        This simulates the entire cache backend failing and tests that the
        application continues to function with database fallback.

        Yields:
            None

        Example:
            >>> mock_mgr = RedisMockManager()
            >>> with mock_mgr.mock_cache_backend_unavailable():
            ...     # This should bypass cache and use database
            ...     result = cacheops_wrapper.get_cached_query(MyModel.objects.all(), user_id=123)
        """
        mock_cache = MagicMock()
        mock_cache.get.side_effect = Exception("Cache backend unavailable")
        mock_cache.set.side_effect = Exception("Cache backend unavailable")
        mock_cache.add.side_effect = Exception("Cache backend unavailable")
        mock_cache.incr.side_effect = Exception("Cache backend unavailable")

        with patch("django.core.cache.cache", mock_cache):
            yield


# Singleton instances for easy import
test_cache_manager = TestCacheManager()
redis_mock_manager = RedisMockManager()


# Convenience functions for common operations
def clear_all_cache() -> int:
    """
    Clear all cache data in test database.

    Convenience function that delegates to TestCacheManager.clear_all_cache().

    Returns:
        Number of keys cleared

    Example:
        >>> from cache.tests.utils import clear_all_cache
        >>> count = clear_all_cache()
        >>> print(f"Cleared {count} keys")
    """
    return test_cache_manager.clear_all_cache()


def inspect_cache_state(user_id: Optional[int] = None, pattern: Optional[str] = None) -> Dict[str, Any]:
    """
    Inspect current cache state for testing.

    Convenience function that delegates to TestCacheManager.inspect_cache_state().

    Args:
        user_id: Optional user ID to filter keys
        pattern: Optional pattern to match keys

    Returns:
        Dictionary with cache state information

    Example:
        >>> from cache.tests.utils import inspect_cache_state
        >>> state = inspect_cache_state(user_id=123)
        >>> print(f"User 123 has {len(state['user_keys'])} keys")
    """
    return test_cache_manager.inspect_cache_state(user_id=user_id, pattern=pattern)


@contextmanager
def mock_redis_connection_error():
    """
    Context manager to mock Redis connection errors.

    Convenience function that delegates to RedisMockManager.mock_redis_connection_error().

    Example:
        >>> from cache.tests.utils import mock_redis_connection_error
        >>> with mock_redis_connection_error():
        ...     # Test code that should handle Redis failure
        ...     result = some_cache_operation()
    """
    with redis_mock_manager.mock_redis_connection_error():
        yield


@contextmanager
def mock_redis_timeout():
    """
    Context manager to mock Redis timeout errors.

    Convenience function that delegates to RedisMockManager.mock_redis_timeout().

    Example:
        >>> from cache.tests.utils import mock_redis_timeout
        >>> with mock_redis_timeout():
        ...     # Test code that should handle Redis timeout
        ...     result = some_cache_operation()
    """
    with redis_mock_manager.mock_redis_timeout():
        yield


@contextmanager
def mock_cache_backend_unavailable():
    """
    Context manager to mock cache backend being unavailable.

    Convenience function that delegates to RedisMockManager.mock_cache_backend_unavailable().

    Example:
        >>> from cache.tests.utils import mock_cache_backend_unavailable
        >>> with mock_cache_backend_unavailable():
        ...     # Test code that should fallback to database
        ...     result = some_cache_operation()
    """
    with redis_mock_manager.mock_cache_backend_unavailable():
        yield
