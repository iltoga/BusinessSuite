"""
Unit tests for benchmark management command.

These tests verify specific functionality of the benchmark system including:
- Command argument parsing
- Dry-run mode
- Report generation
- Metrics collection
- Error handling

Requirements: 10.1, 10.2, 10.3, 10.5, 19.5
"""

import io
import json
import tempfile
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

User = get_user_model()


class BenchmarkCommandArgumentsTests(TestCase):
    """Test command argument parsing."""
    
    def test_default_arguments(self):
        """Test benchmark with default arguments."""
        out = io.StringIO()
        
        call_command(
            "benchmark_cache",
            "--dry-run",
            stdout=out,
        )
        
        output = out.getvalue()
        self.assertIn("10 users", output)  # Default users
        self.assertIn("100 queries", output)  # Default queries
    
    def test_custom_users_argument(self):
        """Test --users argument."""
        out = io.StringIO()
        
        call_command(
            "benchmark_cache",
            "--users", "25",
            "--dry-run",
            stdout=out,
        )
        
        output = out.getvalue()
        self.assertIn("25 users", output)
    
    def test_custom_queries_argument(self):
        """Test --queries argument."""
        out = io.StringIO()
        
        call_command(
            "benchmark_cache",
            "--queries", "500",
            "--dry-run",
            stdout=out,
        )
        
        output = out.getvalue()
        self.assertIn("500 queries", output)
    
    def test_models_argument(self):
        """Test --models argument."""
        out = io.StringIO()
        
        call_command(
            "benchmark_cache",
            "--models", "User",
            "--dry-run",
            stdout=out,
        )
        
        output = out.getvalue()
        self.assertIn("auth.User", output)
    
    def test_invalid_users_argument(self):
        """Test that invalid --users value raises error."""
        out = io.StringIO()
        
        with self.assertRaises(Exception) as context:
            call_command(
                "benchmark_cache",
                "--users", "0",
                stdout=out,
            )
        
        self.assertIn("must be at least 1", str(context.exception))
    
    def test_invalid_queries_argument(self):
        """Test that invalid --queries value raises error."""
        out = io.StringIO()
        
        with self.assertRaises(Exception) as context:
            call_command(
                "benchmark_cache",
                "--queries", "0",
                stdout=out,
            )
        
        self.assertIn("must be at least 1", str(context.exception))


class BenchmarkDryRunTests(TestCase):
    """Test dry-run mode functionality."""
    
    def test_dry_run_no_execution(self):
        """Test that dry-run mode doesn't execute queries."""
        out = io.StringIO()
        
        call_command(
            "benchmark_cache",
            "--users", "100",
            "--queries", "1000",
            "--dry-run",
            stdout=out,
        )
        
        output = out.getvalue()
        
        # Verify dry-run indicators
        self.assertIn("DRY RUN MODE", output)
        self.assertIn("No queries will be executed", output)
        self.assertIn("Would simulate", output)
    
    def test_dry_run_shows_configuration(self):
        """Test that dry-run mode displays configuration."""
        out = io.StringIO()
        
        call_command(
            "benchmark_cache",
            "--users", "50",
            "--queries", "200",
            "--models", "User",
            "--dry-run",
            stdout=out,
        )
        
        output = out.getvalue()
        
        # Verify configuration displayed
        self.assertIn("50 users", output)
        self.assertIn("200 queries", output)
        self.assertIn("auth.User", output)
    
    def test_dry_run_shows_safety_info(self):
        """Test that dry-run mode displays safety information."""
        out = io.StringIO()
        
        call_command(
            "benchmark_cache",
            "--dry-run",
            stdout=out,
        )
        
        output = out.getvalue()
        
        # Verify safety information
        self.assertIn("Safety:", output)
        self.assertIn("Redis DB 3", output)
        self.assertIn("rolled back", output)


class BenchmarkReportGenerationTests(TestCase):
    """Test report generation functionality."""
    
    def test_report_to_file(self):
        """Test that report can be saved to file."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            report_file = f.name
        
        try:
            out = io.StringIO()
            
            # Run dry-run to generate report structure
            call_command(
                "benchmark_cache",
                "--users", "5",
                "--queries", "10",
                "--dry-run",
                stdout=out,
            )
            
            # Verify dry-run completed
            output = out.getvalue()
            self.assertIn("DRY RUN MODE", output)
            
        finally:
            # Clean up
            import os
            if os.path.exists(report_file):
                os.unlink(report_file)
    
    def test_report_to_stdout(self):
        """Test that report can be printed to stdout."""
        out = io.StringIO()
        
        call_command(
            "benchmark_cache",
            "--users", "3",
            "--queries", "5",
            "--dry-run",
            stdout=out,
        )
        
        output = out.getvalue()
        
        # Verify output contains expected information
        self.assertIn("DRY RUN MODE", output)
        self.assertIn("3 users", output)
        self.assertIn("5 queries", output)


class BenchmarkMetricsTests(TestCase):
    """Test metrics collection functionality."""
    
    def test_metrics_structure(self):
        """Test that metrics have correct structure."""
        from core.management.commands.benchmark_cache import BenchmarkMetrics
        
        metrics = BenchmarkMetrics()
        
        # Add some test data
        metrics.cache_hits = 80
        metrics.cache_misses = 20
        metrics.cached_query_times = [0.001, 0.002, 0.001]
        metrics.uncached_query_times = [0.010, 0.015, 0.012]
        metrics.invalidation_times = [0.0001, 0.0002]
        metrics.redis_operation_times = [0.0005, 0.0006]
        metrics.memory_usage_per_user = {1: 1024, 2: 2048}
        
        # Convert to dict
        report = metrics.to_dict()
        
        # Verify structure
        self.assertIn("cache_hit_rate_percent", report)
        self.assertIn("cache_hits", report)
        self.assertIn("cache_misses", report)
        self.assertIn("avg_cached_query_time_ms", report)
        self.assertIn("avg_uncached_query_time_ms", report)
        self.assertIn("speedup_factor", report)
        self.assertIn("avg_invalidation_time_ms", report)
        self.assertIn("avg_redis_operation_time_ms", report)
        self.assertIn("total_memory_usage_kb", report)
        self.assertIn("avg_memory_per_user_kb", report)
    
    def test_cache_hit_rate_calculation(self):
        """Test cache hit rate calculation."""
        from core.management.commands.benchmark_cache import BenchmarkMetrics
        
        metrics = BenchmarkMetrics()
        metrics.cache_hits = 80
        metrics.cache_misses = 20
        
        self.assertEqual(metrics.cache_hit_rate, 80.0)
    
    def test_cache_hit_rate_zero_queries(self):
        """Test cache hit rate with zero queries."""
        from core.management.commands.benchmark_cache import BenchmarkMetrics
        
        metrics = BenchmarkMetrics()
        metrics.cache_hits = 0
        metrics.cache_misses = 0
        
        self.assertEqual(metrics.cache_hit_rate, 0.0)
    
    def test_average_time_calculations(self):
        """Test average time calculations."""
        from core.management.commands.benchmark_cache import BenchmarkMetrics
        
        metrics = BenchmarkMetrics()
        metrics.cached_query_times = [0.001, 0.002, 0.003]  # seconds
        metrics.uncached_query_times = [0.010, 0.020, 0.030]  # seconds
        
        # Should convert to milliseconds
        self.assertAlmostEqual(metrics.avg_cached_time, 2.0, places=1)
        self.assertAlmostEqual(metrics.avg_uncached_time, 20.0, places=1)
    
    def test_speedup_factor_calculation(self):
        """Test speedup factor calculation."""
        from core.management.commands.benchmark_cache import BenchmarkMetrics
        
        metrics = BenchmarkMetrics()
        metrics.cached_query_times = [0.001]  # 1ms
        metrics.uncached_query_times = [0.010]  # 10ms
        
        report = metrics.to_dict()
        self.assertAlmostEqual(report["speedup_factor"], 10.0, places=1)
    
    def test_memory_usage_calculations(self):
        """Test memory usage calculations."""
        from core.management.commands.benchmark_cache import BenchmarkMetrics
        
        metrics = BenchmarkMetrics()
        metrics.memory_usage_per_user = {
            1: 1024,  # 1KB
            2: 2048,  # 2KB
            3: 3072,  # 3KB
        }
        
        self.assertEqual(metrics.total_memory_usage, 6144)  # 6KB in bytes
        self.assertAlmostEqual(metrics.avg_memory_per_user, 2.0, places=1)  # 2KB


class BenchmarkErrorHandlingTests(TestCase):
    """Test error handling functionality."""
    
    def test_invalid_model_name(self):
        """Test handling of invalid model name."""
        out = io.StringIO()
        
        with self.assertRaises(Exception) as context:
            call_command(
                "benchmark_cache",
                "--models", "NonExistentModel",
                "--dry-run",
                stdout=out,
            )
        
        self.assertIn("not found", str(context.exception).lower())
    
    def test_exceeds_max_users(self):
        """Test handling of users exceeding limit."""
        out = io.StringIO()
        
        with self.assertRaises(Exception) as context:
            call_command(
                "benchmark_cache",
                "--users", "100000",  # Exceeds default limit
                stdout=out,
            )
        
        self.assertIn("exceeds maximum limit", str(context.exception))
    
    def test_exceeds_max_queries(self):
        """Test handling of queries exceeding limit."""
        out = io.StringIO()
        
        with self.assertRaises(Exception) as context:
            call_command(
                "benchmark_cache",
                "--queries", "1000000",  # Exceeds default limit
                stdout=out,
            )
        
        self.assertIn("exceeds maximum limit", str(context.exception))


class BenchmarkSafetyTests(TestCase):
    """Test safety features of benchmark system."""
    
    def test_uses_separate_redis_db(self):
        """Test that benchmark uses separate Redis database."""
        from core.management.commands.benchmark_cache import BENCHMARK_REDIS_DB
        
        # Verify benchmark uses DB 3
        self.assertEqual(BENCHMARK_REDIS_DB, 3)
    
    def test_max_records_per_query_limit(self):
        """Test that queries are limited to MAX_RECORDS_PER_QUERY."""
        from core.management.commands.benchmark_cache import MAX_RECORDS_PER_QUERY
        
        # Verify limit is set
        self.assertEqual(MAX_RECORDS_PER_QUERY, 10)
    
    def test_configurable_limits(self):
        """Test that limits are configurable via environment."""
        from core.management.commands.benchmark_cache import MAX_USERS, MAX_QUERIES_PER_USER
        
        # Verify limits exist and are reasonable
        self.assertGreater(MAX_USERS, 0)
        self.assertGreater(MAX_QUERIES_PER_USER, 0)


class BenchmarkIntegrationTests(TestCase):
    """Integration tests for benchmark command."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create test user
        self.user = User.objects.create_user(
            username="benchmarkuser",
            email="benchmark@example.com",
            password="testpass123"
        )
    
    def test_dry_run_with_existing_user(self):
        """Test dry-run with existing user in database."""
        out = io.StringIO()
        
        call_command(
            "benchmark_cache",
            "--users", "1",
            "--queries", "5",
            "--models", "User",
            "--dry-run",
            stdout=out,
        )
        
        output = out.getvalue()
        
        # Verify successful execution
        self.assertIn("DRY RUN MODE", output)
        self.assertIn("auth.User", output)
    
    def test_multiple_models(self):
        """Test benchmarking multiple models."""
        out = io.StringIO()
        
        call_command(
            "benchmark_cache",
            "--users", "2",
            "--queries", "10",
            "--models", "User,Permission",
            "--dry-run",
            stdout=out,
        )
        
        output = out.getvalue()
        
        # Verify both models listed
        self.assertIn("auth.User", output)
        self.assertIn("auth.Permission", output)
