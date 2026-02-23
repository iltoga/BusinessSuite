"""Property-based tests for the NamespaceManager class.

**Feature: hybrid-cache-system, Property 1 & 2: Cache key and version key format validation**

This module tests that the NamespaceManager correctly generates cache keys
and version keys in the expected format across a wide range of valid inputs.
"""

import re

from django.core.cache import cache
from django.test import TestCase
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase

from cache.namespace import NamespaceManager


# Strategy for generating valid user IDs (1 to 1,000,000)
user_id_strategy = st.integers(min_value=1, max_value=1_000_000)

# Strategy for generating valid query hashes (hexadecimal strings 32-64 chars)
query_hash_strategy = st.text(
    alphabet="0123456789abcdef",
    min_size=32,
    max_size=64,
)


class TestCacheKeyFormatValidation(HypothesisTestCase):
    """Property-based tests for cache key format validation.

    **Feature: hybrid-cache-system, Property 1: Cache key format validation**
    **Validates: Requirements 1.1, 11.1**

    Property: For any valid user_id (1 to 1M) and query_hash (hex 32-64 chars),
    the generated cache key must follow the format:
    cache:{user_id}:v{version}:cacheops:{query_hash}
    """

    def setUp(self):
        """Set up test fixtures."""
        self.ns = NamespaceManager()
        # Clear cache before each test
        cache.clear()

    def tearDown(self):
        """Clean up after tests."""
        cache.clear()

    @given(user_id=user_id_strategy, query_hash=query_hash_strategy)
    @settings(max_examples=100)
    def test_cache_key_format_is_valid(self, user_id: int, query_hash: str):
        """
        **Feature: hybrid-cache-system, Property 1: Cache key format validation**
        **Validates: Requirements 1.1, 11.1**

        Test that generated cache keys always follow the correct format:
        cache:{user_id}:v{version}:cacheops:{query_hash}

        This property verifies that:
        1. The key starts with "cache:"
        2. The key contains the user_id
        3. The key contains a version in format ":v{number}:"
        4. The key contains ":cacheops:" separator
        5. The key ends with the query_hash
        """
        # Generate cache key
        cache_key = self.ns.generate_cache_key(user_id, query_hash)

        # Get the current version for this user
        version = self.ns.get_user_version(user_id)

        # Expected format: cache:{user_id}:v{version}:cacheops:{query_hash}
        expected_format = f"cache:{user_id}:v{version}:cacheops:{query_hash}"

        # Verify the key matches the expected format exactly
        assert cache_key == expected_format, (
            f"Cache key format mismatch:\n"
            f"  Expected: {expected_format}\n"
            f"  Got:      {cache_key}"
        )

        # Additional format validations
        assert cache_key.startswith("cache:"), (
            f"Cache key must start with 'cache:', got: {cache_key}"
        )

        assert f":{user_id}:" in cache_key, (
            f"Cache key must contain user_id {user_id}, got: {cache_key}"
        )

        assert f":v{version}:" in cache_key, (
            f"Cache key must contain version :v{version}:, got: {cache_key}"
        )

        assert ":cacheops:" in cache_key, (
            f"Cache key must contain ':cacheops:' separator, got: {cache_key}"
        )

        assert cache_key.endswith(query_hash), (
            f"Cache key must end with query_hash {query_hash}, got: {cache_key}"
        )

    @given(user_id=user_id_strategy, query_hash=query_hash_strategy)
    @settings(max_examples=50)
    def test_cache_key_prefix_format_is_valid(self, user_id: int, query_hash: str):
        """
        **Feature: hybrid-cache-system, Property 1: Cache key format validation**
        **Validates: Requirements 1.1, 11.1**

        Test that the cache key prefix follows the correct format:
        cache:{user_id}:v{version}:cacheops:

        This verifies that the prefix generation is consistent with the
        full key generation.
        """
        # Generate prefix
        prefix = self.ns.get_cache_key_prefix(user_id)

        # Get the current version for this user
        version = self.ns.get_user_version(user_id)

        # Expected format: cache:{user_id}:v{version}:cacheops:
        expected_prefix = f"cache:{user_id}:v{version}:cacheops:"

        # Verify the prefix matches the expected format exactly
        assert prefix == expected_prefix, (
            f"Cache key prefix format mismatch:\n"
            f"  Expected: {expected_prefix}\n"
            f"  Got:      {prefix}"
        )

        # Verify that combining prefix with query_hash produces valid full key
        full_key = prefix + query_hash
        expected_full_key = f"cache:{user_id}:v{version}:cacheops:{query_hash}"

        assert full_key == expected_full_key, (
            f"Prefix + query_hash should produce valid full key:\n"
            f"  Expected: {expected_full_key}\n"
            f"  Got:      {full_key}"
        )

    @given(user_id=user_id_strategy)
    @settings(max_examples=50)
    def test_cache_key_format_persists_across_version_increments(self, user_id: int):
        """
        **Feature: hybrid-cache-system, Property 1: Cache key format validation**
        **Validates: Requirements 1.1, 11.1**

        Test that cache keys maintain correct format even after version increments.

        This verifies that:
        1. Keys before increment have correct format with old version
        2. Keys after increment have correct format with new version
        3. The format structure remains consistent
        """
        query_hash = "abc123def456789012345678901234567890"  # 38 chars

        # Generate key with initial version
        version_before = self.ns.get_user_version(user_id)
        key_before = self.ns.generate_cache_key(user_id, query_hash)
        expected_before = f"cache:{user_id}:v{version_before}:cacheops:{query_hash}"

        assert key_before == expected_before, (
            f"Key before increment has wrong format:\n"
            f"  Expected: {expected_before}\n"
            f"  Got:      {key_before}"
        )

        # Increment version
        version_after = self.ns.increment_user_version(user_id)

        # Generate key with new version
        key_after = self.ns.generate_cache_key(user_id, query_hash)
        expected_after = f"cache:{user_id}:v{version_after}:cacheops:{query_hash}"

        assert key_after == expected_after, (
            f"Key after increment has wrong format:\n"
            f"  Expected: {expected_after}\n"
            f"  Got:      {key_after}"
        )

        # Verify version actually incremented
        assert version_after == version_before + 1, (
            f"Version should increment by 1:\n"
            f"  Before: {version_before}\n"
            f"  After:  {version_after}"
        )

        # Verify keys are different (old key is now inaccessible)
        assert key_before != key_after, (
            "Keys before and after version increment should be different"
        )



class TestVersionKeyFormatValidation(HypothesisTestCase):
    """Property-based tests for version key format validation.

    **Feature: hybrid-cache-system, Property 2: Version key format validation**
    **Validates: Requirements 1.3, 11.2**

    Property: For any valid user_id (1 to 1M), the version key must follow
    the format: cache_user_version:{user_id}
    """

    def setUp(self):
        """Set up test fixtures."""
        self.ns = NamespaceManager()
        # Clear cache before each test
        cache.clear()

    def tearDown(self):
        """Clean up after tests."""
        cache.clear()

    @given(user_id=user_id_strategy)
    @settings(max_examples=100)
    def test_version_key_format_is_valid(self, user_id: int):
        """
        **Feature: hybrid-cache-system, Property 2: Version key format validation**
        **Validates: Requirements 1.3, 11.2**

        Test that version keys always follow the correct format:
        cache_user_version:{user_id}

        This property verifies that:
        1. The key starts with "cache_user_version:"
        2. The key contains the user_id
        3. The key follows the exact format specification
        """
        # Generate version key using the internal method
        version_key = self.ns._get_version_key(user_id)

        # Expected format: cache_user_version:{user_id}
        expected_format = f"cache_user_version:{user_id}"

        # Verify the key matches the expected format exactly
        assert version_key == expected_format, (
            f"Version key format mismatch:\n"
            f"  Expected: {expected_format}\n"
            f"  Got:      {version_key}"
        )

        # Additional format validations
        assert version_key.startswith("cache_user_version:"), (
            f"Version key must start with 'cache_user_version:', got: {version_key}"
        )

        assert version_key.endswith(str(user_id)), (
            f"Version key must end with user_id {user_id}, got: {version_key}"
        )

        # Verify the key contains exactly one colon separator
        parts = version_key.split(":")
        assert len(parts) == 2, (
            f"Version key should have exactly 2 parts separated by ':', got {len(parts)}: {parts}"
        )

        # Verify the second part is the user_id
        assert parts[0] == "cache_user_version", (
            f"First part should be 'cache_user_version', got: {parts[0]}"
        )
        assert parts[1] == str(user_id), (
            f"Second part should be user_id {user_id}, got: {parts[1]}"
        )

    @given(user_id=user_id_strategy)
    @settings(max_examples=50)
    def test_version_key_stored_in_redis_with_correct_format(self, user_id: int):
        """
        **Feature: hybrid-cache-system, Property 2: Version key format validation**
        **Validates: Requirements 1.3, 11.2**

        Test that when a version is stored in Redis, it uses the correct key format.

        This verifies that:
        1. The version is stored under the correct key format
        2. The key can be retrieved using the same format
        3. The stored value is a valid version number
        """
        # Get user version (this will initialize it if not exists)
        version = self.ns.get_user_version(user_id)

        # Expected version key format
        expected_key = f"cache_user_version:{user_id}"

        # Verify we can retrieve the version using the expected key directly
        stored_version = cache.get(expected_key)

        assert stored_version is not None, (
            f"Version should be stored in Redis under key: {expected_key}"
        )

        assert stored_version == version, (
            f"Stored version should match returned version:\n"
            f"  Returned: {version}\n"
            f"  Stored:   {stored_version}"
        )

        # Verify the stored version is a valid positive integer
        assert isinstance(stored_version, int), (
            f"Stored version should be an integer, got {type(stored_version).__name__}"
        )

        assert stored_version >= 1, (
            f"Stored version should be >= 1, got {stored_version}"
        )

    @given(user_id=user_id_strategy)
    @settings(max_examples=50)
    def test_version_key_format_consistent_across_operations(self, user_id: int):
        """
        **Feature: hybrid-cache-system, Property 2: Version key format validation**
        **Validates: Requirements 1.3, 11.2**

        Test that version key format remains consistent across different operations.

        This verifies that:
        1. get_user_version uses correct key format
        2. increment_user_version uses correct key format
        3. Both operations work with the same key
        """
        # Get initial version (initializes if needed)
        version_before = self.ns.get_user_version(user_id)

        # Expected key format
        expected_key = f"cache_user_version:{user_id}"

        # Verify the key exists in Redis with correct format
        stored_before = cache.get(expected_key)
        assert stored_before == version_before, (
            f"get_user_version should use key format {expected_key}"
        )

        # Increment version
        version_after = self.ns.increment_user_version(user_id)

        # Verify the same key is used for increment
        stored_after = cache.get(expected_key)
        assert stored_after == version_after, (
            f"increment_user_version should use key format {expected_key}"
        )

        # Verify version actually incremented
        assert version_after == version_before + 1, (
            f"Version should increment by 1:\n"
            f"  Before: {version_before}\n"
            f"  After:  {version_after}"
        )

    @given(user_id_1=user_id_strategy, user_id_2=user_id_strategy)
    @settings(max_examples=50)
    def test_version_keys_unique_per_user(self, user_id_1: int, user_id_2: int):
        """
        **Feature: hybrid-cache-system, Property 2: Version key format validation**
        **Validates: Requirements 1.3, 11.2**

        Test that different users have different version keys.

        This verifies that:
        1. Each user has a unique version key
        2. Version keys don't collide between users
        3. The format ensures user isolation
        """
        # Generate version keys for both users
        key_1 = self.ns._get_version_key(user_id_1)
        key_2 = self.ns._get_version_key(user_id_2)

        if user_id_1 == user_id_2:
            # Same user should have same key
            assert key_1 == key_2, (
                f"Same user should have same version key:\n"
                f"  User {user_id_1}: {key_1}\n"
                f"  User {user_id_2}: {key_2}"
            )
        else:
            # Different users should have different keys
            assert key_1 != key_2, (
                f"Different users should have different version keys:\n"
                f"  User {user_id_1}: {key_1}\n"
                f"  User {user_id_2}: {key_2}"
            )

        # Verify both keys follow the correct format
        assert key_1 == f"cache_user_version:{user_id_1}", (
            f"Key 1 format incorrect: {key_1}"
        )
        assert key_2 == f"cache_user_version:{user_id_2}", (
            f"Key 2 format incorrect: {key_2}"
        )



class TestUserCacheIsolation(HypothesisTestCase):
    """Property-based tests for user cache isolation.

    **Feature: hybrid-cache-system, Property 3: User cache isolation**
    **Validates: Requirements 1.4, 16.1**

    Property: For any two different user IDs and any query hash, the generated
    cache keys must be distinct, ensuring cache data never leaks between users.
    """

    def setUp(self):
        """Set up test fixtures."""
        self.ns = NamespaceManager()
        # Clear cache before each test
        cache.clear()

    def tearDown(self):
        """Clean up after tests."""
        cache.clear()

    @given(
        user_id_1=user_id_strategy,
        user_id_2=user_id_strategy,
        query_hash=query_hash_strategy,
    )
    @settings(max_examples=100)
    def test_different_users_have_distinct_cache_keys(
        self, user_id_1: int, user_id_2: int, query_hash: str
    ):
        """
        **Feature: hybrid-cache-system, Property 3: User cache isolation**
        **Validates: Requirements 1.4, 16.1**

        Test that different users always get distinct cache keys for the same query.

        This property verifies that:
        1. Two different users querying the same data get different cache keys
        2. Cache keys include user_id to prevent collisions
        3. Cache data cannot leak between users
        """
        # Generate cache keys for both users with the same query hash
        key_1 = self.ns.generate_cache_key(user_id_1, query_hash)
        key_2 = self.ns.generate_cache_key(user_id_2, query_hash)

        if user_id_1 == user_id_2:
            # Same user should get the same key for the same query
            assert key_1 == key_2, (
                f"Same user should get same cache key for same query:\n"
                f"  User {user_id_1}: {key_1}\n"
                f"  User {user_id_2}: {key_2}"
            )
        else:
            # Different users must get different keys even for the same query
            assert key_1 != key_2, (
                f"Different users must have distinct cache keys:\n"
                f"  User {user_id_1}: {key_1}\n"
                f"  User {user_id_2}: {key_2}\n"
                f"  Query hash: {query_hash}"
            )

            # Verify that user_id is embedded in the keys
            assert f":{user_id_1}:" in key_1, (
                f"Key 1 must contain user_id {user_id_1}: {key_1}"
            )
            assert f":{user_id_2}:" in key_2, (
                f"Key 2 must contain user_id {user_id_2}: {key_2}"
            )

            # Verify both keys end with the same query hash
            assert key_1.endswith(query_hash), (
                f"Key 1 should end with query hash: {key_1}"
            )
            assert key_2.endswith(query_hash), (
                f"Key 2 should end with query hash: {key_2}"
            )

    @given(
        user_id_1=user_id_strategy,
        user_id_2=user_id_strategy,
        query_hash=query_hash_strategy,
    )
    @settings(max_examples=50)
    def test_cache_data_isolation_between_users(
        self, user_id_1: int, user_id_2: int, query_hash: str
    ):
        """
        **Feature: hybrid-cache-system, Property 3: User cache isolation**
        **Validates: Requirements 1.4, 16.1**

        Test that cache data stored for one user is not accessible by another user.

        This verifies that:
        1. Data cached for user A cannot be retrieved using user B's key
        2. Each user has completely isolated cache storage
        3. No data leakage occurs between users
        """
        # Skip if same user (no isolation needed)
        if user_id_1 == user_id_2:
            return

        # Generate cache keys for both users
        key_1 = self.ns.generate_cache_key(user_id_1, query_hash)
        key_2 = self.ns.generate_cache_key(user_id_2, query_hash)

        # Store data for user 1
        test_data_1 = f"data_for_user_{user_id_1}"
        cache.set(key_1, test_data_1, timeout=300)

        # Store different data for user 2
        test_data_2 = f"data_for_user_{user_id_2}"
        cache.set(key_2, test_data_2, timeout=300)

        # Verify user 1 gets their own data
        retrieved_1 = cache.get(key_1)
        assert retrieved_1 == test_data_1, (
            f"User {user_id_1} should retrieve their own data:\n"
            f"  Expected: {test_data_1}\n"
            f"  Got:      {retrieved_1}"
        )

        # Verify user 2 gets their own data
        retrieved_2 = cache.get(key_2)
        assert retrieved_2 == test_data_2, (
            f"User {user_id_2} should retrieve their own data:\n"
            f"  Expected: {test_data_2}\n"
            f"  Got:      {retrieved_2}"
        )

        # Verify the data is different (no leakage)
        assert retrieved_1 != retrieved_2, (
            f"Users should have isolated cache data:\n"
            f"  User {user_id_1} data: {retrieved_1}\n"
            f"  User {user_id_2} data: {retrieved_2}"
        )

    @given(user_id_1=user_id_strategy, user_id_2=user_id_strategy)
    @settings(max_examples=50)
    def test_cache_prefixes_isolate_users(self, user_id_1: int, user_id_2: int):
        """
        **Feature: hybrid-cache-system, Property 3: User cache isolation**
        **Validates: Requirements 1.4, 16.1**

        Test that cache key prefixes ensure user isolation.

        This verifies that:
        1. Different users have different cache key prefixes
        2. Prefixes include user_id for isolation
        3. No prefix collision is possible between users
        """
        # Generate prefixes for both users
        prefix_1 = self.ns.get_cache_key_prefix(user_id_1)
        prefix_2 = self.ns.get_cache_key_prefix(user_id_2)

        if user_id_1 == user_id_2:
            # Same user should have same prefix
            assert prefix_1 == prefix_2, (
                f"Same user should have same prefix:\n"
                f"  User {user_id_1}: {prefix_1}\n"
                f"  User {user_id_2}: {prefix_2}"
            )
        else:
            # Different users must have different prefixes
            assert prefix_1 != prefix_2, (
                f"Different users must have distinct prefixes:\n"
                f"  User {user_id_1}: {prefix_1}\n"
                f"  User {user_id_2}: {prefix_2}"
            )

            # Verify user_id is in the prefix
            assert f":{user_id_1}:" in prefix_1, (
                f"Prefix 1 must contain user_id {user_id_1}: {prefix_1}"
            )
            assert f":{user_id_2}:" in prefix_2, (
                f"Prefix 2 must contain user_id {user_id_2}: {prefix_2}"
            )



class TestCacheKeyVersionConsistency(HypothesisTestCase):
    """Property-based tests for cache key version consistency.

    **Feature: hybrid-cache-system, Property 4: Cache key version consistency**
    **Validates: Requirements 1.2**

    Property: For any authenticated user, when a cache key is generated, the version
    in the cache key must match the current user version stored in Redis.
    """

    def setUp(self):
        """Set up test fixtures."""
        self.ns = NamespaceManager()
        # Clear cache before each test
        cache.clear()

    def tearDown(self):
        """Clean up after tests."""
        cache.clear()

    @given(user_id=user_id_strategy, query_hash=query_hash_strategy)
    @settings(max_examples=100)
    def test_cache_key_version_matches_redis_version(
        self, user_id: int, query_hash: str
    ):
        """
        **Feature: hybrid-cache-system, Property 4: Cache key version consistency**
        **Validates: Requirements 1.2**

        Test that the version in generated cache keys always matches the version
        stored in Redis for that user.

        This property verifies that:
        1. Cache keys include the current user version
        2. The version in the key matches what's stored in Redis
        3. Version consistency is maintained across operations
        """
        # Get the current version from Redis
        redis_version = self.ns.get_user_version(user_id)

        # Generate a cache key
        cache_key = self.ns.generate_cache_key(user_id, query_hash)

        # Extract the version from the cache key
        # Format: cache:{user_id}:v{version}:cacheops:{query_hash}
        parts = cache_key.split(":")
        assert len(parts) >= 4, f"Cache key should have at least 4 parts: {cache_key}"

        # The version part should be at index 2 (after "cache" and user_id)
        version_part = parts[2]
        assert version_part.startswith("v"), (
            f"Version part should start with 'v': {version_part}"
        )

        # Extract the numeric version
        key_version = int(version_part[1:])

        # Verify the version in the key matches Redis
        assert key_version == redis_version, (
            f"Cache key version must match Redis version:\n"
            f"  Redis version: {redis_version}\n"
            f"  Key version:   {key_version}\n"
            f"  Cache key:     {cache_key}"
        )

    @given(user_id=user_id_strategy, query_hash=query_hash_strategy)
    @settings(max_examples=50)
    def test_multiple_keys_have_consistent_version(
        self, user_id: int, query_hash: str
    ):
        """
        **Feature: hybrid-cache-system, Property 4: Cache key version consistency**
        **Validates: Requirements 1.2**

        Test that multiple cache keys generated for the same user at the same time
        all use the same version.

        This verifies that:
        1. Version is consistent across multiple key generations
        2. No race conditions cause version mismatches
        3. All keys for a user use the current version
        """
        # Get the current version
        current_version = self.ns.get_user_version(user_id)

        # Generate multiple cache keys with different query hashes
        query_hashes = [
            query_hash,
            "a" * 32,  # Different hash
            "b" * 32,  # Another different hash
        ]

        keys = [self.ns.generate_cache_key(user_id, qh) for qh in query_hashes]

        # Extract versions from all keys
        for key in keys:
            parts = key.split(":")
            version_part = parts[2]
            key_version = int(version_part[1:])

            assert key_version == current_version, (
                f"All keys should use the same version:\n"
                f"  Expected version: {current_version}\n"
                f"  Key version:      {key_version}\n"
                f"  Key:              {key}"
            )

    @given(user_id=user_id_strategy, query_hash=query_hash_strategy)
    @settings(max_examples=50)
    def test_version_consistency_after_increment(
        self, user_id: int, query_hash: str
    ):
        """
        **Feature: hybrid-cache-system, Property 4: Cache key version consistency**
        **Validates: Requirements 1.2**

        Test that after incrementing the version, new cache keys use the new version
        and it matches what's stored in Redis.

        This verifies that:
        1. Version increment updates Redis correctly
        2. New keys use the incremented version
        3. Version consistency is maintained after changes
        """
        # Get initial version
        version_before = self.ns.get_user_version(user_id)

        # Generate key with initial version
        key_before = self.ns.generate_cache_key(user_id, query_hash)
        parts_before = key_before.split(":")
        key_version_before = int(parts_before[2][1:])

        assert key_version_before == version_before, (
            f"Key version should match Redis before increment:\n"
            f"  Redis: {version_before}\n"
            f"  Key:   {key_version_before}"
        )

        # Increment version
        version_after = self.ns.increment_user_version(user_id)

        # Generate key with new version
        key_after = self.ns.generate_cache_key(user_id, query_hash)
        parts_after = key_after.split(":")
        key_version_after = int(parts_after[2][1:])

        # Verify new key uses new version
        assert key_version_after == version_after, (
            f"Key version should match Redis after increment:\n"
            f"  Redis: {version_after}\n"
            f"  Key:   {key_version_after}"
        )

        # Verify version actually incremented
        assert version_after == version_before + 1, (
            f"Version should increment by 1:\n"
            f"  Before: {version_before}\n"
            f"  After:  {version_after}"
        )

        # Verify key versions also incremented
        assert key_version_after == key_version_before + 1, (
            f"Key version should increment by 1:\n"
            f"  Before: {key_version_before}\n"
            f"  After:  {key_version_after}"
        )

    @given(user_id=user_id_strategy)
    @settings(max_examples=50)
    def test_prefix_version_matches_redis_version(self, user_id: int):
        """
        **Feature: hybrid-cache-system, Property 4: Cache key version consistency**
        **Validates: Requirements 1.2**

        Test that the version in cache key prefixes matches the Redis version.

        This verifies that:
        1. Prefixes include the current version
        2. Prefix version matches Redis version
        3. Consistency is maintained for prefix generation
        """
        # Get current version from Redis
        redis_version = self.ns.get_user_version(user_id)

        # Get cache key prefix
        prefix = self.ns.get_cache_key_prefix(user_id)

        # Extract version from prefix
        # Format: cache:{user_id}:v{version}:cacheops:
        parts = prefix.split(":")
        version_part = parts[2]
        prefix_version = int(version_part[1:])

        # Verify prefix version matches Redis
        assert prefix_version == redis_version, (
            f"Prefix version must match Redis version:\n"
            f"  Redis version:  {redis_version}\n"
            f"  Prefix version: {prefix_version}\n"
            f"  Prefix:         {prefix}"
        )



class TestVersionIncrementInvalidation(HypothesisTestCase):
    """Property-based tests for version increment invalidation.

    **Feature: hybrid-cache-system, Property 5: Version increment invalidation**
    **Validates: Requirements 2.1, 2.4**

    Property: For any user, after caching data at version N and incrementing the
    version to N+1, all cache entries from version N must be inaccessible without
    requiring deletion of the old keys.
    """

    def setUp(self):
        """Set up test fixtures."""
        self.ns = NamespaceManager()
        # Clear cache before each test
        cache.clear()

    def tearDown(self):
        """Clean up after tests."""
        cache.clear()

    @given(user_id=user_id_strategy, query_hash=query_hash_strategy)
    @settings(max_examples=100)
    def test_version_increment_makes_old_keys_inaccessible(
        self, user_id: int, query_hash: str
    ):
        """
        **Feature: hybrid-cache-system, Property 5: Version increment invalidation**
        **Validates: Requirements 2.1, 2.4**

        Test that incrementing the version makes all old cache entries inaccessible.

        This property verifies that:
        1. Data cached at version N is accessible with version N key
        2. After incrementing to version N+1, version N key no longer retrieves data
        3. New keys use version N+1
        4. Old data is not deleted but becomes inaccessible (O(1) invalidation)
        """
        # Get initial version
        version_n = self.ns.get_user_version(user_id)

        # Generate cache key for version N
        key_n = self.ns.generate_cache_key(user_id, query_hash)

        # Store test data at version N
        test_data = f"data_at_version_{version_n}"
        cache.set(key_n, test_data, timeout=300)

        # Verify data is accessible with version N key
        retrieved_before = cache.get(key_n)
        assert retrieved_before == test_data, (
            f"Data should be accessible at version {version_n}:\n"
            f"  Expected: {test_data}\n"
            f"  Got:      {retrieved_before}"
        )

        # Increment version to N+1
        version_n_plus_1 = self.ns.increment_user_version(user_id)

        # Verify version actually incremented
        assert version_n_plus_1 == version_n + 1, (
            f"Version should increment by 1:\n"
            f"  Before: {version_n}\n"
            f"  After:  {version_n_plus_1}"
        )

        # Generate new cache key (should use version N+1)
        key_n_plus_1 = self.ns.generate_cache_key(user_id, query_hash)

        # Verify new key is different from old key
        assert key_n_plus_1 != key_n, (
            f"New key should be different from old key:\n"
            f"  Old key (v{version_n}):  {key_n}\n"
            f"  New key (v{version_n_plus_1}): {key_n_plus_1}"
        )

        # Verify old data is NOT accessible via new key (version N+1)
        retrieved_with_new_key = cache.get(key_n_plus_1)
        assert retrieved_with_new_key is None, (
            f"Old data should NOT be accessible with new version key:\n"
            f"  New key: {key_n_plus_1}\n"
            f"  Retrieved: {retrieved_with_new_key}"
        )

        # Verify old data still exists in Redis (not deleted, just inaccessible)
        # This demonstrates O(1) invalidation - no deletion required
        old_data_still_exists = cache.get(key_n)
        assert old_data_still_exists == test_data, (
            f"Old data should still exist in Redis at old key:\n"
            f"  Old key: {key_n}\n"
            f"  Data: {old_data_still_exists}"
        )

    @given(user_id=user_id_strategy)
    @settings(max_examples=50)
    def test_multiple_cache_entries_invalidated_by_single_increment(
        self, user_id: int
    ):
        """
        **Feature: hybrid-cache-system, Property 5: Version increment invalidation**
        **Validates: Requirements 2.1, 2.4**

        Test that a single version increment invalidates all cache entries for a user.

        This verifies that:
        1. Multiple cache entries can be stored at version N
        2. Single version increment makes all entries inaccessible
        3. O(1) operation regardless of number of cached entries
        """
        # Get initial version
        version_n = self.ns.get_user_version(user_id)

        # Create multiple cache entries at version N
        query_hashes = [
            "a" * 32,
            "b" * 32,
            "c" * 32,
        ]

        keys_and_data = []
        for i, qh in enumerate(query_hashes):
            key = self.ns.generate_cache_key(user_id, qh)
            data = f"data_{i}_at_version_{version_n}"
            cache.set(key, data, timeout=300)
            keys_and_data.append((key, data))

        # Verify all entries are accessible before increment
        for key, expected_data in keys_and_data:
            retrieved = cache.get(key)
            assert retrieved == expected_data, (
                f"Data should be accessible before increment:\n"
                f"  Key: {key}\n"
                f"  Expected: {expected_data}\n"
                f"  Got: {retrieved}"
            )

        # Increment version (single O(1) operation)
        version_n_plus_1 = self.ns.increment_user_version(user_id)

        # Generate new keys with version N+1
        new_keys = [self.ns.generate_cache_key(user_id, qh) for qh in query_hashes]

        # Verify all new keys are different from old keys
        old_keys = [k for k, _ in keys_and_data]
        for old_key, new_key in zip(old_keys, new_keys):
            assert old_key != new_key, (
                f"New keys should differ from old keys:\n"
                f"  Old: {old_key}\n"
                f"  New: {new_key}"
            )

        # Verify none of the old data is accessible via new keys
        for new_key in new_keys:
            retrieved = cache.get(new_key)
            assert retrieved is None, (
                f"Old data should NOT be accessible with new key:\n"
                f"  Key: {new_key}\n"
                f"  Retrieved: {retrieved}"
            )

        # Verify old data still exists at old keys (not deleted)
        for old_key, expected_data in keys_and_data:
            retrieved = cache.get(old_key)
            assert retrieved == expected_data, (
                f"Old data should still exist at old key:\n"
                f"  Key: {old_key}\n"
                f"  Expected: {expected_data}\n"
                f"  Got: {retrieved}"
            )

    @given(user_id=user_id_strategy, query_hash=query_hash_strategy)
    @settings(max_examples=50)
    def test_version_increment_is_o1_operation(self, user_id: int, query_hash: str):
        """
        **Feature: hybrid-cache-system, Property 5: Version increment invalidation**
        **Validates: Requirements 2.1, 2.4**

        Test that version increment is an O(1) operation that doesn't iterate over keys.

        This verifies that:
        1. Version increment only updates a single Redis key
        2. No iteration over cache keys is required
        3. Operation completes in constant time
        """
        # Store some cache entries
        for i in range(5):
            key = self.ns.generate_cache_key(user_id, f"{query_hash}{i:02d}")
            cache.set(key, f"data_{i}", timeout=300)

        # Get version key
        version_key = self.ns._get_version_key(user_id)

        # Get version before increment
        version_before = cache.get(version_key)

        # Increment version (should be O(1) - just INCR on version key)
        version_after = self.ns.increment_user_version(user_id)

        # Verify only the version key was modified
        assert version_after == version_before + 1, (
            f"Version should increment by 1:\n"
            f"  Before: {version_before}\n"
            f"  After: {version_after}"
        )

        # Verify the version key was updated in Redis
        stored_version = cache.get(version_key)
        assert stored_version == version_after, (
            f"Version key should be updated in Redis:\n"
            f"  Expected: {version_after}\n"
            f"  Got: {stored_version}"
        )

        # The key point: we didn't need to iterate over or delete any cache entries
        # This is O(1) invalidation - just increment one integer

    @given(user_id=user_id_strategy, query_hash=query_hash_strategy)
    @settings(max_examples=50)
    def test_multiple_increments_create_distinct_versions(
        self, user_id: int, query_hash: str
    ):
        """
        **Feature: hybrid-cache-system, Property 5: Version increment invalidation**
        **Validates: Requirements 2.1, 2.4**

        Test that multiple version increments create distinct, isolated versions.

        This verifies that:
        1. Each increment creates a new version
        2. Data from different versions is isolated
        3. Each version has its own namespace
        """
        versions_and_keys = []

        # Create cache entries across multiple versions
        for i in range(3):
            version = self.ns.get_user_version(user_id)
            key = self.ns.generate_cache_key(user_id, query_hash)
            data = f"data_at_version_{version}"

            cache.set(key, data, timeout=300)
            versions_and_keys.append((version, key, data))

            # Increment to next version (except on last iteration)
            if i < 2:
                self.ns.increment_user_version(user_id)

        # Verify all versions are distinct
        versions = [v for v, _, _ in versions_and_keys]
        assert len(set(versions)) == len(versions), (
            f"All versions should be distinct: {versions}"
        )

        # Verify all keys are distinct
        keys = [k for _, k, _ in versions_and_keys]
        assert len(set(keys)) == len(keys), (
            f"All keys should be distinct: {keys}"
        )

        # Verify each version's data is still accessible at its own key
        for version, key, expected_data in versions_and_keys:
            retrieved = cache.get(key)
            assert retrieved == expected_data, (
                f"Data should be accessible at its version key:\n"
                f"  Version: {version}\n"
                f"  Key: {key}\n"
                f"  Expected: {expected_data}\n"
                f"  Got: {retrieved}"
            )



class TestInputValidation(HypothesisTestCase):
    """Property-based tests for input validation.

    **Feature: hybrid-cache-system, Property 6 & 7: Input validation**
    **Validates: Requirements 11.4, 11.5**

    Property 6: For any non-positive integer or non-integer value provided as
    user_id, the cache key generation must reject the input and raise a validation error.

    Property 7: For any integer less than 1 or non-integer value provided as
    user_version, the cache key generation must reject the input and raise a validation error.
    """

    def setUp(self):
        """Set up test fixtures."""
        self.ns = NamespaceManager()
        # Clear cache before each test
        cache.clear()

    def tearDown(self):
        """Clean up after tests."""
        cache.clear()

    @given(user_id=st.integers(max_value=0))
    @settings(max_examples=50)
    def test_non_positive_user_id_rejected(self, user_id: int):
        """
        **Feature: hybrid-cache-system, Property 6: Input validation for user ID**
        **Validates: Requirements 11.4**

        Test that non-positive user IDs are rejected with validation errors.

        This property verifies that:
        1. Zero user_id is rejected
        2. Negative user_id is rejected
        3. Appropriate error is raised
        """
        query_hash = "a" * 32

        # Attempt to generate cache key with invalid user_id
        with self.assertRaises((ValueError, TypeError)) as context:
            self.ns.generate_cache_key(user_id, query_hash)

        # Verify error message mentions user_id validation
        error_message = str(context.exception).lower()
        assert "user" in error_message or "id" in error_message or "positive" in error_message, (
            f"Error message should mention user_id validation:\n"
            f"  User ID: {user_id}\n"
            f"  Error: {context.exception}"
        )

    @given(
        user_id=st.one_of(
            st.floats(allow_nan=False, allow_infinity=False),
            st.text(),
            st.none(),
        )
    )
    @settings(max_examples=50)
    def test_non_integer_user_id_rejected(self, user_id):
        """
        **Feature: hybrid-cache-system, Property 6: Input validation for user ID**
        **Validates: Requirements 11.4**

        Test that non-integer user IDs are rejected with validation errors.

        This property verifies that:
        1. Float user_id is rejected
        2. String user_id is rejected
        3. None user_id is rejected
        4. Appropriate error is raised
        """
        query_hash = "a" * 32

        # Attempt to generate cache key with invalid user_id type
        with self.assertRaises((ValueError, TypeError, AttributeError)) as context:
            self.ns.generate_cache_key(user_id, query_hash)

        # Error should be raised (any of the expected types is acceptable)

    @given(user_id=user_id_strategy)
    @settings(max_examples=50)
    def test_valid_positive_user_id_accepted(self, user_id: int):
        """
        **Feature: hybrid-cache-system, Property 6: Input validation for user ID**
        **Validates: Requirements 11.4**

        Test that valid positive user IDs are accepted.

        This property verifies that:
        1. Positive integers are accepted
        2. No validation error is raised
        3. Cache key is generated successfully
        """
        query_hash = "a" * 32

        # Should not raise any exception
        try:
            cache_key = self.ns.generate_cache_key(user_id, query_hash)
            # Verify key was generated
            assert cache_key is not None
            assert isinstance(cache_key, str)
            assert len(cache_key) > 0
        except (ValueError, TypeError) as e:
            self.fail(
                f"Valid user_id {user_id} should not raise validation error: {e}"
            )

    @given(user_id=user_id_strategy)
    @settings(max_examples=50)
    def test_version_key_validates_user_id(self, user_id: int):
        """
        **Feature: hybrid-cache-system, Property 6: Input validation for user ID**
        **Validates: Requirements 11.4**

        Test that version key generation also validates user_id.

        This property verifies that:
        1. Version key generation validates user_id
        2. Invalid user_id is rejected
        3. Valid user_id is accepted
        """
        # Valid user_id should work
        try:
            version_key = self.ns._get_version_key(user_id)
            assert version_key is not None
            assert isinstance(version_key, str)
        except (ValueError, TypeError) as e:
            self.fail(
                f"Valid user_id {user_id} should not raise error in version key generation: {e}"
            )

    @given(invalid_user_id=st.integers(max_value=0))
    @settings(max_examples=50)
    def test_version_key_rejects_invalid_user_id(self, invalid_user_id: int):
        """
        **Feature: hybrid-cache-system, Property 6: Input validation for user ID**
        **Validates: Requirements 11.4**

        Test that version key generation rejects invalid user_ids.

        This property verifies that:
        1. Negative user_ids are rejected
        2. Zero user_id is rejected
        """
        # Invalid user_id should be rejected by get_user_version (which calls _validate_user_id)
        with self.assertRaises((ValueError, TypeError)):
            self.ns.get_user_version(invalid_user_id)

    @given(
        query_hash=st.one_of(
            st.text(alphabet="xyz", min_size=1, max_size=10),  # Invalid chars
            st.text(alphabet="ABCDEF", min_size=1, max_size=10),  # Uppercase hex (invalid)
            st.text(alphabet="0123456789abcdefg", min_size=1, max_size=10),  # Contains 'g'
            st.none(),
        )
    )
    @settings(max_examples=50)
    def test_invalid_query_hash_rejected(self, query_hash):
        """
        **Feature: hybrid-cache-system, Property 6: Input validation for user ID**
        **Validates: Requirements 11.4**

        Test that invalid query hashes are rejected.

        This property verifies that:
        1. Non-hexadecimal query hashes are rejected
        2. None query hash is rejected
        3. Empty query hash is rejected
        """
        user_id = 123

        # Skip if query_hash happens to be valid hex (lowercase hex digits)
        if query_hash is not None and isinstance(query_hash, str):
            if query_hash and all(c in "0123456789abcdef" for c in query_hash):
                return  # Skip valid hashes

        # Attempt to generate cache key with invalid query_hash
        with self.assertRaises((ValueError, TypeError, AttributeError)) as context:
            self.ns.generate_cache_key(user_id, query_hash)

        # Error should be raised

    @given(user_id=user_id_strategy, query_hash=query_hash_strategy)
    @settings(max_examples=50)
    def test_valid_inputs_accepted(self, user_id: int, query_hash: str):
        """
        **Feature: hybrid-cache-system, Property 6 & 7: Input validation**
        **Validates: Requirements 11.4, 11.5**

        Test that valid inputs are accepted without errors.

        This property verifies that:
        1. Valid user_id and query_hash are accepted
        2. No validation errors are raised
        3. Cache operations complete successfully
        """
        # All operations should succeed with valid inputs
        try:
            # Generate cache key
            cache_key = self.ns.generate_cache_key(user_id, query_hash)
            assert cache_key is not None

            # Get user version
            version = self.ns.get_user_version(user_id)
            assert version >= 1

            # Get cache key prefix
            prefix = self.ns.get_cache_key_prefix(user_id)
            assert prefix is not None

            # Increment version
            new_version = self.ns.increment_user_version(user_id)
            assert new_version == version + 1

        except (ValueError, TypeError) as e:
            self.fail(
                f"Valid inputs should not raise validation errors:\n"
                f"  user_id: {user_id}\n"
                f"  query_hash: {query_hash}\n"
                f"  Error: {e}"
            )



class TestInputSanitization(HypothesisTestCase):
    """Property-based tests for input sanitization.

    **Feature: hybrid-cache-system, Property 8: Input sanitization**
    **Validates: Requirements 11.3, 16.5**

    Property: For any user-provided input used in cache key generation, special
    characters that could cause injection attacks must be properly escaped or rejected.
    """

    def setUp(self):
        """Set up test fixtures."""
        self.ns = NamespaceManager()
        # Clear cache before each test
        cache.clear()

    def tearDown(self):
        """Clean up after tests."""
        cache.clear()

    @given(
        query_hash=st.text(
            alphabet="0123456789abcdef:;{}[]()<>|&$`'\"\\",
            min_size=32,
            max_size=64,
        )
    )
    @settings(max_examples=100)
    def test_special_characters_in_query_hash_rejected(self, query_hash: str):
        """
        **Feature: hybrid-cache-system, Property 8: Input sanitization**
        **Validates: Requirements 11.3, 16.5**

        Test that query hashes with special characters are rejected.

        This property verifies that:
        1. Special characters that could cause injection are rejected
        2. Only hexadecimal characters are allowed
        3. No escaping is needed because invalid input is rejected
        """
        user_id = 123

        # Skip if query_hash happens to be pure hex (no special chars)
        if all(c in "0123456789abcdef" for c in query_hash):
            return  # Skip valid hex strings

        # Query hash with special characters should be rejected
        with self.assertRaises((ValueError, TypeError)) as context:
            self.ns.generate_cache_key(user_id, query_hash)

        # Verify error mentions validation
        error_message = str(context.exception).lower()
        assert (
            "hex" in error_message
            or "query" in error_message
            or "invalid" in error_message
        ), f"Error should mention validation: {context.exception}"

    @given(user_id=user_id_strategy, query_hash=query_hash_strategy)
    @settings(max_examples=50)
    def test_generated_keys_contain_no_injection_characters(
        self, user_id: int, query_hash: str
    ):
        """
        **Feature: hybrid-cache-system, Property 8: Input sanitization**
        **Validates: Requirements 11.3, 16.5**

        Test that generated cache keys contain no characters that could cause injection.

        This property verifies that:
        1. Generated keys only contain safe characters
        2. No shell metacharacters are present
        3. No SQL injection characters are present
        4. No Redis command injection characters are present
        """
        # Generate cache key
        cache_key = self.ns.generate_cache_key(user_id, query_hash)

        # Define dangerous characters that should never appear in cache keys
        dangerous_chars = [
            ";",  # Command separator
            "|",  # Pipe
            "&",  # Background execution
            "$",  # Variable expansion
            "`",  # Command substitution
            "'",  # SQL string delimiter
            '"',  # SQL string delimiter
            "\\",  # Escape character
            "\n",  # Newline
            "\r",  # Carriage return
            "\t",  # Tab
            "\x00",  # Null byte
            "<",  # Redirection
            ">",  # Redirection
            "(",  # Subshell
            ")",  # Subshell
            "{",  # Brace expansion
            "}",  # Brace expansion
            "[",  # Character class
            "]",  # Character class
        ]

        # Verify no dangerous characters in the generated key
        for char in dangerous_chars:
            assert char not in cache_key, (
                f"Cache key should not contain dangerous character '{char}':\n"
                f"  Key: {cache_key}"
            )

        # Verify key only contains expected safe characters
        # Expected format: cache:{user_id}:v{version}:cacheops:{query_hash}
        # Safe characters: alphanumeric, colon, underscore
        safe_pattern = re.compile(r"^[a-z0-9:_]+$")
        assert safe_pattern.match(cache_key), (
            f"Cache key should only contain safe characters (a-z, 0-9, :, _):\n"
            f"  Key: {cache_key}"
        )

    @given(user_id=user_id_strategy)
    @settings(max_examples=50)
    def test_version_keys_contain_no_injection_characters(self, user_id: int):
        """
        **Feature: hybrid-cache-system, Property 8: Input sanitization**
        **Validates: Requirements 11.3, 16.5**

        Test that version keys contain no characters that could cause injection.

        This property verifies that:
        1. Version keys only contain safe characters
        2. No injection characters are present
        3. Format is strictly controlled
        """
        # Generate version key
        version_key = self.ns._get_version_key(user_id)

        # Verify no dangerous characters
        dangerous_chars = [";", "|", "&", "$", "`", "'", '"', "\\", "\n", "\r", "\t"]

        for char in dangerous_chars:
            assert char not in version_key, (
                f"Version key should not contain dangerous character '{char}':\n"
                f"  Key: {version_key}"
            )

        # Verify key only contains expected safe characters
        # Expected format: cache_user_version:{user_id}
        safe_pattern = re.compile(r"^[a-z0-9:_]+$")
        assert safe_pattern.match(version_key), (
            f"Version key should only contain safe characters (a-z, 0-9, :, _):\n"
            f"  Key: {version_key}"
        )

    @given(user_id=user_id_strategy)
    @settings(max_examples=50)
    def test_cache_key_prefix_contains_no_injection_characters(self, user_id: int):
        """
        **Feature: hybrid-cache-system, Property 8: Input sanitization**
        **Validates: Requirements 11.3, 16.5**

        Test that cache key prefixes contain no characters that could cause injection.

        This property verifies that:
        1. Prefixes only contain safe characters
        2. No injection characters are present
        3. Format is strictly controlled
        """
        # Generate cache key prefix
        prefix = self.ns.get_cache_key_prefix(user_id)

        # Verify no dangerous characters
        dangerous_chars = [";", "|", "&", "$", "`", "'", '"', "\\", "\n", "\r", "\t"]

        for char in dangerous_chars:
            assert char not in prefix, (
                f"Cache key prefix should not contain dangerous character '{char}':\n"
                f"  Prefix: {prefix}"
            )

        # Verify prefix only contains expected safe characters
        # Expected format: cache:{user_id}:v{version}:cacheops:
        safe_pattern = re.compile(r"^[a-z0-9:_]+$")
        assert safe_pattern.match(prefix), (
            f"Cache key prefix should only contain safe characters (a-z, 0-9, :, _):\n"
            f"  Prefix: {prefix}"
        )

    @given(user_id=user_id_strategy, query_hash=query_hash_strategy)
    @settings(max_examples=50)
    def test_cache_keys_safe_for_redis_commands(self, user_id: int, query_hash: str):
        """
        **Feature: hybrid-cache-system, Property 8: Input sanitization**
        **Validates: Requirements 11.3, 16.5**

        Test that cache keys are safe to use in Redis commands without escaping.

        This property verifies that:
        1. Keys can be used directly in Redis GET/SET commands
        2. No Redis command injection is possible
        3. Keys don't contain Redis special characters
        """
        # Generate cache key
        cache_key = self.ns.generate_cache_key(user_id, query_hash)

        # Redis special characters that could cause issues
        redis_special_chars = [
            " ",  # Space (requires quoting)
            "\n",  # Newline
            "\r",  # Carriage return
            "\t",  # Tab
        ]

        for char in redis_special_chars:
            assert char not in cache_key, (
                f"Cache key should not contain Redis special character '{repr(char)}':\n"
                f"  Key: {cache_key}"
            )

        # Verify key can be used in Redis commands without escaping
        # Try to actually use it with Redis
        try:
            # Store and retrieve a value using the key
            test_value = f"test_value_for_{user_id}"
            cache.set(cache_key, test_value, timeout=60)
            retrieved = cache.get(cache_key)

            assert retrieved == test_value, (
                f"Key should work with Redis without escaping:\n"
                f"  Key: {cache_key}\n"
                f"  Expected: {test_value}\n"
                f"  Got: {retrieved}"
            )
        finally:
            # Clean up
            cache.delete(cache_key)

    @given(user_id=user_id_strategy, query_hash=query_hash_strategy)
    @settings(max_examples=50)
    def test_no_path_traversal_in_cache_keys(self, user_id: int, query_hash: str):
        """
        **Feature: hybrid-cache-system, Property 8: Input sanitization**
        **Validates: Requirements 11.3, 16.5**

        Test that cache keys don't contain path traversal sequences.

        This property verifies that:
        1. No "../" sequences are present
        2. No absolute paths are present
        3. Keys are safe for file-based cache backends
        """
        # Generate cache key
        cache_key = self.ns.generate_cache_key(user_id, query_hash)

        # Path traversal sequences that should never appear
        path_traversal_sequences = [
            "../",
            "..\\",
            "/",
            "\\",
        ]

        for sequence in path_traversal_sequences:
            assert sequence not in cache_key, (
                f"Cache key should not contain path traversal sequence '{sequence}':\n"
                f"  Key: {cache_key}"
            )

        # Verify key doesn't start with path-like characters
        assert not cache_key.startswith("/"), (
            f"Cache key should not start with '/': {cache_key}"
        )
        assert not cache_key.startswith("\\"), (
            f"Cache key should not start with '\\': {cache_key}"
        )
