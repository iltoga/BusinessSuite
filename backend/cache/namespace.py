"""
Namespace manager for per-user cache versioning and O(1) invalidation.

This module provides the core namespace layer that enables per-user cache isolation
and instant cache clearing through version increments. It generates cache keys in the
format: cache:{user_id}:v{version}:cacheops:{query_hash}

Key Features:
- Per-user cache versioning for O(1) invalidation
- Input validation and sanitization for security
- Separate namespace prefix to avoid conflicts with existing cache usage
- Atomic version increments using Redis INCR
"""

import logging
import re
from typing import Optional

from django.core.cache import cache

from cache.metrics import cache_metrics

logger = logging.getLogger(__name__)


class NamespaceManager:
    """
    Manages per-user cache namespaces and versions for O(1) cache invalidation.
    
    This class provides methods to:
    - Generate namespaced cache keys with user ID and version
    - Manage user version storage and retrieval from Redis
    - Provide O(1) cache invalidation via version increment
    - Check and set user cache enabled/disabled status
    - Validate and sanitize all cache key components
    
    Cache Key Format:
        Full key: cache:{user_id}:v{user_version}:cacheops:{query_hash}
        Version key: cache_user_version:{user_id}
        Prefix: cache:{user_id}:v{user_version}:cacheops:
    
    Example Usage:
        >>> ns = NamespaceManager()
        >>> version = ns.get_user_version(123)
        >>> prefix = ns.get_cache_key_prefix(123)
        >>> new_version = ns.increment_user_version(123)
        >>> enabled = ns.is_cache_enabled(123)
    """
    
    # Version key format: cache_user_version:{user_id}
    VERSION_KEY_PREFIX = "cache_user_version"
    
    # Cache enabled key format: cache_user_enabled:{user_id}
    ENABLED_KEY_PREFIX = "cache_user_enabled"
    
    # Cache key prefix format: cache:{user_id}:v{version}:cacheops:
    CACHE_KEY_PREFIX_FORMAT = "cache:{user_id}:v{version}:cacheops:"
    
    # Validation patterns
    QUERY_HASH_PATTERN = re.compile(r'^[a-f0-9]+$')
    
    def __init__(self):
        """Initialize the namespace manager."""
        self.cache = cache
    
    def get_user_version(self, user_id: int) -> int:
        """
        Get the current cache version for a user.
        
        If the user has no version yet, initializes it to 1 atomically.
        Uses Redis GET operation followed by SET NX for initialization if needed.
        
        Args:
            user_id: Positive integer user ID
            
        Returns:
            Current cache version (integer >= 1)
            
        Raises:
            ValueError: If user_id is not a positive integer
            
        Example:
            >>> ns = NamespaceManager()
            >>> version = ns.get_user_version(123)
            >>> print(version)  # 1 (if first time) or current version
        """
        # Validate user_id
        self._validate_user_id(user_id)
        
        version_key = self._get_version_key(user_id)
        
        try:
            # Try to get existing version
            version = self.cache.get(version_key)
            
            if version is None:
                # Initialize version to 1 atomically using add()
                # add() only sets if key doesn't exist (atomic operation)
                self.cache.add(version_key, 1, timeout=None)
                # Retrieve the version (either our 1 or another process's value)
                version = self.cache.get(version_key)
                
                if version is None:
                    # Fallback: if still None, set it explicitly
                    self.cache.set(version_key, 1, timeout=None)
                    version = 1
                    
                logger.info(
                    f"Cache version initialized - user_id={user_id}, version={version}, "
                    f"operation=version_init"
                )
            else:
                logger.debug(
                    f"Cache version retrieved - user_id={user_id}, version={version}, "
                    f"operation=version_get"
                )
            
            return int(version)
            
        except Exception as e:
            logger.error(
                f"Cache error - user_id={user_id}, operation=version_get, "
                f"error={str(e)}",
                exc_info=True
            )
            # Return default version 1 on error
            return 1
    
    def increment_user_version(self, user_id: int) -> int:
        """
        Increment the cache version for a user, invalidating all their cache entries.
        
        This provides O(1) cache invalidation by making all previous version cache
        entries inaccessible without requiring key deletion or iteration.
        Uses Redis INCR for atomic increment operation.
        
        Args:
            user_id: Positive integer user ID
            
        Returns:
            New cache version after increment
            
        Raises:
            ValueError: If user_id is not a positive integer
            
        Example:
            >>> ns = NamespaceManager()
            >>> old_version = ns.get_user_version(123)  # Returns 5
            >>> new_version = ns.increment_user_version(123)  # Returns 6
            >>> # All cache entries with v5 are now inaccessible
        """
        # Validate user_id
        self._validate_user_id(user_id)
        
        version_key = self._get_version_key(user_id)
        
        try:
            # Measure latency
            with cache_metrics.measure_latency('invalidate', user_id=user_id):
                # Ensure version exists before incrementing
                current_version = self.get_user_version(user_id)
                
                # Use incr() for atomic increment
                # Django's cache.incr() maps to Redis INCR command
                new_version = self.cache.incr(version_key)
            
            # Record invalidation metric
            cache_metrics.record_invalidation(user_id=user_id)
            
            logger.info(
                f"Cache invalidated - user_id={user_id}, operation=invalidate, "
                f"old_version={current_version}, new_version={new_version}, "
                f"reason=user_requested"
            )
            
            return new_version
            
        except Exception as e:
            cache_metrics.record_error('invalidation')
            logger.error(
                f"Cache error - user_id={user_id}, operation=invalidate, "
                f"error={str(e)}",
                exc_info=True
            )
            # On error, try to get current version + 1
            try:
                current = self.get_user_version(user_id)
                new_version = current + 1
                self.cache.set(version_key, new_version, timeout=None)
                logger.warning(
                    f"Cache invalidation fallback - user_id={user_id}, "
                    f"operation=invalidate_fallback, old_version={current}, "
                    f"new_version={new_version}"
                )
                return new_version
            except Exception as fallback_error:
                logger.error(
                    f"Cache error - user_id={user_id}, operation=invalidate_fallback, "
                    f"error={str(fallback_error)}",
                    exc_info=True
                )
                raise
    
    def get_cache_key_prefix(self, user_id: int) -> str:
        """
        Generate the cache key prefix for a user including their current version.
        
        The prefix format is: cache:{user_id}:v{version}:cacheops:
        This prefix is prepended to all cache keys for the user, ensuring isolation
        and enabling O(1) invalidation through version increments.
        
        Args:
            user_id: Positive integer user ID
            
        Returns:
            Cache key prefix string
            
        Raises:
            ValueError: If user_id is not a positive integer
            
        Example:
            >>> ns = NamespaceManager()
            >>> prefix = ns.get_cache_key_prefix(123)
            >>> print(prefix)  # "cache:123:v5:cacheops:"
            >>> full_key = prefix + "abc123def456"
            >>> print(full_key)  # "cache:123:v5:cacheops:abc123def456"
        """
        # Validate user_id
        self._validate_user_id(user_id)
        
        # Get current version
        version = self.get_user_version(user_id)
        
        # Generate prefix
        prefix = self.CACHE_KEY_PREFIX_FORMAT.format(
            user_id=user_id,
            version=version
        )
        
        return prefix
    
    def is_cache_enabled(self, user_id: int) -> bool:
        """
        Check if caching is enabled for a user.
        
        Args:
            user_id: Positive integer user ID
            
        Returns:
            True if caching is enabled, False otherwise
            Defaults to True if not explicitly set
            
        Raises:
            ValueError: If user_id is not a positive integer
            
        Example:
            >>> ns = NamespaceManager()
            >>> if ns.is_cache_enabled(123):
            ...     # Use cache
            ... else:
            ...     # Bypass cache
        """
        # Validate user_id
        self._validate_user_id(user_id)
        
        enabled_key = self._get_enabled_key(user_id)
        
        try:
            # Get enabled status, default to True if not set
            enabled = self.cache.get(enabled_key)
            
            if enabled is None:
                # Default to enabled
                return True
            
            return bool(enabled)
            
        except Exception as e:
            logger.error(
                f"Error checking cache enabled status for user {user_id}: {e}",
                exc_info=True
            )
            # Default to enabled on error
            return True
    
    def set_cache_enabled(self, user_id: int, enabled: bool) -> None:
        """
        Set whether caching is enabled for a user.
        
        When caching is disabled for a user, all cache operations should be
        bypassed and queries should execute directly against the database.
        
        Args:
            user_id: Positive integer user ID
            enabled: True to enable caching, False to disable
            
        Raises:
            ValueError: If user_id is not a positive integer
            
        Example:
            >>> ns = NamespaceManager()
            >>> ns.set_cache_enabled(123, False)  # Disable caching
            >>> ns.set_cache_enabled(123, True)   # Enable caching
        """
        # Validate user_id
        self._validate_user_id(user_id)
        
        enabled_key = self._get_enabled_key(user_id)
        
        try:
            # Store enabled status (no expiration)
            self.cache.set(enabled_key, enabled, timeout=None)
            
            logger.info(
                f"Cache status changed - user_id={user_id}, operation=set_enabled, "
                f"enabled={enabled}"
            )
            
        except Exception as e:
            logger.error(
                f"Cache error - user_id={user_id}, operation=set_enabled, "
                f"error={str(e)}",
                exc_info=True
            )
            raise
    
    def _get_version_key(self, user_id: int) -> str:
        """
        Generate the Redis key for storing a user's cache version.
        
        Format: cache_user_version:{user_id}
        
        Args:
            user_id: User ID (already validated)
            
        Returns:
            Version key string
        """
        return f"{self.VERSION_KEY_PREFIX}:{user_id}"
    
    def _get_enabled_key(self, user_id: int) -> str:
        """
        Generate the Redis key for storing a user's cache enabled status.
        
        Format: cache_user_enabled:{user_id}
        
        Args:
            user_id: User ID (already validated)
            
        Returns:
            Enabled key string
        """
        return f"{self.ENABLED_KEY_PREFIX}:{user_id}"
    
    def _validate_user_id(self, user_id: int) -> None:
        """
        Validate that user_id is a positive integer.
        
        Args:
            user_id: User ID to validate
            
        Raises:
            ValueError: If user_id is not a positive integer
        """
        if not isinstance(user_id, int):
            raise ValueError(f"user_id must be an integer, got {type(user_id).__name__}")
        
        if user_id <= 0:
            raise ValueError(f"user_id must be positive, got {user_id}")
    
    def _validate_query_hash(self, query_hash: str) -> None:
        """
        Validate that query_hash is a valid hexadecimal string.
        
        Args:
            query_hash: Query hash to validate
            
        Raises:
            ValueError: If query_hash is not a valid hexadecimal string
        """
        if not isinstance(query_hash, str):
            raise ValueError(
                f"query_hash must be a string, got {type(query_hash).__name__}"
            )
        
        if not query_hash:
            raise ValueError("query_hash cannot be empty")
        
        if not self.QUERY_HASH_PATTERN.match(query_hash):
            raise ValueError(
                f"query_hash must be hexadecimal (0-9, a-f), got: {query_hash}"
            )
    
    def generate_cache_key(self, user_id: int, query_hash: str) -> str:
        """
        Generate a complete cache key for a user's query.
        
        Format: cache:{user_id}:v{version}:cacheops:{query_hash}
        
        This method combines the namespace prefix with the query hash to create
        a complete cache key that includes user isolation and version information.
        
        Args:
            user_id: Positive integer user ID
            query_hash: Hexadecimal query hash from cacheops
            
        Returns:
            Complete cache key string
            
        Raises:
            ValueError: If user_id or query_hash are invalid
            
        Example:
            >>> ns = NamespaceManager()
            >>> key = ns.generate_cache_key(123, "abc123def456")
            >>> print(key)  # "cache:123:v5:cacheops:abc123def456"
        """
        # Validate inputs
        self._validate_user_id(user_id)
        self._validate_query_hash(query_hash)
        
        # Get prefix with current version
        prefix = self.get_cache_key_prefix(user_id)
        
        # Combine prefix and query hash
        cache_key = f"{prefix}{query_hash}"
        
        return cache_key


# Singleton instance for easy import
namespace_manager = NamespaceManager()
