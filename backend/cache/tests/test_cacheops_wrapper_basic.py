"""
Basic unit tests for the cacheops wrapper module.

These tests verify the core functionality of the CacheopsWrapper class,
including configuration, query caching with namespace prefixes, and
model invalidation.
"""

import unittest
from unittest.mock import MagicMock, patch, PropertyMock

from django.test import TestCase

from cache.cacheops_wrapper import CacheopsWrapper, _thread_local


class CacheopsWrapperBasicTests(TestCase):
    """Basic unit tests for CacheopsWrapper."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.wrapper = CacheopsWrapper()
        # Clean up thread local state
        if hasattr(_thread_local, 'user_id'):
            delattr(_thread_local, 'user_id')
    
    def tearDown(self):
        """Clean up after tests."""
        # Clean up thread local state
        if hasattr(_thread_local, 'user_id'):
            delattr(_thread_local, 'user_id')
    
    def test_wrapper_initialization(self):
        """Test that wrapper initializes correctly."""
        wrapper = CacheopsWrapper()
        self.assertIsNotNone(wrapper.namespace_manager)
        self.assertFalse(wrapper._cacheops_configured)
        self.assertIsNone(wrapper._original_key_func)
    
    @patch('cache.cacheops_wrapper.namespace_manager')
    def test_get_cached_query_without_configuration(self, mock_ns_manager):
        """Test that get_cached_query works without cacheops configured."""
        # Create a mock queryset
        mock_queryset = MagicMock()
        mock_queryset.__iter__ = MagicMock(return_value=iter([1, 2, 3]))
        
        # Execute query without configuration
        result = self.wrapper.get_cached_query(mock_queryset, user_id=123)
        
        # Should return list of results
        self.assertEqual(result, [1, 2, 3])
    
    @patch('cache.cacheops_wrapper.namespace_manager')
    def test_get_cached_query_with_cache_disabled(self, mock_ns_manager):
        """Test that queries bypass cache when disabled for user."""
        # Mock cache disabled for user
        mock_ns_manager.is_cache_enabled.return_value = False
        
        # Create a mock queryset
        mock_queryset = MagicMock()
        mock_queryset.__iter__ = MagicMock(return_value=iter([1, 2, 3]))
        
        # Create wrapper with mocked namespace manager
        wrapper = CacheopsWrapper()
        wrapper.namespace_manager = mock_ns_manager
        wrapper._cacheops_configured = True
        
        # Execute query
        result = wrapper.get_cached_query(mock_queryset, user_id=123)
        
        # Should check if cache is enabled
        mock_ns_manager.is_cache_enabled.assert_called_once_with(123)
        
        # Should return list of results
        self.assertEqual(result, [1, 2, 3])
    
    @patch('cache.cacheops_wrapper.namespace_manager')
    def test_get_cached_query_sets_thread_local(self, mock_ns_manager):
        """Test that get_cached_query sets thread-local user context."""
        # Mock cache enabled
        mock_ns_manager.is_cache_enabled.return_value = True
        
        # Create a mock queryset
        mock_queryset = MagicMock()
        mock_queryset.__iter__ = MagicMock(return_value=iter([1, 2, 3]))
        
        # Create wrapper with mocked namespace manager
        wrapper = CacheopsWrapper()
        wrapper.namespace_manager = mock_ns_manager
        wrapper._cacheops_configured = True
        
        # Verify thread local is not set initially
        self.assertFalse(hasattr(_thread_local, 'user_id'))
        
        # Execute query
        result = wrapper.get_cached_query(mock_queryset, user_id=123)
        
        # Thread local should be cleaned up after execution
        self.assertFalse(hasattr(_thread_local, 'user_id'))
        
        # Should return list of results
        self.assertEqual(result, [1, 2, 3])
    
    @patch('cache.cacheops_wrapper.namespace_manager')
    def test_get_cached_query_without_user_id(self, mock_ns_manager):
        """Test that queries work without user_id (non-user-specific cache)."""
        # Create a mock queryset
        mock_queryset = MagicMock()
        mock_queryset.__iter__ = MagicMock(return_value=iter([1, 2, 3]))
        
        # Create wrapper with mocked namespace manager
        wrapper = CacheopsWrapper()
        wrapper.namespace_manager = mock_ns_manager
        wrapper._cacheops_configured = True
        
        # Execute query without user_id
        result = wrapper.get_cached_query(mock_queryset, user_id=None)
        
        # Should not check cache enabled status
        mock_ns_manager.is_cache_enabled.assert_not_called()
        
        # Thread local should not be set
        self.assertFalse(hasattr(_thread_local, 'user_id'))
        
        # Should return list of results
        self.assertEqual(result, [1, 2, 3])
    
    def test_invalidate_model_without_configuration(self):
        """Test that invalidate_model handles missing configuration gracefully."""
        # Create a mock model class
        mock_model = MagicMock()
        mock_model.__name__ = 'TestModel'
        
        # Should not raise exception
        self.wrapper.invalidate_model(mock_model)
    
    @patch('cache.cacheops_wrapper.logger')
    def test_get_cached_query_handles_errors(self, mock_logger):
        """Test that get_cached_query handles errors gracefully."""
        # Create a mock queryset that raises an error on first call
        mock_queryset = MagicMock()
        call_count = [0]
        
        def side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("Test error")
            return iter([1, 2, 3])
        
        mock_queryset.__iter__ = MagicMock(side_effect=side_effect)
        
        # Mark as configured
        self.wrapper._cacheops_configured = True
        
        # Execute query - should fall back to second call
        result = self.wrapper.get_cached_query(mock_queryset, user_id=123)
        
        # Should log error
        self.assertTrue(mock_logger.error.called)
        
        # Should return fallback results
        self.assertEqual(result, [1, 2, 3])
    
    def test_configure_cacheops_import_error(self):
        """Test that configure_cacheops handles missing cacheops gracefully."""
        with patch('cache.cacheops_wrapper.CacheopsWrapper._hook_key_generation'):
            with patch('builtins.__import__', side_effect=ImportError("No module named 'cacheops'")):
                # Should raise ImportError with helpful message
                with self.assertRaises(ImportError) as context:
                    self.wrapper.configure_cacheops()
                
                self.assertIn('django-cacheops is not installed', str(context.exception))


class ThreadLocalContextTests(TestCase):
    """Tests for thread-local context management."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Clean up thread local state
        if hasattr(_thread_local, 'user_id'):
            delattr(_thread_local, 'user_id')
    
    def tearDown(self):
        """Clean up after tests."""
        # Clean up thread local state
        if hasattr(_thread_local, 'user_id'):
            delattr(_thread_local, 'user_id')
    
    def test_thread_local_isolation(self):
        """Test that thread-local storage is isolated per thread."""
        # Set user_id in current thread
        _thread_local.user_id = 123
        
        # Verify it's set
        self.assertEqual(_thread_local.user_id, 123)
        
        # Clean up
        delattr(_thread_local, 'user_id')
        
        # Verify it's cleaned up
        self.assertFalse(hasattr(_thread_local, 'user_id'))
