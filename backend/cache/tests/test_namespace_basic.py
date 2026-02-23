"""
Basic unit tests for the NamespaceManager class.

These tests verify the core functionality of the namespace manager including:
- User version management
- Cache key generation
- Cache enabled/disabled status
- Input validation
"""

import pytest
from django.core.cache import cache
from django.test import TestCase

from cache.namespace import NamespaceManager


class NamespaceManagerBasicTests(TestCase):
    """Basic unit tests for NamespaceManager."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.ns = NamespaceManager()
        # Clear cache before each test
        cache.clear()
    
    def tearDown(self):
        """Clean up after tests."""
        cache.clear()
    
    def test_get_user_version_initializes_to_one(self):
        """Test that get_user_version initializes to 1 for new users."""
        user_id = 123
        version = self.ns.get_user_version(user_id)
        self.assertEqual(version, 1)
    
    def test_get_user_version_returns_existing_version(self):
        """Test that get_user_version returns existing version."""
        user_id = 456
        # Initialize version
        self.ns.get_user_version(user_id)
        # Increment it
        self.ns.increment_user_version(user_id)
        # Should return 2
        version = self.ns.get_user_version(user_id)
        self.assertEqual(version, 2)
    
    def test_increment_user_version_increments_atomically(self):
        """Test that increment_user_version increments the version."""
        user_id = 789
        # Get initial version (should be 1)
        initial = self.ns.get_user_version(user_id)
        self.assertEqual(initial, 1)
        
        # Increment
        new_version = self.ns.increment_user_version(user_id)
        self.assertEqual(new_version, 2)
        
        # Verify it persisted
        current = self.ns.get_user_version(user_id)
        self.assertEqual(current, 2)
    
    def test_get_cache_key_prefix_format(self):
        """Test that get_cache_key_prefix returns correct format."""
        user_id = 123
        prefix = self.ns.get_cache_key_prefix(user_id)
        
        # Should match format: cache:{user_id}:v{version}:cacheops:
        self.assertTrue(prefix.startswith(f"cache:{user_id}:v"))
        self.assertTrue(prefix.endswith(":cacheops:"))
        self.assertIn(":v1:", prefix)  # First version should be 1
    
    def test_get_cache_key_prefix_includes_current_version(self):
        """Test that prefix includes the current version."""
        user_id = 456
        # Get initial prefix
        prefix1 = self.ns.get_cache_key_prefix(user_id)
        self.assertIn(":v1:", prefix1)
        
        # Increment version
        self.ns.increment_user_version(user_id)
        
        # Get new prefix
        prefix2 = self.ns.get_cache_key_prefix(user_id)
        self.assertIn(":v2:", prefix2)
        
        # Prefixes should be different
        self.assertNotEqual(prefix1, prefix2)
    
    def test_is_cache_enabled_defaults_to_true(self):
        """Test that is_cache_enabled defaults to True."""
        user_id = 123
        enabled = self.ns.is_cache_enabled(user_id)
        self.assertTrue(enabled)
    
    def test_set_cache_enabled_sets_status(self):
        """Test that set_cache_enabled changes the status."""
        user_id = 456
        
        # Disable cache
        self.ns.set_cache_enabled(user_id, False)
        self.assertFalse(self.ns.is_cache_enabled(user_id))
        
        # Enable cache
        self.ns.set_cache_enabled(user_id, True)
        self.assertTrue(self.ns.is_cache_enabled(user_id))
    
    def test_validate_user_id_rejects_non_positive(self):
        """Test that user_id validation rejects non-positive integers."""
        with self.assertRaises(ValueError):
            self.ns.get_user_version(0)
        
        with self.assertRaises(ValueError):
            self.ns.get_user_version(-1)
    
    def test_validate_user_id_rejects_non_integer(self):
        """Test that user_id validation rejects non-integers."""
        with self.assertRaises(ValueError):
            self.ns.get_user_version("123")
        
        with self.assertRaises(ValueError):
            self.ns.get_user_version(123.5)
    
    def test_generate_cache_key_format(self):
        """Test that generate_cache_key returns correct format."""
        user_id = 123
        query_hash = "abc123def456"
        
        key = self.ns.generate_cache_key(user_id, query_hash)
        
        # Should match format: cache:{user_id}:v{version}:cacheops:{query_hash}
        self.assertTrue(key.startswith(f"cache:{user_id}:v"))
        self.assertTrue(key.endswith(f":cacheops:{query_hash}"))
    
    def test_generate_cache_key_validates_query_hash(self):
        """Test that generate_cache_key validates query hash."""
        user_id = 123
        
        # Valid hexadecimal
        valid_hash = "abc123def456"
        key = self.ns.generate_cache_key(user_id, valid_hash)
        self.assertIsNotNone(key)
        
        # Invalid: contains non-hex characters
        with self.assertRaises(ValueError):
            self.ns.generate_cache_key(user_id, "xyz123")
        
        # Invalid: empty string
        with self.assertRaises(ValueError):
            self.ns.generate_cache_key(user_id, "")
    
    def test_user_isolation(self):
        """Test that different users get different cache keys."""
        user1_id = 123
        user2_id = 456
        query_hash = "abc123def456"
        
        key1 = self.ns.generate_cache_key(user1_id, query_hash)
        key2 = self.ns.generate_cache_key(user2_id, query_hash)
        
        # Keys should be different
        self.assertNotEqual(key1, key2)
        
        # Both should contain the query hash
        self.assertIn(query_hash, key1)
        self.assertIn(query_hash, key2)
    
    def test_version_increment_invalidates_old_keys(self):
        """Test that incrementing version makes old keys inaccessible."""
        user_id = 123
        query_hash = "abc123def456"
        
        # Generate key with version 1
        key_v1 = self.ns.generate_cache_key(user_id, query_hash)
        self.assertIn(":v1:", key_v1)
        
        # Increment version
        self.ns.increment_user_version(user_id)
        
        # Generate key with version 2
        key_v2 = self.ns.generate_cache_key(user_id, query_hash)
        self.assertIn(":v2:", key_v2)
        
        # Keys should be different (old key is now inaccessible)
        self.assertNotEqual(key_v1, key_v2)
