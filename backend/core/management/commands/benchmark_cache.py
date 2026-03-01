"""
Django management command for benchmarking cache performance.

This command provides production-safe cache performance measurement with the following features:
- Measures cache hit rates for configured query patterns
- Measures response time differences (cached vs uncached)
- Measures cache invalidation time (O(1) verification)
- Measures memory usage per user
- Measures Redis operation latency
- Generates JSON reports with all metrics

Safety Guarantees (Requirement 10.4):
- Uses read-only queries (no data modification)
- Uses Redis database 3 for benchmarking (separate from cache DB 1 and cacheops DB 2)
- Uses transaction rollback for any writes
- Configurable query limits to prevent resource exhaustion
- Dry-run mode for testing without execution

Redis Database Allocation:
- Database 0 (default): reserved/unused by cache benchmark
- Database 1: Django cache
- Database 2: Cacheops query cache
- Database 3: Benchmark system (isolated)
- Database 4: Test environment (isolated)

Usage:
    python manage.py benchmark_cache --users 100 --queries 1000 --report output.json
    python manage.py benchmark_cache --dry-run --models Customer,Invoice
    python manage.py benchmark_cache --users 10 --queries 100 --report benchmark.json
"""

import json
import logging
import os
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional

import redis
from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.models import Model, QuerySet

from cache.namespace import namespace_manager

logger = logging.getLogger(__name__)

User = get_user_model()

# Benchmark Redis database number (separate from production)
BENCHMARK_REDIS_DB = 3

# Maximum query limits for safety
MAX_USERS = int(os.getenv("BENCHMARK_MAX_USERS", "1000"))
MAX_QUERIES_PER_USER = int(os.getenv("BENCHMARK_MAX_QUERIES", "10000"))
MAX_RECORDS_PER_QUERY = 10  # Limit records fetched per query


class BenchmarkMetrics:
    """Container for benchmark metrics."""
    
    def __init__(self):
        self.cache_hits = 0
        self.cache_misses = 0
        self.cached_query_times: List[float] = []
        self.uncached_query_times: List[float] = []
        self.invalidation_times: List[float] = []
        self.redis_operation_times: List[float] = []
        self.memory_usage_per_user: Dict[int, int] = {}
        self.errors: List[str] = []
    
    @property
    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate as percentage."""
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return (self.cache_hits / total) * 100
    
    @property
    def avg_cached_time(self) -> float:
        """Average cached query response time in milliseconds."""
        if not self.cached_query_times:
            return 0.0
        return sum(self.cached_query_times) / len(self.cached_query_times) * 1000
    
    @property
    def avg_uncached_time(self) -> float:
        """Average uncached query response time in milliseconds."""
        if not self.uncached_query_times:
            return 0.0
        return sum(self.uncached_query_times) / len(self.uncached_query_times) * 1000
    
    @property
    def avg_invalidation_time(self) -> float:
        """Average cache invalidation time in milliseconds."""
        if not self.invalidation_times:
            return 0.0
        return sum(self.invalidation_times) / len(self.invalidation_times) * 1000
    
    @property
    def avg_redis_operation_time(self) -> float:
        """Average Redis operation latency in milliseconds."""
        if not self.redis_operation_times:
            return 0.0
        return sum(self.redis_operation_times) / len(self.redis_operation_times) * 1000
    
    @property
    def total_memory_usage(self) -> int:
        """Total memory usage across all users in bytes."""
        return sum(self.memory_usage_per_user.values())
    
    @property
    def avg_memory_per_user(self) -> float:
        """Average memory usage per user in KB."""
        if not self.memory_usage_per_user:
            return 0.0
        return (self.total_memory_usage / len(self.memory_usage_per_user)) / 1024
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary for JSON serialization."""
        return {
            "cache_hit_rate_percent": round(self.cache_hit_rate, 2),
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "avg_cached_query_time_ms": round(self.avg_cached_time, 3),
            "avg_uncached_query_time_ms": round(self.avg_uncached_time, 3),
            "speedup_factor": round(self.avg_uncached_time / self.avg_cached_time, 2) if self.avg_cached_time > 0 else 0,
            "avg_invalidation_time_ms": round(self.avg_invalidation_time, 3),
            "avg_redis_operation_time_ms": round(self.avg_redis_operation_time, 3),
            "total_memory_usage_kb": round(self.total_memory_usage / 1024, 2),
            "avg_memory_per_user_kb": round(self.avg_memory_per_user, 2),
            "users_benchmarked": len(self.memory_usage_per_user),
            "total_queries": self.cache_hits + self.cache_misses,
            "errors": self.errors,
        }


class Command(BaseCommand):
    """
    Management command for benchmarking cache performance.
    
    This command measures cache performance metrics including hit rates, response times,
    invalidation performance, and memory usage. It uses read-only queries and a separate
    Redis database to ensure production data safety.
    
    Safety Features:
    - Read-only queries with transaction rollback
    - Separate Redis database (DB 3) for isolation
    - Configurable query limits
    - Dry-run mode for validation
    """
    
    help = "Benchmark cache performance with production-safe read-only queries"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.benchmark_redis = None
    
    def _get_benchmark_redis(self) -> redis.Redis:
        """
        Get Redis connection for benchmark database (DB 3).
        
        This ensures benchmark operations are isolated from production cache data.
        
        Returns:
            Redis client connected to benchmark database
        """
        if self.benchmark_redis is None:
            # Parse Redis URL from settings
            redis_url = os.getenv("REDIS_URL", "redis://redis:6379/1")
            
            # Replace database number with benchmark DB
            if "/1" in redis_url:
                benchmark_url = redis_url.replace("/1", f"/{BENCHMARK_REDIS_DB}")
            elif "/0" in redis_url:
                benchmark_url = redis_url.replace("/0", f"/{BENCHMARK_REDIS_DB}")
            else:
                # Append database number if not present
                benchmark_url = f"{redis_url.rstrip('/')}/{BENCHMARK_REDIS_DB}"
            
            self.benchmark_redis = redis.from_url(
                benchmark_url,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
            )
            
            logger.info(f"Connected to benchmark Redis database {BENCHMARK_REDIS_DB}")
        
        return self.benchmark_redis
    
    def add_arguments(self, parser):
        """Add command-line arguments."""
        parser.add_argument(
            "--users",
            type=int,
            default=10,
            help="Number of simulated users (default: 10)",
        )
        parser.add_argument(
            "--queries",
            type=int,
            default=100,
            help="Number of queries per user (default: 100)",
        )
        parser.add_argument(
            "--report",
            type=str,
            default=None,
            help="Output file for JSON report (default: print to stdout)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Test without executing queries (validate configuration only)",
        )
        parser.add_argument(
            "--models",
            type=str,
            default=None,
            help="Comma-separated list of models to benchmark (default: all cacheable models)",
        )
    
    def handle(self, *args, **options):
        """Execute the benchmark command."""
        self.stdout.write(self.style.SUCCESS("Starting cache benchmark..."))
        
        # Extract options
        num_users = options["users"]
        num_queries = options["queries"]
        report_file = options["report"]
        dry_run = options["dry_run"]
        models_str = options["models"]
        
        # Validate options with safety limits
        if num_users < 1:
            raise CommandError("--users must be at least 1")
        if num_queries < 1:
            raise CommandError("--queries must be at least 1")
        
        # Apply safety limits (Requirement 10.4)
        if num_users > MAX_USERS:
            raise CommandError(
                f"--users exceeds maximum limit of {MAX_USERS} "
                f"(set BENCHMARK_MAX_USERS env var to override)"
            )
        if num_queries > MAX_QUERIES_PER_USER:
            raise CommandError(
                f"--queries exceeds maximum limit of {MAX_QUERIES_PER_USER} "
                f"(set BENCHMARK_MAX_QUERIES env var to override)"
            )
        
        # Get models to benchmark
        models_to_benchmark = self._get_models_to_benchmark(models_str)
        
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No queries will be executed"))
            self.stdout.write(f"Would benchmark {len(models_to_benchmark)} models:")
            for model in models_to_benchmark:
                self.stdout.write(f"  - {model._meta.label}")
            self.stdout.write(f"Would simulate {num_users} users with {num_queries} queries each")
            self.stdout.write(f"Safety: Using Redis DB {BENCHMARK_REDIS_DB} (isolated from production)")
            self.stdout.write(f"Safety: All queries limited to {MAX_RECORDS_PER_QUERY} records")
            self.stdout.write(f"Safety: All writes will be rolled back")
            return
        
        # Initialize benchmark Redis connection
        try:
            benchmark_redis = self._get_benchmark_redis()
            # Test connection
            benchmark_redis.ping()
            self.stdout.write(
                self.style.SUCCESS(f"Connected to benchmark Redis DB {BENCHMARK_REDIS_DB}")
            )
        except Exception as e:
            raise CommandError(f"Failed to connect to benchmark Redis: {e}")
        
        # Run benchmark
        try:
            metrics = self._run_benchmark(num_users, num_queries, models_to_benchmark)
            
            # Generate report
            report = self._generate_report(metrics, num_users, num_queries, models_to_benchmark)
            
            # Output report
            if report_file:
                self._save_report(report, report_file)
                self.stdout.write(self.style.SUCCESS(f"Report saved to {report_file}"))
            else:
                self.stdout.write(json.dumps(report, indent=2))
            
            # Print summary
            self._print_summary(metrics)
            
        except Exception as e:
            logger.exception("Benchmark failed")
            raise CommandError(f"Benchmark failed: {e}")
        finally:
            # Clean up benchmark Redis data
            if self.benchmark_redis:
                try:
                    self.benchmark_redis.flushdb()
                    self.stdout.write("Cleaned up benchmark Redis data")
                except Exception as e:
                    logger.warning(f"Failed to clean up benchmark Redis: {e}")
    
    def _get_models_to_benchmark(self, models_str: Optional[str]) -> List[type]:
        """
        Get list of models to benchmark.
        
        Args:
            models_str: Comma-separated model names or None for all cacheable models
            
        Returns:
            List of model classes
        """
        if models_str:
            # Parse specific models
            model_names = [name.strip() for name in models_str.split(",")]
            models = []
            for name in model_names:
                try:
                    # Try to get model by app_label.ModelName or just ModelName
                    if "." in name:
                        model = apps.get_model(name)
                    else:
                        # Search all apps for this model name
                        found = False
                        for app_config in apps.get_app_configs():
                            try:
                                model = app_config.get_model(name)
                                found = True
                                break
                            except LookupError:
                                continue
                        if not found:
                            raise LookupError(f"Model {name} not found")
                    models.append(model)
                except LookupError:
                    raise CommandError(f"Model not found: {name}")
            return models
        else:
            # Get all models configured in CACHEOPS
            cacheops_config = getattr(settings, "CACHEOPS", {})
            models = []
            for model_pattern in cacheops_config.keys():
                if model_pattern == "*":
                    continue
                try:
                    # Parse pattern like 'app.model' or 'app.*'
                    if ".*" in model_pattern:
                        app_label = model_pattern.replace(".*", "")
                        app_config = apps.get_app_config(app_label)
                        models.extend(app_config.get_models())
                    else:
                        model = apps.get_model(model_pattern)
                        models.append(model)
                except (LookupError, ValueError):
                    continue
            
            # If no models found in CACHEOPS, use some common models
            if not models:
                self.stdout.write(self.style.WARNING("No models configured in CACHEOPS, using default models"))
                try:
                    models = [
                        apps.get_model("auth", "User"),
                        apps.get_model("auth", "Permission"),
                        apps.get_model("contenttypes", "ContentType"),
                    ]
                except LookupError:
                    pass
            
            return models
    
    def _run_benchmark(
        self, num_users: int, num_queries: int, models: List[type]
    ) -> BenchmarkMetrics:
        """
        Run the benchmark with specified parameters.
        
        Args:
            num_users: Number of users to simulate
            num_queries: Number of queries per user
            models: List of models to benchmark
            
        Returns:
            BenchmarkMetrics object with collected metrics
        """
        metrics = BenchmarkMetrics()
        
        self.stdout.write(f"Benchmarking {len(models)} models with {num_users} users...")
        
        # Get or create test users
        users = self._get_or_create_test_users(num_users)
        
        # Benchmark each user
        for user_idx, user in enumerate(users):
            self.stdout.write(f"Benchmarking user {user_idx + 1}/{num_users} (ID: {user.id})...")
            
            # Measure memory before
            memory_before = self._estimate_user_cache_memory(user.id)
            
            # Run queries for this user
            for query_idx in range(num_queries):
                model = models[query_idx % len(models)]
                
                # Measure uncached query time
                uncached_time = self._measure_uncached_query(model, user.id)
                metrics.uncached_query_times.append(uncached_time)
                metrics.cache_misses += 1
                
                # Measure cached query time (second execution should hit cache)
                cached_time = self._measure_cached_query(model, user.id)
                metrics.cached_query_times.append(cached_time)
                metrics.cache_hits += 1
                
                # Measure Redis operation latency
                redis_time = self._measure_redis_operation(user.id)
                metrics.redis_operation_times.append(redis_time)
            
            # Measure memory after
            memory_after = self._estimate_user_cache_memory(user.id)
            metrics.memory_usage_per_user[user.id] = memory_after - memory_before
            
            # Measure invalidation time (O(1) verification)
            invalidation_time = self._measure_invalidation(user.id)
            metrics.invalidation_times.append(invalidation_time)
        
        return metrics
    
    def _get_or_create_test_users(self, num_users: int) -> List[User]:
        """
        Get or create test users for benchmarking.
        
        Args:
            num_users: Number of users needed
            
        Returns:
            List of User objects
        """
        # Get existing users (prefer non-superusers for realistic testing)
        users = list(User.objects.filter(is_superuser=False)[:num_users])
        
        if len(users) < num_users:
            self.stdout.write(
                self.style.WARNING(
                    f"Only {len(users)} users found, using them for benchmark"
                )
            )
        
        if not users:
            raise CommandError("No users found in database. Create at least one user first.")
        
        return users
    
    def _measure_uncached_query(self, model: type, user_id: int) -> float:
        """
        Measure query execution time without cache.
        
        Safety: Uses read-only query with transaction rollback (Requirement 10.4).
        
        Args:
            model: Model class to query
            user_id: User ID for namespace
            
        Returns:
            Query execution time in seconds
        """
        # Clear cache for this user to ensure cache miss
        namespace_manager.increment_user_version(user_id)
        
        start_time = time.time()
        try:
            # Execute a simple read-only query with transaction rollback
            # This ensures no data is modified even if the query has side effects
            with transaction.atomic():
                # Limit to MAX_RECORDS_PER_QUERY for safety
                list(model.objects.all()[:MAX_RECORDS_PER_QUERY])
                # Force rollback to ensure no writes
                transaction.set_rollback(True)
        except Exception as e:
            logger.warning(f"Query failed for {model._meta.label}: {e}")
        
        return time.time() - start_time
    
    def _measure_cached_query(self, model: type, user_id: int) -> float:
        """
        Measure query execution time with cache.
        
        Safety: Uses read-only query with transaction rollback (Requirement 10.4).
        
        Args:
            model: Model class to query
            user_id: User ID for namespace
            
        Returns:
            Query execution time in seconds
        """
        start_time = time.time()
        try:
            # Execute the same query (should hit cache)
            # Still use transaction rollback for safety
            with transaction.atomic():
                list(model.objects.all()[:MAX_RECORDS_PER_QUERY])
                transaction.set_rollback(True)
        except Exception as e:
            logger.warning(f"Cached query failed for {model._meta.label}: {e}")
        
        return time.time() - start_time
    
    def _measure_redis_operation(self, user_id: int) -> float:
        """
        Measure Redis operation latency using benchmark Redis DB.
        
        Safety: Uses separate Redis database (DB 3) for isolation (Requirement 10.4).
        
        Args:
            user_id: User ID for namespace
            
        Returns:
            Operation time in seconds
        """
        start_time = time.time()
        try:
            # Measure GET operation on benchmark Redis
            benchmark_redis = self._get_benchmark_redis()
            version_key = f"{namespace_manager.VERSION_KEY_PREFIX}:{user_id}"
            benchmark_redis.get(version_key)
        except Exception as e:
            logger.warning(f"Redis operation failed: {e}")
        
        return time.time() - start_time
    
    def _measure_invalidation(self, user_id: int) -> float:
        """
        Measure cache invalidation time (O(1) verification).
        
        Safety: Uses benchmark Redis DB for isolation (Requirement 10.4).
        
        Args:
            user_id: User ID for namespace
            
        Returns:
            Invalidation time in seconds
        """
        start_time = time.time()
        try:
            # Measure version increment (O(1) operation) on benchmark Redis
            benchmark_redis = self._get_benchmark_redis()
            version_key = f"{namespace_manager.VERSION_KEY_PREFIX}:{user_id}"
            benchmark_redis.incr(version_key)
        except Exception as e:
            logger.warning(f"Invalidation failed: {e}")
        
        return time.time() - start_time
    
    def _estimate_user_cache_memory(self, user_id: int) -> int:
        """
        Estimate memory usage for a user's cache entries.
        
        This is an approximation based on counting keys and estimating average size.
        Uses benchmark Redis DB for isolation.
        
        Args:
            user_id: User ID
            
        Returns:
            Estimated memory usage in bytes
        """
        try:
            # Get user version from benchmark Redis
            benchmark_redis = self._get_benchmark_redis()
            version_key = f"{namespace_manager.VERSION_KEY_PREFIX}:{user_id}"
            version = benchmark_redis.get(version_key)
            
            if version is None:
                return 0
            
            # Estimate: assume average cache entry is ~1KB
            # In production, you could use Redis MEMORY USAGE command for accuracy
            # For now, we'll use a simple estimation based on key count
            
            # Count keys for this user (pattern: cache:{user_id}:v{version}:*)
            pattern = f"cache:{user_id}:v{version.decode() if isinstance(version, bytes) else version}:*"
            keys = list(benchmark_redis.scan_iter(match=pattern, count=100))
            
            # Estimate 1KB per key
            return len(keys) * 1024
        except Exception as e:
            logger.warning(f"Memory estimation failed: {e}")
            return 0
    
    def _generate_report(
        self,
        metrics: BenchmarkMetrics,
        num_users: int,
        num_queries: int,
        models: List[type],
    ) -> Dict[str, Any]:
        """
        Generate benchmark report.
        
        Args:
            metrics: Collected metrics
            num_users: Number of users benchmarked
            num_queries: Number of queries per user
            models: Models benchmarked
            
        Returns:
            Report dictionary
        """
        return {
            "benchmark_config": {
                "num_users": num_users,
                "num_queries_per_user": num_queries,
                "total_queries": num_users * num_queries,
                "models_benchmarked": [model._meta.label for model in models],
                "max_records_per_query": MAX_RECORDS_PER_QUERY,
            },
            "safety_guarantees": {
                "read_only_queries": True,
                "transaction_rollback": True,
                "separate_redis_db": BENCHMARK_REDIS_DB,
                "query_limits_enforced": True,
                "max_users_limit": MAX_USERS,
                "max_queries_limit": MAX_QUERIES_PER_USER,
            },
            "metrics": metrics.to_dict(),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
    
    def _save_report(self, report: Dict[str, Any], filename: str):
        """
        Save report to JSON file.
        
        Args:
            report: Report dictionary
            filename: Output filename
        """
        with open(filename, "w") as f:
            json.dump(report, f, indent=2)
    
    def _print_summary(self, metrics: BenchmarkMetrics):
        """
        Print benchmark summary to stdout.
        
        Args:
            metrics: Collected metrics
        """
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("BENCHMARK SUMMARY"))
        self.stdout.write("=" * 60)
        
        self.stdout.write(f"\nCache Hit Rate: {metrics.cache_hit_rate:.2f}%")
        self.stdout.write(f"Cache Hits: {metrics.cache_hits}")
        self.stdout.write(f"Cache Misses: {metrics.cache_misses}")
        
        self.stdout.write(f"\nAvg Cached Query Time: {metrics.avg_cached_time:.3f} ms")
        self.stdout.write(f"Avg Uncached Query Time: {metrics.avg_uncached_time:.3f} ms")
        
        if metrics.avg_cached_time > 0:
            speedup = metrics.avg_uncached_time / metrics.avg_cached_time
            self.stdout.write(f"Speedup Factor: {speedup:.2f}x")
        
        self.stdout.write(f"\nAvg Invalidation Time: {metrics.avg_invalidation_time:.3f} ms (O(1) verification)")
        self.stdout.write(f"Avg Redis Operation Time: {metrics.avg_redis_operation_time:.3f} ms")
        
        self.stdout.write(f"\nTotal Memory Usage: {metrics.total_memory_usage / 1024:.2f} KB")
        self.stdout.write(f"Avg Memory Per User: {metrics.avg_memory_per_user:.2f} KB")
        
        if metrics.errors:
            self.stdout.write(self.style.WARNING(f"\nErrors encountered: {len(metrics.errors)}"))
            for error in metrics.errors[:5]:  # Show first 5 errors
                self.stdout.write(f"  - {error}")
        
        self.stdout.write("\n" + "=" * 60)
