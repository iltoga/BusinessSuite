# Post-Migration Validation Checklist: Hybrid Cache System

**Migration Date**: _____________  
**Validated By**: _____________  
**System**: Django 6 + Angular 19 Application  
**Migration Type**: LocMemCache → Redis-based Hybrid Cache System

---

## Overview

This checklist provides comprehensive validation steps to ensure the hybrid cache system migration was successful and the system is operating correctly. Follow these steps in order, checking off each item as you complete it.

**Key Validation Areas**:
- ✅ Immediate health checks (first 5 minutes)
- ✅ Existing cache pattern validation
- ✅ New namespace system validation
- ✅ Performance validation
- ✅ Memory usage validation
- ✅ Error log monitoring
- ✅ Extended monitoring (first 24 hours)

**Success Criteria**:
- All 27 existing cache validation tests pass
- Cache hit rate > 70% after 4 hours
- Redis memory usage < 200MB (80% of 256MB limit)
- No increase in error rate
- Response times ≤ pre-migration baseline

---

## Section 1: Immediate Validation (First 5 Minutes)

**Purpose**: Verify the system is operational and basic functionality works.

**Time Required**: 5 minutes

### 1.1 Application Health Check

**Commands**:
```bash
# 1. Check application is responding
curl http://localhost:8000/health
# Expected: 200 OK

# 2. Check application logs for startup errors
tail -50 /path/to/application.log | grep -iE "error|critical|exception"
# Expected: No cache-related errors

# 3. Verify application process is running
ps aux | grep django
# Expected: Django processes running
```

**Checklist**:
- [ ] Application responds to health check
- [ ] No critical errors in startup logs
- [ ] Django processes are running
- [ ] Application started successfully

**If Failed**: Check application logs, verify Redis connectivity, review Phase 3 of migration runbook

---

### 1.2 Redis Connectivity Check

**Commands**:
```bash
# 1. Test Redis connection
redis-cli -u $REDIS_URL ping
# Expected: PONG

# 2. Check Redis connections from Django
redis-cli -u $REDIS_URL CLIENT LIST | grep django
# Expected: Multiple connections from Django application

# 3. Verify Redis version
redis-cli -u $REDIS_URL INFO server | grep redis_version
# Expected: redis_version:7.x.x

# 4. Check Redis is using correct database
redis-cli -u $REDIS_URL CLIENT LIST | grep "db=1"
# Expected: Connections using database 1
```

**Checklist**:
- [ ] Redis responds to PING
- [ ] Django connections established
- [ ] Redis version is 7.x or higher
- [ ] Connections using database 1

**If Failed**: Check Redis service status, verify REDIS_URL environment variable, check network connectivity

---

### 1.3 Basic Cache Operations Test

**Commands**:
```bash
# Test basic cache operations
python manage.py shell
```

**Python Verification**:
```python
from django.core.cache import cache

# Test set/get
cache.set('migration_health_check', 'success', 60)
result = cache.get('migration_health_check')
print(f"Cache test: {result}")
# Expected: Cache test: success

# Test delete
cache.delete('migration_health_check')
verify = cache.get('migration_health_check')
print(f"After delete: {verify}")
# Expected: After delete: None

# Test increment
cache.set('test_counter', 0, 60)
cache.incr('test_counter')
counter = cache.get('test_counter')
print(f"Counter: {counter}")
# Expected: Counter: 1

cache.delete('test_counter')
exit()
```

**Checklist**:
- [ ] cache.set() works
- [ ] cache.get() works
- [ ] cache.delete() works
- [ ] cache.incr() works
- [ ] No exceptions raised

**If Failed**: Check Redis connectivity, verify cache backend configuration, review Django settings

---

### 1.4 User Authentication Test

**Commands**:
```bash
# Test user login via API
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","password":"testpass"}'
# Expected: 200 OK with authentication token

# Or test via Django shell
python manage.py shell
```

**Python Verification**:
```python
from django.contrib.auth import authenticate
from core.models import UserProfile

# Test authentication
user = authenticate(username='testuser', password='testpass')
print(f"User authenticated: {user is not None}")
# Expected: User authenticated: True

# Check cache_enabled field exists
profile = UserProfile.objects.first()
print(f"Cache enabled: {profile.cache_enabled}")
# Expected: Cache enabled: True

exit()
```

**Checklist**:
- [ ] User login works
- [ ] Authentication successful
- [ ] UserProfile.cache_enabled field exists
- [ ] cache_enabled is True by default

**If Failed**: Check database migration applied, verify user credentials, check authentication middleware

---

### 1.5 Cache Key Format Verification

**Commands**:
```bash
# Monitor Redis for cache key creation
redis-cli -u $REDIS_URL MONITOR | head -20
# (Run in separate terminal, then make a request in the application)

# Sample cache keys
redis-cli -u $REDIS_URL --scan --pattern "cache:*" | head -10
# Expected: Keys with format cache:{user_id}:v{version}:cacheops:{hash}

# Check user version keys
redis-cli -u $REDIS_URL --scan --pattern "cache_user_version:*" | head -5
# Expected: Keys with format cache_user_version:{user_id}
```

**Checklist**:
- [ ] Cache keys are being created
- [ ] Keys follow format: cache:{user_id}:v{version}:cacheops:{hash}
- [ ] User version keys exist: cache_user_version:{user_id}
- [ ] No malformed keys

**If Failed**: Check middleware is active, verify namespace manager configuration, check cacheops integration

---

## Section 2: Existing Cache Pattern Validation (First Hour)

**Purpose**: Verify all existing cache usage patterns work correctly after migration.

**Time Required**: 10 minutes

**Reference**: See `backend/cache/tests/VALIDATION_RESULTS.md` for detailed test documentation

### 2.1 Run Existing Cache Validation Tests

**Commands**:
```bash
# Run all 27 validation tests
python manage.py test backend.cache.tests.test_existing_cache_validation -v 2

# Expected output:
# test_meta_token_cache_operations ... ok
# test_meta_token_cache_expiration ... ok
# test_meta_token_cache_deletion ... ok
# test_meta_token_cache_bulk_operations ... ok
# test_cron_lock_acquisition ... ok
# test_cron_lock_release ... ok
# test_cron_lock_timeout ... ok
# test_cron_lock_bulk_operations ... ok
# test_cron_lock_concurrent_access ... ok
# test_invoice_sequence_initialization ... ok
# test_invoice_sequence_increment ... ok
# test_invoice_sequence_concurrent_access ... ok
# test_invoice_sequence_year_isolation ... ok
# test_invoice_sequence_cache_update ... ok
# test_invoice_sequence_cache_retrieval ... ok
# test_calendar_cursor_initialization ... ok
# test_calendar_cursor_increment ... ok
# test_calendar_cursor_event_storage ... ok
# test_calendar_cursor_bulk_operations ... ok
# test_calendar_cursor_cache_reset ... ok
# test_workflow_cursor_initialization ... ok
# test_workflow_cursor_increment ... ok
# test_workflow_cursor_event_storage ... ok
# test_workflow_cursor_bulk_operations ... ok
# test_workflow_cursor_cache_reset ... ok
# test_cache_performance_set_get ... ok
# test_cache_performance_increment ... ok
# test_cache_performance_delete_many ... ok
# ----------------------------------------------------------------------
# Ran 27 tests in 2.5s
# OK
```

**Checklist**:
- [ ] All 27 tests passed
- [ ] No test failures
- [ ] No test errors
- [ ] Test execution time < 5 seconds

**If Failed**: Review test output, check specific failing pattern, verify Redis connectivity, see troubleshooting section

---

### 2.2 Meta WhatsApp Token Caching Validation

**Manual Test** (if safe in production):
```bash
# Check token cache keys exist
redis-cli -u $REDIS_URL KEYS "meta_whatsapp:*"
# Expected: meta_whatsapp:runtime_access_token, meta_whatsapp:runtime_access_token_expires_at

# Verify token retrieval works
python manage.py shell
```

**Python Verification**:
```python
from django.core.cache import cache

# Check if token is cached (don't modify in production)
token = cache.get('meta_whatsapp:runtime_access_token')
expires_at = cache.get('meta_whatsapp:runtime_access_token_expires_at')

print(f"Token cached: {token is not None}")
print(f"Expires at cached: {expires_at is not None}")
# Expected: Both should be True if tokens are cached

exit()
```

**Checklist**:
- [ ] Token cache keys exist (if tokens are cached)
- [ ] Token retrieval works
- [ ] No WhatsApp API errors in logs
- [ ] WhatsApp integration functional

**If Failed**: Check cache operations, verify token refresh logic, review WhatsApp service logs

---

### 2.3 Cron Job Lock Validation

**Manual Test**:
```bash
# Check cron lock keys
redis-cli -u $REDIS_URL KEYS "cron:*"
# Expected: cron:*:enqueue_lock, cron:*:run_lock keys

# Verify lock acquisition works
python manage.py shell
```

**Python Verification**:
```python
from django.core.cache import cache
import uuid

# Test lock acquisition (use test lock name)
lock_key = 'cron:test_job:enqueue_lock'
lock_token = str(uuid.uuid4())

# Try to acquire lock
acquired = cache.add(lock_key, lock_token, timeout=60)
print(f"Lock acquired: {acquired}")
# Expected: Lock acquired: True

# Try to acquire again (should fail)
acquired_again = cache.add(lock_key, str(uuid.uuid4()), timeout=60)
print(f"Lock acquired again: {acquired_again}")
# Expected: Lock acquired again: False

# Release lock
cache.delete(lock_key)
exit()
```

**Checklist**:
- [ ] Lock acquisition works
- [ ] Duplicate acquisition prevented
- [ ] Lock release works
- [ ] No duplicate cron job executions

**If Failed**: Check cache.add() operation, verify lock timeout, review cron job logs

---

### 2.4 Invoice Sequence Cache Validation

**Manual Test**:
```bash
# Check invoice sequence keys
redis-cli -u $REDIS_URL KEYS "invoice_seq:*"
# Expected: invoice_seq:2026 (or current year)

# Verify sequence increment works
python manage.py shell
```

**Python Verification**:
```python
from django.core.cache import cache
from datetime import datetime

# Get current year
year = datetime.now().year
seq_key = f'invoice_seq:{year}'

# Check current sequence
current = cache.get(seq_key)
print(f"Current sequence: {current}")

# Test increment (safe in production - just increments counter)
if current is not None:
    cache.incr(seq_key)
    new_value = cache.get(seq_key)
    print(f"After increment: {new_value}")
    # Expected: new_value = current + 1

exit()
```

**Checklist**:
- [ ] Invoice sequence keys exist
- [ ] Sequence increment works
- [ ] No invoice number conflicts
- [ ] Invoice generation functional

**If Failed**: Check cache.incr() operation, verify sequence initialization, review invoice model

---

### 2.5 Stream Cursor Cache Validation

**Manual Test**:
```bash
# Check stream cursor keys
redis-cli -u $REDIS_URL KEYS "*stream:cursor"
# Expected: calendar_reminders:stream:cursor, workflow_notifications:stream:cursor

redis-cli -u $REDIS_URL KEYS "*stream:last_event"
# Expected: calendar_reminders:stream:last_event, workflow_notifications:stream:last_event

# Verify cursor operations work
python manage.py shell
```

**Python Verification**:
```python
from django.core.cache import cache

# Check calendar cursor
cal_cursor = cache.get('calendar_reminders:stream:cursor')
print(f"Calendar cursor: {cal_cursor}")

# Check workflow cursor
wf_cursor = cache.get('workflow_notifications:stream:cursor')
print(f"Workflow cursor: {wf_cursor}")

# Both should be integers (0 or higher)
exit()
```

**Checklist**:
- [ ] Stream cursor keys exist
- [ ] Cursor values are valid integers
- [ ] No duplicate notifications
- [ ] Calendar reminders working
- [ ] Workflow notifications working

**If Failed**: Check cursor initialization, verify stream processing, review notification logs

---

## Section 3: New Namespace System Validation (First Hour)

**Purpose**: Verify the new per-user namespace system works correctly.

**Time Required**: 10 minutes

### 3.1 Namespace Key Format Validation

**Commands**:
```bash
# Check namespace cache keys
redis-cli -u $REDIS_URL --scan --pattern "cache:*:v*:cacheops:*" | head -10
# Expected: Keys with format cache:{user_id}:v{version}:cacheops:{hash}

# Check user version keys
redis-cli -u $REDIS_URL --scan --pattern "cache_user_version:*" | head -10
# Expected: Keys with format cache_user_version:{user_id}

# Verify key format
redis-cli -u $REDIS_URL --scan --pattern "cache:*" | head -1
# Should match pattern: cache:123:v1:cacheops:abc123def456
```

**Checklist**:
- [ ] Namespace cache keys exist
- [ ] Keys follow correct format
- [ ] User version keys exist
- [ ] No malformed keys

**If Failed**: Check namespace manager, verify middleware active, review cacheops wrapper

---

### 3.2 Per-User Cache Isolation Test

**Commands**:
```bash
# Test with multiple users
python manage.py shell
```

**Python Verification**:
```python
from django.contrib.auth.models import User
from cache.namespace import NamespaceManager

ns_manager = NamespaceManager()

# Get versions for different users
user1 = User.objects.first()
user2 = User.objects.last()

version1 = ns_manager.get_user_version(user1.id)
version2 = ns_manager.get_user_version(user2.id)

print(f"User {user1.id} version: {version1}")
print(f"User {user2.id} version: {version2}")

# Generate cache key prefixes
prefix1 = ns_manager.get_cache_key_prefix(user1.id)
prefix2 = ns_manager.get_cache_key_prefix(user2.id)

print(f"User {user1.id} prefix: {prefix1}")
print(f"User {user2.id} prefix: {prefix2}")

# Verify prefixes are different
print(f"Prefixes are different: {prefix1 != prefix2}")
# Expected: Prefixes are different: True

exit()
```

**Checklist**:
- [ ] Different users have different cache prefixes
- [ ] User versions are tracked separately
- [ ] Cache isolation working
- [ ] No cache key collisions

**If Failed**: Check namespace manager logic, verify user ID handling, review cache key generation

---

### 3.3 O(1) Cache Invalidation Test

**Commands**:
```bash
# Test O(1) invalidation
python manage.py shell
```

**Python Verification**:
```python
from django.contrib.auth.models import User
from cache.namespace import NamespaceManager
import time

ns_manager = NamespaceManager()
user = User.objects.first()

# Get current version
old_version = ns_manager.get_user_version(user.id)
print(f"Old version: {old_version}")

# Measure invalidation time
start = time.time()
new_version = ns_manager.increment_user_version(user.id)
elapsed = (time.time() - start) * 1000  # Convert to milliseconds

print(f"New version: {new_version}")
print(f"Invalidation time: {elapsed:.3f}ms")

# Verify version incremented
print(f"Version incremented: {new_version == old_version + 1}")
# Expected: Version incremented: True

# Verify invalidation was fast (< 10ms)
print(f"Invalidation was O(1): {elapsed < 10}")
# Expected: Invalidation was O(1): True

exit()
```

**Checklist**:
- [ ] Version increment works
- [ ] Invalidation time < 10ms
- [ ] O(1) complexity verified
- [ ] No key iteration used

**If Failed**: Check Redis INCR operation, verify namespace manager, review performance

---

### 3.4 Cache Enable/Disable Test

**Commands**:
```bash
# Test cache enable/disable
python manage.py shell
```

**Python Verification**:
```python
from django.contrib.auth.models import User
from cache.namespace import NamespaceManager

ns_manager = NamespaceManager()
user = User.objects.first()

# Check current state
enabled = ns_manager.is_cache_enabled(user.id)
print(f"Cache enabled: {enabled}")
# Expected: Cache enabled: True (default)

# Disable cache
ns_manager.set_cache_enabled(user.id, False)
enabled = ns_manager.is_cache_enabled(user.id)
print(f"After disable: {enabled}")
# Expected: After disable: False

# Re-enable cache
ns_manager.set_cache_enabled(user.id, True)
enabled = ns_manager.is_cache_enabled(user.id)
print(f"After enable: {enabled}")
# Expected: After enable: True

exit()
```

**Checklist**:
- [ ] Cache can be disabled
- [ ] Cache can be enabled
- [ ] State persists correctly
- [ ] Bypass works when disabled

**If Failed**: Check UserProfile model, verify cache_enabled field, review middleware logic

---

### 3.5 Cache Control API Test

**Commands**:
```bash
# Test cache control API endpoints (requires authentication token)

# 1. Get cache status
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/cache/status
# Expected: {"enabled": true, "version": 1}

# 2. Clear cache
curl -X POST -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/cache/clear
# Expected: {"version": 2, "cleared": true}

# 3. Disable cache
curl -X POST -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/cache/disable
# Expected: {"enabled": false}

# 4. Enable cache
curl -X POST -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/cache/enable
# Expected: {"enabled": true, "version": 2}
```

**Checklist**:
- [ ] Status endpoint works
- [ ] Clear endpoint works
- [ ] Disable endpoint works
- [ ] Enable endpoint works
- [ ] Authentication required
- [ ] Version increments on clear

**If Failed**: Check API endpoints, verify authentication, review cache views

---

## Section 4: Performance Validation (First 4 Hours)

**Purpose**: Verify no performance regression and cache effectiveness.

**Time Required**: 15 minutes (plus monitoring time)

### 4.1 Cache Hit Rate Monitoring

**Commands**:
```bash
# Check cache hit rate
redis-cli -u $REDIS_URL INFO stats | grep -E "keyspace_hits|keyspace_misses"

# Calculate hit rate
redis-cli -u $REDIS_URL INFO stats | \
  awk '/keyspace_hits/{hits=$2} /keyspace_misses/{misses=$2} END {
    total=hits+misses; 
    if(total>0) print "Hit rate: " (hits/total*100) "%"; 
    else print "No cache operations yet"
  }'
```

**Expected Hit Rates**:
| Time After Migration | Expected Hit Rate |
|---------------------|-------------------|
| 5 minutes | 10-20% |
| 15 minutes | 30-40% |
| 1 hour | 50-60% |
| 4 hours | 70-80% |
| 24 hours | 80-90% |

**Checklist**:
- [ ] Hit rate is increasing over time
- [ ] Hit rate > 70% after 4 hours
- [ ] No sudden drops in hit rate
- [ ] Cache is being used effectively

**If Failed**: Check cache configuration, verify queries are being cached, review TTL settings

---

### 4.2 Response Time Validation

**Commands**:
```bash
# Monitor response times (method depends on your setup)

# Option 1: Using curl with timing
curl -w "@-" -o /dev/null -s http://localhost:8000/api/invoices/ <<'EOF'
    time_namelookup:  %{time_namelookup}\n
       time_connect:  %{time_connect}\n
    time_appconnect:  %{time_appconnect}\n
   time_pretransfer:  %{time_pretransfer}\n
      time_redirect:  %{time_redirect}\n
 time_starttransfer:  %{time_starttransfer}\n
                    ----------\n
         time_total:  %{time_total}\n
EOF

# Option 2: Check application metrics dashboard
# (Method depends on your monitoring setup)

# Option 3: Run benchmark
python manage.py benchmark_cache --users 50 --queries 500 --report post_migration_benchmark.json
```

**Expected Response Times**:
- Cached requests: < 20ms (target: 5-15ms)
- Uncached requests: < 200ms (target: 50-150ms)
- No regression from pre-migration baseline

**Checklist**:
- [ ] Cached response times acceptable
- [ ] Uncached response times acceptable
- [ ] No performance regression
- [ ] Response times improving as cache warms up

**If Failed**: Check Redis latency, verify cache is being used, review database query performance

---

### 4.3 Database Load Validation

**Commands**:
```bash
# Check database connection count
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT count(*) FROM pg_stat_activity WHERE datname='$DB_NAME';"

# Monitor slow queries (if logging enabled)
tail -f /var/log/postgresql/postgresql.log | grep "duration:"

# Check database metrics dashboard
# (Method depends on your monitoring setup)
```

**Expected Results**:
- Database query count reduced by 50-80% (after cache warmup)
- Fewer slow queries
- Lower database CPU usage

**Checklist**:
- [ ] Database load reduced
- [ ] Fewer database connections
- [ ] Slow query count decreased
- [ ] Database performance improved

**If Failed**: Check cache hit rate, verify queries are being cached, review cacheops configuration

---

### 4.4 Run Benchmark System

**Commands**:
```bash
# Run cache benchmark (after 4 hours of warmup)
python manage.py benchmark_cache \
  --users 100 \
  --queries 1000 \
  --report post_migration_benchmark_$(date +%Y%m%d_%H%M%S).json

# Expected output:
# Benchmark Results:
# - Cache hit rate: 70-80%
# - Avg response time (cached): 5-15ms
# - Avg response time (uncached): 50-150ms
# - Cache invalidation time: < 1ms (O(1))
# - Memory per user: 100-500KB

# Compare with baseline (if available)
diff backend/cache/tests/BENCHMARK_RESULTS.md post_migration_benchmark_*.json
```

**Checklist**:
- [ ] Benchmark runs successfully
- [ ] Cache hit rate > 70%
- [ ] Cached response time < 20ms
- [ ] Invalidation time < 1ms (O(1))
- [ ] No performance regression vs baseline

**If Failed**: Review benchmark results, check cache configuration, verify system resources

---

## Section 5: Memory Usage Validation (First 24 Hours)

**Purpose**: Verify Redis memory usage stays within production limits (256MB).

**Time Required**: Ongoing monitoring

### 5.1 Redis Memory Usage Check

**Commands**:
```bash
# Check current memory usage
redis-cli -u $REDIS_URL INFO memory | grep used_memory_human
# Expected: < 200MB (80% of 256MB limit)

# Check memory peak
redis-cli -u $REDIS_URL INFO memory | grep used_memory_peak_human

# Check memory fragmentation
redis-cli -u $REDIS_URL INFO memory | grep mem_fragmentation_ratio
# Expected: 1.0-1.5 (healthy range)

# Monitor memory over time
watch -n 300 'redis-cli -u $REDIS_URL INFO memory | grep used_memory_human'
# Check every 5 minutes
```

**Memory Usage Thresholds**:
- **Green**: < 150MB (< 60% of limit)
- **Yellow**: 150-200MB (60-80% of limit)
- **Red**: > 200MB (> 80% of limit) - Action required

**Checklist**:
- [ ] Memory usage < 200MB
- [ ] Memory growth is stable
- [ ] No memory spikes
- [ ] Fragmentation ratio healthy (1.0-1.5)

**If Failed**: See Section 5.3 for memory optimization steps

---

### 5.2 Cache Key Count Monitoring

**Commands**:
```bash
# Check total key count
redis-cli -u $REDIS_URL DBSIZE
# Expected: Growing steadily, then stabilizing

# Check key count by pattern
redis-cli -u $REDIS_URL --scan --pattern "cache:*" | wc -l
# Namespace cache keys

redis-cli -u $REDIS_URL --scan --pattern "cache_user_version:*" | wc -l
# User version keys (should equal number of active users)

# Monitor key count growth
watch -n 600 'redis-cli -u $REDIS_URL DBSIZE'
# Check every 10 minutes
```

**Expected Key Counts** (approximate):
| Time After Migration | Expected Keys |
|---------------------|---------------|
| 5 minutes | 50-200 |
| 1 hour | 500-2000 |
| 4 hours | 2000-5000 |
| 24 hours | 5000-10000 |

**Checklist**:
- [ ] Key count growing steadily
- [ ] Key count stabilizes after warmup
- [ ] No excessive key creation
- [ ] User version keys match active users

**If Failed**: Check TTL settings, verify cache expiration, review key patterns

---

### 5.3 Memory Optimization (If Needed)

**If memory usage exceeds 200MB**, take these actions:

**Step 1: Analyze Key Distribution**
```bash
# Sample keys to see what's being cached
redis-cli -u $REDIS_URL --scan --pattern "cache:*" | head -50

# Check key sizes
redis-cli -u $REDIS_URL --bigkeys
# Identifies largest keys
```

**Step 2: Adjust TTL Values**
```python
# Edit backend/business_suite/settings/base.py
CACHEOPS = {
    # Reduce TTL for high-volume models
    'invoices.invoice': {'ops': 'all', 'timeout': 60 * 2},  # 2 min instead of 5
    'customer_applications.docapplication': {'ops': 'all', 'timeout': 60 * 2},
    # Keep longer TTL for static data
    'contenttypes.contenttype': {'ops': 'all', 'timeout': 60 * 60},  # 1 hour
}

# Restart application
sudo systemctl restart django-app
```

**Step 3: Configure Maxmemory Policy**
```bash
# Set eviction policy
redis-cli -u $REDIS_URL CONFIG SET maxmemory 256mb
redis-cli -u $REDIS_URL CONFIG SET maxmemory-policy allkeys-lru

# Verify
redis-cli -u $REDIS_URL CONFIG GET maxmemory-policy
# Expected: allkeys-lru

# Make permanent in redis.conf
echo "maxmemory 256mb" | sudo tee -a /etc/redis/redis.conf
echo "maxmemory-policy allkeys-lru" | sudo tee -a /etc/redis/redis.conf
```

**Checklist**:
- [ ] Key distribution analyzed
- [ ] TTL values adjusted if needed
- [ ] Maxmemory policy configured
- [ ] Memory usage reduced to acceptable levels

---

## Section 6: Error Log Monitoring (First 24 Hours)

**Purpose**: Monitor application logs for cache-related issues using Grafana Alloy log scraping.

**Time Required**: Ongoing monitoring

### 6.1 Application Log Monitoring

**Commands**:
```bash
# Monitor application logs for cache errors
tail -f /path/to/application.log | grep -iE "cache|redis"

# Check for specific error patterns
grep -iE "cache.*error|redis.*error|connection.*refused" /path/to/application.log | tail -50

# Count cache-related errors
grep -iE "cache.*error|redis.*error" /path/to/application.log | wc -l

# Monitor error rate over time
watch -n 300 'grep -iE "cache.*error" /path/to/application.log | tail -10'
```

**Error Patterns to Watch**:
- Redis connection errors
- Cache serialization errors
- Cache deserialization errors
- Timeout errors
- Memory errors

**Checklist**:
- [ ] No increase in error rate
- [ ] No Redis connection errors
- [ ] No cache serialization errors
- [ ] Error rate < 0.1% of requests

**If Failed**: Review error logs, check Redis connectivity, verify cache configuration

---

### 6.2 Grafana Alloy Log Scraping Verification

**Purpose**: Ensure logs are being scraped correctly for monitoring.

**Commands**:
```bash
# Check if Grafana Alloy is scraping logs
# (Method depends on your Grafana Alloy setup)

# Verify log format is compatible
tail -10 /path/to/application.log

# Check for structured logging
grep -E "level=|severity=" /path/to/application.log | head -5
```

**Grafana Dashboard Checks**:
- [ ] Cache error rate dashboard shows data
- [ ] Cache hit rate dashboard shows data
- [ ] Redis connection status visible
- [ ] Memory usage metrics visible
- [ ] Response time metrics visible

**Checklist**:
- [ ] Logs are being scraped
- [ ] Cache metrics visible in Grafana
- [ ] Alerts configured (if applicable)
- [ ] No gaps in log data

**If Failed**: Check Grafana Alloy configuration, verify log format, review scraping rules

---

### 6.3 Cache-Specific Log Analysis

**Commands**:
```bash
# Analyze cache hit/miss patterns
grep -E "cache (hit|miss)" /path/to/application.log | \
  awk '{print $NF}' | sort | uniq -c | sort -rn

# Check for cache invalidation events
grep -i "cache.*invalidat" /path/to/application.log | tail -20

# Monitor cache version changes
grep -i "version.*increment" /path/to/application.log | tail -20

# Check for fallback to database
grep -i "cache.*fallback\|redis.*unavailable" /path/to/application.log | tail -20
```

**Log Patterns to Monitor**:
- Cache hit/miss ratio in logs
- Invalidation events (should be O(1) fast)
- Fallback events (should be rare)
- Version increment events (user-initiated)

**Checklist**:
- [ ] Cache hit/miss logged correctly
- [ ] Invalidation events logged
- [ ] Fallback events are rare (< 1%)
- [ ] No unexpected cache behavior

**If Failed**: Review logging configuration, check cache operations, verify error handling

---

### 6.4 Redis Server Log Monitoring

**Commands**:
```bash
# Check Redis server logs
tail -f /var/log/redis/redis-server.log

# Look for warnings or errors
grep -iE "warning|error" /var/log/redis/redis-server.log | tail -20

# Check for memory warnings
grep -i "memory" /var/log/redis/redis-server.log | tail -20

# Check for connection issues
grep -i "connection" /var/log/redis/redis-server.log | tail -20
```

**Redis Log Patterns to Watch**:
- Memory warnings
- Connection timeouts
- Slow commands
- Eviction events

**Checklist**:
- [ ] No Redis errors
- [ ] No memory warnings
- [ ] No connection issues
- [ ] No slow command warnings

**If Failed**: Check Redis configuration, verify memory limits, review connection pool settings

---

## Section 7: Extended Validation (First 24 Hours)

**Purpose**: Monitor system stability and performance over the first 24 hours.

**Time Required**: Periodic checks (3 times per day)

### 7.1 Morning Check (8 AM)

**Commands**:
```bash
# Daily cache summary
cat > daily_cache_summary.sh << 'EOF'
#!/bin/bash
echo "=== Daily Cache Summary ==="
echo "Date: $(date)"
echo ""
echo "Redis Memory:"
redis-cli -u $REDIS_URL INFO memory | grep used_memory_human
echo ""
echo "Cache Stats:"
redis-cli -u $REDIS_URL INFO stats | grep -E "keyspace_hits|keyspace_misses"
echo ""
echo "Key Count:"
redis-cli -u $REDIS_URL DBSIZE
echo ""
echo "Error Count (last 24h):"
grep -i "cache.*error" /path/to/application.log | wc -l
echo ""
echo "Application Status:"
curl -s http://localhost:8000/health | head -1
EOF

chmod +x daily_cache_summary.sh
./daily_cache_summary.sh
```

**Checklist**:
- [ ] Review overnight logs for errors
- [ ] Check Redis memory usage
- [ ] Verify cache hit rate
- [ ] Check application health
- [ ] No user-reported issues

**If Issues Found**: Review error logs, check specific failing components, escalate if needed

---

### 7.2 Afternoon Check (2 PM)

**Commands**:
```bash
# Run daily summary again
./daily_cache_summary.sh

# Check peak traffic performance
redis-cli -u $REDIS_URL INFO stats | grep instantaneous_ops_per_sec

# Monitor response times during peak
# (Method depends on your monitoring setup)
```

**Checklist**:
- [ ] Monitor peak traffic performance
- [ ] Check for any user-reported issues
- [ ] Verify cache effectiveness during high load
- [ ] Memory usage stable during peak

**If Issues Found**: Check performance metrics, review cache hit rate, verify system resources

---

### 7.3 Evening Check (8 PM)

**Commands**:
```bash
# Run daily summary
./daily_cache_summary.sh

# Review daily metrics
echo "=== Daily Metrics Summary ==="
echo "Total requests today: $(grep -c "GET\|POST" /path/to/application.log)"
echo "Cache errors today: $(grep -ic "cache.*error" /path/to/application.log)"
echo "Redis restarts today: $(grep -c "Redis.*start" /var/log/redis/redis-server.log)"
```

**Checklist**:
- [ ] Review daily error logs
- [ ] Check memory usage trends
- [ ] Verify system stability
- [ ] No critical issues

**If Issues Found**: Document issues, plan remediation, schedule follow-up

---

## Section 8: Success Criteria Validation

**Purpose**: Verify all success criteria are met before considering migration complete.

**Time Required**: 10 minutes

### 8.1 Technical Success Criteria

**Immediate Success Criteria** (within 1 hour):
- [ ] Application starts without errors
- [ ] Redis connections established
- [ ] Cache operations work correctly
- [ ] All 27 validation tests pass
- [ ] No increase in error rate
- [ ] Response times ≤ pre-migration baseline

**Short-term Success Criteria** (within 24 hours):
- [ ] Cache hit rate > 70%
- [ ] Memory usage < 200MB (80% of 256MB limit)
- [ ] No cache-related errors in logs
- [ ] User-reported issues = 0
- [ ] Performance meets or exceeds baseline

**Verification Commands**:
```bash
# Check all criteria
echo "=== Success Criteria Check ==="
echo "1. Application health:"
curl -s http://localhost:8000/health && echo "✅ OK" || echo "❌ FAIL"

echo "2. Redis connectivity:"
redis-cli -u $REDIS_URL ping && echo "✅ OK" || echo "❌ FAIL"

echo "3. Cache operations:"
python manage.py shell -c "from django.core.cache import cache; cache.set('test','ok',60); print('✅ OK' if cache.get('test')=='ok' else '❌ FAIL')"

echo "4. Validation tests:"
python manage.py test backend.cache.tests.test_existing_cache_validation --verbosity=0 && echo "✅ OK" || echo "❌ FAIL"

echo "5. Cache hit rate:"
redis-cli -u $REDIS_URL INFO stats | awk '/keyspace_hits/{h=$2} /keyspace_misses/{m=$2} END {rate=h/(h+m)*100; print (rate>70 ? "✅ " : "❌ ") rate "%"}'

echo "6. Memory usage:"
redis-cli -u $REDIS_URL INFO memory | awk '/used_memory:/{mem=$2/1024/1024; print (mem<200 ? "✅ " : "❌ ") mem " MB"}'
```

**Checklist**:
- [ ] All immediate criteria met
- [ ] All short-term criteria met (after 24h)
- [ ] No critical issues
- [ ] System is stable

---

### 8.2 Functional Success Criteria

**Core Functionality Checklist**:
- [ ] Users can log in
- [ ] Invoice generation works
- [ ] Calendar reminders work
- [ ] Workflow notifications work
- [ ] WhatsApp integration works
- [ ] Cron jobs execute correctly

**Cache Functionality Checklist**:
- [ ] Per-user cache isolation works
- [ ] Cache clear functionality works
- [ ] Automatic invalidation works
- [ ] Frontend cache synchronization works
- [ ] Existing cache patterns work

**Manual Testing**:
```bash
# Test key workflows
# 1. User login
# 2. Create invoice
# 3. View calendar
# 4. Check notifications
# 5. Clear cache via UI
# 6. Verify cache cleared
```

**Checklist**:
- [ ] All core functionality works
- [ ] All cache functionality works
- [ ] No user-facing errors
- [ ] User experience acceptable

---

### 8.3 Performance Success Criteria

**Response Time Criteria**:
- [ ] Cached requests: < 20ms (target: 5-15ms)
- [ ] Uncached requests: < 200ms (target: 50-150ms)
- [ ] Cache invalidation: < 1ms (O(1) operation)

**Cache Effectiveness Criteria**:
- [ ] Hit rate: > 80% (after warmup)
- [ ] Miss rate: < 20%
- [ ] Eviction rate: < 5% of total operations

**Resource Usage Criteria**:
- [ ] Redis memory: < 200MB
- [ ] Redis CPU: < 20%
- [ ] Application CPU: No increase
- [ ] Database load: Reduced by 50-80%

**Verification Commands**:
```bash
# Check response times (run benchmark)
python manage.py benchmark_cache --users 50 --queries 500

# Check resource usage
echo "Redis Memory: $(redis-cli -u $REDIS_URL INFO memory | grep used_memory_human | cut -d: -f2)"
echo "Redis CPU: $(redis-cli -u $REDIS_URL INFO cpu | grep used_cpu_sys | cut -d: -f2)"

# Check database load (method depends on your setup)
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT count(*) FROM pg_stat_activity WHERE datname='$DB_NAME';"
```

**Checklist**:
- [ ] All response time criteria met
- [ ] All cache effectiveness criteria met
- [ ] All resource usage criteria met
- [ ] No performance regression

---

### 8.4 Business Success Criteria

**User Experience Criteria**:
- [ ] No user complaints about performance
- [ ] No increase in support tickets
- [ ] User satisfaction maintained or improved

**System Reliability Criteria**:
- [ ] Uptime: 99.9%+
- [ ] Error rate: < 0.1%
- [ ] No data loss
- [ ] No security incidents

**Verification**:
```bash
# Check uptime
uptime

# Check error rate
total_requests=$(grep -c "GET\|POST" /path/to/application.log)
error_requests=$(grep -c "500\|502\|503\|504" /path/to/application.log)
error_rate=$(echo "scale=4; $error_requests / $total_requests * 100" | bc)
echo "Error rate: $error_rate%"

# Check for data loss (verify database integrity)
python manage.py check --database default
```

**Checklist**:
- [ ] User experience criteria met
- [ ] System reliability criteria met
- [ ] No business impact
- [ ] Stakeholders satisfied

---

## Section 9: Troubleshooting Common Issues

**Purpose**: Quick reference for resolving common post-migration issues.

### Issue 1: Cache Hit Rate Lower Than Expected

**Symptoms**:
- Hit rate < 70% after 4 hours
- Most requests hitting database
- Slow performance

**Diagnosis**:
```bash
# Check if cache is being used
redis-cli -u $REDIS_URL MONITOR | head -20

# Check cache key count
redis-cli -u $REDIS_URL DBSIZE

# Verify cacheops is active
python manage.py shell -c "from django.conf import settings; print(settings.CACHEOPS)"
```

**Solutions**:
1. Wait longer for cache warmup (up to 24 hours)
2. Verify cacheops configuration includes your models
3. Check TTL values aren't too short
4. Verify middleware is active

---

### Issue 2: Redis Memory Usage Too High

**Symptoms**:
- Memory usage > 200MB
- Redis evicting keys frequently
- Performance degrading

**Diagnosis**:
```bash
# Check memory usage
redis-cli -u $REDIS_URL INFO memory | grep used_memory_human

# Check eviction stats
redis-cli -u $REDIS_URL INFO stats | grep evicted_keys

# Find large keys
redis-cli -u $REDIS_URL --bigkeys
```

**Solutions**:
1. Reduce TTL values for high-volume models (see Section 5.3)
2. Configure maxmemory-policy to allkeys-lru
3. Clear cache and let it rebuild: `redis-cli -u $REDIS_URL FLUSHDB`
4. Review which models are being cached

---

### Issue 3: Existing Cache Patterns Not Working

**Symptoms**:
- WhatsApp token errors
- Duplicate cron job executions
- Invoice sequence errors

**Diagnosis**:
```bash
# Run validation tests
python manage.py test backend.cache.tests.test_existing_cache_validation -v 2

# Check specific pattern
python manage.py shell -c "from django.core.cache import cache; cache.set('test','ok',60); print(cache.get('test'))"
```

**Solutions**:
1. Verify Redis is accessible
2. Check cache backend configuration
3. Verify no key prefix conflicts
4. Review error logs for specific failures

---

### Issue 4: Cache Keys Not Being Created

**Symptoms**:
- Redis MONITOR shows no cache keys
- DBSIZE returns 0 or very low number
- All requests hitting database

**Diagnosis**:
```bash
# Check middleware is active
python manage.py shell -c "from django.conf import settings; print('cache.middleware.CacheMiddleware' in settings.MIDDLEWARE)"

# Check user has caching enabled
python manage.py shell -c "from core.models import UserProfile; print(UserProfile.objects.first().cache_enabled)"

# Verify cacheops configuration
python manage.py shell -c "from django.conf import settings; print(bool(settings.CACHEOPS))"
```

**Solutions**:
1. Verify middleware is in MIDDLEWARE list after auth middleware
2. Check user.cache_enabled is True
3. Verify CACHEOPS dictionary is configured
4. Restart application

---

### Issue 5: Performance Slower Than Before

**Symptoms**:
- Response times > 2x pre-migration
- Users complaining about slowness
- Database load higher than expected

**Diagnosis**:
```bash
# Check cache hit rate
redis-cli -u $REDIS_URL INFO stats | grep keyspace_hits

# Check Redis latency
redis-cli -u $REDIS_URL --latency

# Check database query count
# (Method depends on your monitoring setup)
```

**Solutions**:
1. Wait for cache warmup (15-30 minutes minimum)
2. Check Redis latency (should be < 5ms)
3. Verify queries are being cached
4. Run benchmark to identify bottlenecks

---

### Issue 6: Frontend Cache Not Synchronizing

**Symptoms**:
- Frontend shows stale data
- Cache version headers missing
- IndexedDB not clearing

**Diagnosis**:
```bash
# Check response headers
curl -I http://localhost:8000/api/invoices/
# Should include: X-Cache-Version

# Verify middleware is active
python manage.py shell -c "from django.conf import settings; print('cache.middleware.CacheMiddleware' in settings.MIDDLEWARE)"
```

**Solutions**:
1. Verify middleware order (after auth middleware)
2. Check Angular interceptor is registered
3. Clear frontend cache manually: `indexedDB.deleteDatabase('hybrid-cache')`
4. Verify cache version headers in responses

---

## Section 10: Migration Sign-Off

**Purpose**: Document completion and approval of post-migration validation.

### 10.1 Validation Summary

**Migration Details**:
- Migration Date: _____________
- Validation Start Time: _____________
- Validation End Time: _____________
- Total Validation Duration: _____________

**Validation Results**:
- [ ] All immediate checks passed (Section 1)
- [ ] All existing cache patterns validated (Section 2)
- [ ] New namespace system validated (Section 3)
- [ ] Performance criteria met (Section 4)
- [ ] Memory usage acceptable (Section 5)
- [ ] No critical errors in logs (Section 6)
- [ ] Extended monitoring completed (Section 7)
- [ ] All success criteria met (Section 8)

**Issues Encountered**:
1. _____________
2. _____________
3. _____________

**Resolutions Applied**:
1. _____________
2. _____________
3. _____________

---

### 10.2 Metrics Summary

**Cache Performance**:
- Cache hit rate: _____________% (target: > 70%)
- Cached response time: _____________ms (target: < 20ms)
- Uncached response time: _____________ms (target: < 200ms)
- Cache invalidation time: _____________ms (target: < 1ms)

**Resource Usage**:
- Redis memory usage: _____________MB (limit: 256MB)
- Redis key count: _____________
- Database load reduction: _____________%
- Error rate: _____________%

**System Health**:
- Application uptime: _____________%
- Redis uptime: _____________%
- User-reported issues: _____________
- Support tickets: _____________

---

### 10.3 Recommendations

**Immediate Actions** (if any):
1. _____________
2. _____________
3. _____________

**Short-term Optimizations** (next 7 days):
1. _____________
2. _____________
3. _____________

**Long-term Improvements** (next 30 days):
1. _____________
2. _____________
3. _____________

---

### 10.4 Sign-Off and Approvals

**Validation Completed By**: _____________  
**Date**: _____________  
**Time**: _____________

**Verification Checklist**:
- [ ] All validation sections completed
- [ ] All tests passed
- [ ] No critical issues outstanding
- [ ] System is stable and performing well
- [ ] Documentation updated
- [ ] Team notified of completion

**Approvals**:

**Migration Lead**:
- Name: _____________
- Signature: _____________
- Date: _____________

**Technical Lead**:
- Name: _____________
- Signature: _____________
- Date: _____________

**Operations Lead**:
- Name: _____________
- Signature: _____________
- Date: _____________

**Product Owner** (if applicable):
- Name: _____________
- Signature: _____________
- Date: _____________

---

### 10.5 Next Steps

**Immediate** (next 24 hours):
- [ ] Continue monitoring cache performance
- [ ] Monitor error logs for any issues
- [ ] Track user feedback
- [ ] Document any additional issues

**Short-term** (next 7 days):
- [ ] Review cache hit rate trends
- [ ] Optimize TTL values if needed
- [ ] Address any performance issues
- [ ] Update documentation based on learnings

**Long-term** (next 30 days):
- [ ] Analyze cache effectiveness per model
- [ ] Implement additional optimizations
- [ ] Review and update monitoring dashboards
- [ ] Plan for future enhancements

---

## Appendix A: Quick Reference Commands

### Health Checks
```bash
# Application health
curl http://localhost:8000/health

# Redis health
redis-cli -u $REDIS_URL ping

# Cache test
python manage.py shell -c "from django.core.cache import cache; cache.set('test','ok',60); print(cache.get('test'))"

# Validation tests
python manage.py test backend.cache.tests.test_existing_cache_validation
```

### Monitoring
```bash
# Redis memory
redis-cli -u $REDIS_URL INFO memory | grep used_memory_human

# Redis key count
redis-cli -u $REDIS_URL DBSIZE

# Cache stats
redis-cli -u $REDIS_URL INFO stats | grep -E "keyspace|hits|misses"

# Application logs
tail -f /path/to/application.log | grep -iE "cache|redis|error"
```

### Troubleshooting
```bash
# Clear cache
redis-cli -u $REDIS_URL FLUSHDB

# Restart application
sudo systemctl restart django-app

# Check connections
redis-cli -u $REDIS_URL CLIENT LIST | grep django

# Monitor operations
redis-cli -u $REDIS_URL MONITOR
```

---

## Appendix B: Validation Test Results Reference

### Expected Test Results

**File**: `backend/cache/tests/VALIDATION_RESULTS.md`

**Total Tests**: 27
- Meta WhatsApp token caching: 4 tests
- Cron job lock coordination: 5 tests
- Invoice sequence cache: 6 tests
- Calendar reminder stream cursor: 5 tests
- Workflow notification stream cursor: 5 tests
- Cache performance: 3 tests

**All tests should pass** - if any fail, see troubleshooting section.

---

## Appendix C: Benchmark Results Reference

### Expected Benchmark Results

**File**: `backend/cache/tests/BENCHMARK_RESULTS.md`

**Key Metrics**:
- Cache hit rate: 50% (initial) → 70-80% (after warmup)
- Cached query time: 1.3ms → 5-15ms (target)
- Uncached query time: 1.4ms → 50-150ms (target)
- O(1) invalidation: 0.35ms (excellent)
- Redis operations: 0.46ms (excellent)

**Note**: Initial benchmark may show lower hit rates due to cold cache. Re-run after 4 hours for accurate results.

---

## Appendix D: Configuration Reference

### Environment Variables
```bash
REDIS_URL=redis://redis:6379/1
CACHE_KEY_PREFIX=revisbali
CACHE_DEFAULT_TIMEOUT=300
```

### Redis Databases
- DB 0: Huey task queue
- DB 1: Django cache (default)
- DB 2: Cacheops ORM cache
- DB 3: Benchmark system
- DB 15: Test environment

### Key Patterns
- Django cache: `revisbali:cache:*`
- Cacheops: `cache:{user_id}:v{version}:cacheops:{hash}`
- User version: `cache_user_version:{user_id}`
- Existing patterns: `meta_whatsapp:*`, `cron:*`, `invoice_seq:*`, etc.

### Important Files
- Settings: `backend/business_suite/settings/base.py`
- Cache backends: `backend/business_suite/settings/cache_backends.py`
- Middleware: `backend/cache/middleware.py`
- Namespace: `backend/cache/namespace.py`
- Validation tests: `backend/cache/tests/test_existing_cache_validation.py`

---

## Appendix E: Support and Escalation

### Support Contacts

**Technical Issues**:
- Development Team: _____________
- Operations Team: _____________
- On-Call Engineer: _____________

**Escalation Path**:
- Level 1: Development team
- Level 2: Technical lead
- Level 3: System administrator
- Level 4: CTO

### Communication Channels
- Email: support@example.com
- Slack: #cache-migration
- Phone: +1-XXX-XXX-XXXX
- Emergency: +1-XXX-XXX-XXXX

---

## Appendix F: Additional Resources

### Documentation References

**Migration Documentation**:
- Pre-Migration Checklist: `backend/cache/PRE_MIGRATION_CHECKLIST.md`
- Migration Runbook: `backend/cache/MIGRATION_RUNBOOK.md`
- Post-Migration Checklist: `backend/cache/POST_MIGRATION_CHECKLIST.md` (this document)

**System Documentation**:
- Architecture: `backend/cache/ARCHITECTURE.md`
- API Documentation: `backend/cache/API_DOCUMENTATION.md`
- Optimization Notes: `backend/cache/OPTIMIZATION_NOTES.md`

**Test Results**:
- Validation Results: `backend/cache/tests/VALIDATION_RESULTS.md`
- Benchmark Results: `backend/cache/tests/BENCHMARK_RESULTS.md`

**Specifications**:
- Requirements: `.kiro/specs/hybrid-cache-system/requirements.md`
- Design: `.kiro/specs/hybrid-cache-system/design.md`
- Tasks: `.kiro/specs/hybrid-cache-system/tasks.md`

### External Resources

**Django Cache Framework**:
- Documentation: https://docs.djangoproject.com/en/stable/topics/cache/
- Best practices: https://docs.djangoproject.com/en/stable/topics/cache/#cache-key-prefixing

**django-redis**:
- GitHub: https://github.com/jazzband/django-redis
- Documentation: https://github.com/jazzband/django-redis#readme

**django-cacheops**:
- GitHub: https://github.com/Suor/django-cacheops
- Documentation: https://github.com/Suor/django-cacheops#readme

**Redis**:
- Documentation: https://redis.io/documentation
- Commands: https://redis.io/commands
- Best practices: https://redis.io/topics/memory-optimization

---

## Appendix G: Grafana Alloy Log Monitoring

### Log Scraping Configuration

**Purpose**: Ensure cache-related logs are properly scraped by Grafana Alloy for monitoring.

**Log Patterns to Monitor**:
```
# Cache operations
level=INFO msg="Cache hit" user_id=123 cache_key="cache:123:v1:cacheops:abc"
level=INFO msg="Cache miss" user_id=123 cache_key="cache:123:v1:cacheops:def"

# Cache errors
level=ERROR msg="Redis connection failed" error="connection refused"
level=ERROR msg="Cache serialization failed" model="Invoice" error="..."

# Cache invalidation
level=INFO msg="Cache invalidated" user_id=123 old_version=1 new_version=2

# Performance metrics
level=INFO msg="Cache operation" operation="get" duration_ms=1.2
level=INFO msg="Cache operation" operation="set" duration_ms=2.5
```

**Grafana Dashboard Queries**:
```promql
# Cache hit rate
sum(rate(cache_hits_total[5m])) / sum(rate(cache_operations_total[5m]))

# Cache error rate
sum(rate(cache_errors_total[5m])) / sum(rate(cache_operations_total[5m]))

# Redis memory usage
redis_memory_used_bytes / redis_memory_max_bytes

# Cache operation latency
histogram_quantile(0.95, rate(cache_operation_duration_seconds_bucket[5m]))
```

**Alerts to Configure**:
- Cache error rate > 1%
- Redis memory usage > 80%
- Cache hit rate < 50% (after warmup)
- Redis connection failures

---

**END OF POST-MIGRATION CHECKLIST**

*This checklist should be completed after production migration to ensure the system is operating correctly. Keep this document for reference and compliance.*

