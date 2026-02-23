"""
Unit tests for cache logging and monitoring functionality.

Tests verify that:
- Cache hit/miss events are logged correctly
- Cache invalidation events are logged
- Error logging includes stack traces
- Metrics are collected correctly
"""

import logging
from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache
from django.test import TestCase

from cache.metrics import CacheMetrics, cache_metrics
from cache.namespace import NamespaceManager, namespace_manager


class TestCacheLogging(TestCase):
    """Test cache operation logging."""
    
    def setUp(self):
        """Set up test fixtures."""
        cache.clear()
        self.namespace_manager = NamespaceManager()
    
    def tearDown(self):
        """Clean up after tests."""
        cache.clear()
    
    @patch('cache.namespace.logger')
    def test_version_init_logged(self, mock_logger):
        """Test that cache version initialization is logged."""
        user_id = 123
        
        # Get version for first time (should initialize)
        version = self.namespace_manager.get_user_version(user_id)
        
        # Verify INFO log was called for initialization
        mock_logger.info.assert_called()
        log_message = mock_logger.info.call_args[0][0]
        
        assert f"user_id={user_id}" in log_message
        assert f"version={version}" in log_message
        assert "operation=version_init" in log_message
    
    @patch('cache.namespace.logger')
    def test_version_get_logged(self, mock_logger):
        """Test that cache version retrieval is logged."""
        user_id = 456
        
        # Initialize version first
        self.namespace_manager.get_user_version(user_id)
        mock_logger.reset_mock()
        
        # Get version again (should log as retrieval)
        version = self.namespace_manager.get_user_version(user_id)
        
        # Verify DEBUG log was called
        mock_logger.debug.assert_called()
        log_message = mock_logger.debug.call_args[0][0]
        
        assert f"user_id={user_id}" in log_message
        assert f"version={version}" in log_message
        assert "operation=version_get" in log_message
    
    @patch('cache.namespace.logger')
    def test_invalidation_logged(self, mock_logger):
        """Test that cache invalidation events are logged."""
        user_id = 789
        
        # Initialize version
        old_version = self.namespace_manager.get_user_version(user_id)
        mock_logger.reset_mock()
        
        # Increment version (invalidate)
        new_version = self.namespace_manager.increment_user_version(user_id)
        
        # Verify INFO log was called
        mock_logger.info.assert_called()
        log_message = mock_logger.info.call_args[0][0]
        
        assert f"user_id={user_id}" in log_message
        assert "operation=invalidate" in log_message
        assert f"old_version={old_version}" in log_message
        assert f"new_version={new_version}" in log_message
        assert "reason=user_requested" in log_message
    
    @patch('cache.namespace.logger')
    def test_cache_enabled_change_logged(self, mock_logger):
        """Test that cache enabled status changes are logged."""
        user_id = 111
        
        # Set cache enabled
        self.namespace_manager.set_cache_enabled(user_id, False)
        
        # Verify INFO log was called
        mock_logger.info.assert_called()
        log_message = mock_logger.info.call_args[0][0]
        
        assert f"user_id={user_id}" in log_message
        assert "operation=set_enabled" in log_message
        assert "enabled=False" in log_message
    
    @patch('cache.namespace.logger')
    def test_error_logging_includes_stack_trace(self, mock_logger):
        """Test that error logging includes stack traces."""
        user_id = 222
        
        # Make cache.get raise an exception by patching the instance's cache
        with patch.object(self.namespace_manager, 'cache') as mock_cache:
            mock_cache.get.side_effect = Exception("Redis connection failed")
            mock_cache.add.side_effect = Exception("Redis connection failed")
            mock_cache.set.side_effect = Exception("Redis connection failed")
            
            # Try to get version (should log error with stack trace)
            version = self.namespace_manager.get_user_version(user_id)
            
            # Verify ERROR log was called with exc_info=True
            mock_logger.error.assert_called()
            call_args = mock_logger.error.call_args
            
            # Check that exc_info=True was passed (enables stack trace)
            assert call_args[1].get('exc_info') is True
            
            # Check error message format
            log_message = call_args[0][0]
            assert f"user_id={user_id}" in log_message
            assert "operation=version_get" in log_message
            assert "error=" in log_message


class TestCacheMetrics(TestCase):
    """Test cache metrics collection."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.metrics = CacheMetrics()
    
    def tearDown(self):
        """Clean up after tests."""
        self.metrics.reset()
    
    def test_record_cache_hit(self):
        """Test recording cache hit events."""
        user_id = 123
        
        # Record cache hit
        self.metrics.record_cache_hit(user_id=user_id)
        
        # Verify metrics
        stats = self.metrics.get_user_stats(user_id)
        assert stats['hits'] == 1
        assert stats['misses'] == 0
        assert stats['total_operations'] == 1
        assert stats['hit_rate'] == 1.0
    
    def test_record_cache_miss(self):
        """Test recording cache miss events."""
        user_id = 456
        
        # Record cache miss
        self.metrics.record_cache_miss(user_id=user_id)
        
        # Verify metrics
        stats = self.metrics.get_user_stats(user_id)
        assert stats['hits'] == 0
        assert stats['misses'] == 1
        assert stats['total_operations'] == 1
        assert stats['hit_rate'] == 0.0
    
    def test_hit_rate_calculation(self):
        """Test cache hit rate calculation."""
        user_id = 789
        
        # Record mixed hits and misses
        self.metrics.record_cache_hit(user_id=user_id)
        self.metrics.record_cache_hit(user_id=user_id)
        self.metrics.record_cache_miss(user_id=user_id)
        self.metrics.record_cache_hit(user_id=user_id)
        
        # Verify hit rate: 3 hits / 4 total = 0.75
        stats = self.metrics.get_user_stats(user_id)
        assert stats['hits'] == 3
        assert stats['misses'] == 1
        assert stats['total_operations'] == 4
        assert stats['hit_rate'] == 0.75
    
    def test_record_invalidation(self):
        """Test recording invalidation events."""
        user_id = 111
        
        # Record invalidation
        self.metrics.record_invalidation(user_id=user_id)
        
        # Verify global stats
        global_stats = self.metrics.get_global_stats()
        assert global_stats['operation_counts']['invalidation'] == 1
    
    def test_record_error(self):
        """Test recording error events."""
        # Record different error types
        self.metrics.record_error('connection')
        self.metrics.record_error('serialization')
        self.metrics.record_error('connection')
        
        # Verify error counts
        global_stats = self.metrics.get_global_stats()
        assert global_stats['error_counts']['connection'] == 2
        assert global_stats['error_counts']['serialization'] == 1
    
    def test_measure_latency(self):
        """Test latency measurement."""
        import time
        
        user_id = 222
        
        # Measure latency of an operation
        with self.metrics.measure_latency('query', user_id=user_id):
            time.sleep(0.01)  # Simulate 10ms operation
        
        # Verify latency was recorded
        stats = self.metrics.get_user_stats(user_id)
        assert stats['avg_latency_ms'] >= 10.0  # At least 10ms
        assert stats['avg_latency_ms'] < 50.0   # But not too high
        
        # Verify global latency stats
        global_stats = self.metrics.get_global_stats()
        assert 'query' in global_stats['avg_latencies']
        assert global_stats['avg_latencies']['query'] >= 10.0
    
    def test_multiple_users_isolated(self):
        """Test that metrics for different users are isolated."""
        user1 = 100
        user2 = 200
        
        # Record different metrics for each user
        self.metrics.record_cache_hit(user_id=user1)
        self.metrics.record_cache_hit(user_id=user1)
        self.metrics.record_cache_miss(user_id=user2)
        
        # Verify user 1 stats
        stats1 = self.metrics.get_user_stats(user1)
        assert stats1['hits'] == 2
        assert stats1['misses'] == 0
        assert stats1['hit_rate'] == 1.0
        
        # Verify user 2 stats
        stats2 = self.metrics.get_user_stats(user2)
        assert stats2['hits'] == 0
        assert stats2['misses'] == 1
        assert stats2['hit_rate'] == 0.0
    
    def test_global_stats(self):
        """Test global statistics aggregation."""
        # Record operations for multiple users
        self.metrics.record_cache_hit(user_id=1)
        self.metrics.record_cache_miss(user_id=1)
        self.metrics.record_cache_hit(user_id=2)
        self.metrics.record_invalidation(user_id=1)
        self.metrics.record_error('connection')
        
        # Get global stats
        global_stats = self.metrics.get_global_stats()
        
        # Verify operation counts
        assert global_stats['operation_counts']['cache_hit'] == 2
        assert global_stats['operation_counts']['cache_miss'] == 1
        assert global_stats['operation_counts']['invalidation'] == 1
        
        # Verify error counts
        assert global_stats['error_counts']['connection'] == 1
        
        # Verify user count
        assert global_stats['total_users'] == 2
    
    def test_reset_metrics(self):
        """Test resetting all metrics."""
        # Record some metrics
        self.metrics.record_cache_hit(user_id=123)
        self.metrics.record_cache_miss(user_id=456)
        self.metrics.record_error('connection')
        
        # Reset
        self.metrics.reset()
        
        # Verify all metrics are cleared
        stats = self.metrics.get_user_stats(123)
        assert stats['total_operations'] == 0
        
        global_stats = self.metrics.get_global_stats()
        assert len(global_stats['operation_counts']) == 0
        assert len(global_stats['error_counts']) == 0
        assert global_stats['total_users'] == 0
    
    def test_prometheus_export(self):
        """Test Prometheus format export."""
        # Record some metrics
        self.metrics.record_cache_hit(user_id=123)
        self.metrics.record_cache_miss(user_id=123)
        self.metrics.record_error('connection')
        
        # Export to Prometheus format
        prometheus_output = self.metrics.export_prometheus()
        
        # Verify format
        assert isinstance(prometheus_output, str)
        assert 'cache_operations_total' in prometheus_output
        assert 'cache_errors_total' in prometheus_output
        assert 'cache_hit_rate' in prometheus_output
        
        # Verify values are present
        assert 'operation="cache_hit"' in prometheus_output
        assert 'operation="cache_miss"' in prometheus_output
        assert 'error_type="connection"' in prometheus_output
        assert 'user_id="123"' in prometheus_output


class TestIntegratedLoggingAndMetrics(TestCase):
    """Test integrated logging and metrics in namespace operations."""
    
    def setUp(self):
        """Set up test fixtures."""
        cache.clear()
        self.namespace_manager = NamespaceManager()
        cache_metrics.reset()
    
    def tearDown(self):
        """Clean up after tests."""
        cache.clear()
        cache_metrics.reset()
    
    @patch('cache.namespace.logger')
    def test_invalidation_logs_and_records_metrics(self, mock_logger):
        """Test that invalidation both logs and records metrics."""
        user_id = 999
        
        # Initialize version
        self.namespace_manager.get_user_version(user_id)
        mock_logger.reset_mock()
        
        # Invalidate
        self.namespace_manager.increment_user_version(user_id)
        
        # Verify logging
        mock_logger.info.assert_called()
        log_message = mock_logger.info.call_args[0][0]
        assert "operation=invalidate" in log_message
        
        # Verify metrics
        global_stats = cache_metrics.get_global_stats()
        assert global_stats['operation_counts']['invalidation'] == 1
    
    @patch('cache.namespace.logger')
    def test_error_logs_and_records_metrics(self, mock_logger):
        """Test that errors both log and record metrics."""
        user_id = 888
        
        # Make cache operations fail
        with patch.object(self.namespace_manager, 'cache') as mock_cache:
            mock_cache.get.side_effect = Exception("Redis error")
            mock_cache.add.side_effect = Exception("Redis error")
            mock_cache.set.side_effect = Exception("Redis error")
            
            # Try to get version (should log error)
            version = self.namespace_manager.get_user_version(user_id)
            
            # Verify error logging with stack trace
            mock_logger.error.assert_called()
            call_args = mock_logger.error.call_args
            assert call_args[1].get('exc_info') is True


@pytest.mark.django_db
class TestLoggingFormat:
    """Test that log messages follow the specified format."""
    
    def test_log_format_includes_required_fields(self):
        """Test that log messages include user_id, cache_key, and operation."""
        namespace_manager = NamespaceManager()
        
        with patch('cache.namespace.logger') as mock_logger:
            user_id = 555
            
            # Perform operations
            namespace_manager.get_user_version(user_id)
            namespace_manager.increment_user_version(user_id)
            namespace_manager.set_cache_enabled(user_id, False)
            
            # Check all log calls
            for call in mock_logger.info.call_args_list + mock_logger.debug.call_args_list:
                log_message = call[0][0]
                
                # Verify format includes key fields
                assert "user_id=" in log_message
                assert "operation=" in log_message
    
    def test_error_log_format(self):
        """Test that error log messages include error details."""
        namespace_manager = NamespaceManager()
        
        with patch.object(namespace_manager, 'cache') as mock_cache:
            with patch('cache.namespace.logger') as mock_logger:
                mock_cache.get.side_effect = Exception("Test error")
                mock_cache.add.side_effect = Exception("Test error")
                mock_cache.set.side_effect = Exception("Test error")
                
                user_id = 666
                namespace_manager.get_user_version(user_id)
                
                # Verify error log format
                mock_logger.error.assert_called()
                error_call = mock_logger.error.call_args
                log_message = error_call[0][0]
                
                assert "user_id=" in log_message
                assert "operation=" in log_message
                assert "error=" in log_message
                assert error_call[1].get('exc_info') is True
