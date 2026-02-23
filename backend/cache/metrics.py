"""
Cache metrics collection for monitoring cache performance.

This module provides utilities for collecting and tracking cache metrics:
- Cache hit rate per user
- Cache operation latency
- Cache operation counts

Metrics can be integrated with Django metrics frameworks or exported for
monitoring systems like Prometheus, Datadog, etc.
"""

import logging
import time
from collections import defaultdict
from contextlib import contextmanager
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class CacheMetrics:
    """
    Collects and tracks cache performance metrics.
    
    This class provides methods to:
    - Track cache hit/miss rates per user
    - Measure cache operation latency
    - Count cache operations by type
    - Export metrics for monitoring systems
    
    Metrics are stored in memory and can be periodically exported or
    integrated with Django metrics frameworks.
    
    Example Usage:
        >>> metrics = CacheMetrics()
        >>> metrics.record_cache_hit(user_id=123)
        >>> metrics.record_cache_miss(user_id=123)
        >>> with metrics.measure_latency('query', user_id=123):
        ...     # Execute cache operation
        ...     pass
        >>> stats = metrics.get_user_stats(123)
        >>> print(stats)  # {'hit_rate': 0.5, 'total_operations': 2, ...}
    """
    
    def __init__(self):
        """Initialize the metrics collector."""
        # Per-user metrics
        self._user_hits: Dict[int, int] = defaultdict(int)
        self._user_misses: Dict[int, int] = defaultdict(int)
        self._user_latencies: Dict[int, list] = defaultdict(list)
        
        # Global metrics
        self._operation_counts: Dict[str, int] = defaultdict(int)
        self._operation_latencies: Dict[str, list] = defaultdict(list)
        
        # Error tracking
        self._error_counts: Dict[str, int] = defaultdict(int)
    
    def record_cache_hit(self, user_id: Optional[int] = None) -> None:
        """
        Record a cache hit event.
        
        Args:
            user_id: Optional user ID for per-user metrics
            
        Example:
            >>> metrics.record_cache_hit(user_id=123)
        """
        if user_id is not None:
            self._user_hits[user_id] += 1
        
        self._operation_counts['cache_hit'] += 1
        
        logger.debug(f"Metric recorded - operation=cache_hit, user_id={user_id}")
    
    def record_cache_miss(self, user_id: Optional[int] = None) -> None:
        """
        Record a cache miss event.
        
        Args:
            user_id: Optional user ID for per-user metrics
            
        Example:
            >>> metrics.record_cache_miss(user_id=123)
        """
        if user_id is not None:
            self._user_misses[user_id] += 1
        
        self._operation_counts['cache_miss'] += 1
        
        logger.debug(f"Metric recorded - operation=cache_miss, user_id={user_id}")
    
    def record_invalidation(self, user_id: Optional[int] = None) -> None:
        """
        Record a cache invalidation event.
        
        Args:
            user_id: Optional user ID for per-user metrics
            
        Example:
            >>> metrics.record_invalidation(user_id=123)
        """
        self._operation_counts['invalidation'] += 1
        
        logger.debug(f"Metric recorded - operation=invalidation, user_id={user_id}")
    
    def record_error(self, error_type: str) -> None:
        """
        Record a cache error event.
        
        Args:
            error_type: Type of error (e.g., 'connection', 'serialization')
            
        Example:
            >>> metrics.record_error('connection')
        """
        self._error_counts[error_type] += 1
        
        logger.debug(f"Metric recorded - operation=error, error_type={error_type}")
    
    @contextmanager
    def measure_latency(self, operation: str, user_id: Optional[int] = None):
        """
        Context manager to measure operation latency.
        
        Args:
            operation: Operation name (e.g., 'query', 'invalidate')
            user_id: Optional user ID for per-user metrics
            
        Yields:
            None
            
        Example:
            >>> with metrics.measure_latency('query', user_id=123):
            ...     # Execute cache operation
            ...     result = cache.get(key)
        """
        start_time = time.time()
        
        try:
            yield
        finally:
            latency_ms = (time.time() - start_time) * 1000  # Convert to milliseconds
            
            # Record latency
            self._operation_latencies[operation].append(latency_ms)
            
            if user_id is not None:
                self._user_latencies[user_id].append(latency_ms)
            
            logger.debug(
                f"Metric recorded - operation=latency, type={operation}, "
                f"user_id={user_id}, latency_ms={latency_ms:.2f}"
            )
    
    def get_user_stats(self, user_id: int) -> Dict[str, float]:
        """
        Get cache statistics for a specific user.
        
        Args:
            user_id: User ID to get stats for
            
        Returns:
            Dictionary with user cache statistics:
            - hit_rate: Cache hit rate (0.0 to 1.0)
            - total_operations: Total cache operations
            - hits: Number of cache hits
            - misses: Number of cache misses
            - avg_latency_ms: Average operation latency in milliseconds
            
        Example:
            >>> stats = metrics.get_user_stats(123)
            >>> print(f"Hit rate: {stats['hit_rate']:.2%}")
        """
        hits = self._user_hits.get(user_id, 0)
        misses = self._user_misses.get(user_id, 0)
        total = hits + misses
        
        hit_rate = hits / total if total > 0 else 0.0
        
        latencies = self._user_latencies.get(user_id, [])
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
        
        return {
            'hit_rate': hit_rate,
            'total_operations': total,
            'hits': hits,
            'misses': misses,
            'avg_latency_ms': avg_latency,
        }
    
    def get_global_stats(self) -> Dict[str, any]:
        """
        Get global cache statistics across all users.
        
        Returns:
            Dictionary with global cache statistics:
            - operation_counts: Count of each operation type
            - error_counts: Count of each error type
            - avg_latencies: Average latency per operation type
            - total_users: Number of users with cache activity
            
        Example:
            >>> stats = metrics.get_global_stats()
            >>> print(f"Total cache hits: {stats['operation_counts']['cache_hit']}")
        """
        # Calculate average latencies per operation
        avg_latencies = {}
        for operation, latencies in self._operation_latencies.items():
            avg_latencies[operation] = sum(latencies) / len(latencies) if latencies else 0.0
        
        # Count unique users
        unique_users = set(self._user_hits.keys()) | set(self._user_misses.keys())
        
        return {
            'operation_counts': dict(self._operation_counts),
            'error_counts': dict(self._error_counts),
            'avg_latencies': avg_latencies,
            'total_users': len(unique_users),
        }
    
    def reset(self) -> None:
        """
        Reset all metrics to zero.
        
        Useful for testing or periodic metric exports.
        
        Example:
            >>> metrics.reset()
        """
        self._user_hits.clear()
        self._user_misses.clear()
        self._user_latencies.clear()
        self._operation_counts.clear()
        self._operation_latencies.clear()
        self._error_counts.clear()
        
        logger.info("Cache metrics reset")
    
    def export_prometheus(self) -> str:
        """
        Export metrics in Prometheus format.
        
        Returns:
            String with metrics in Prometheus exposition format
            
        Example:
            >>> prometheus_metrics = metrics.export_prometheus()
            >>> print(prometheus_metrics)
        """
        lines = []
        
        # Operation counts
        lines.append("# HELP cache_operations_total Total number of cache operations")
        lines.append("# TYPE cache_operations_total counter")
        for operation, count in self._operation_counts.items():
            lines.append(f'cache_operations_total{{operation="{operation}"}} {count}')
        
        # Error counts
        lines.append("# HELP cache_errors_total Total number of cache errors")
        lines.append("# TYPE cache_errors_total counter")
        for error_type, count in self._error_counts.items():
            lines.append(f'cache_errors_total{{error_type="{error_type}"}} {count}')
        
        # Average latencies
        lines.append("# HELP cache_operation_latency_ms Average operation latency in milliseconds")
        lines.append("# TYPE cache_operation_latency_ms gauge")
        for operation, latencies in self._operation_latencies.items():
            if latencies:
                avg = sum(latencies) / len(latencies)
                lines.append(f'cache_operation_latency_ms{{operation="{operation}"}} {avg:.2f}')
        
        # Per-user hit rates
        lines.append("# HELP cache_hit_rate Cache hit rate per user")
        lines.append("# TYPE cache_hit_rate gauge")
        for user_id in set(self._user_hits.keys()) | set(self._user_misses.keys()):
            stats = self.get_user_stats(user_id)
            lines.append(f'cache_hit_rate{{user_id="{user_id}"}} {stats["hit_rate"]:.4f}')
        
        return '\n'.join(lines) + '\n'


# Singleton instance for easy import
cache_metrics = CacheMetrics()
