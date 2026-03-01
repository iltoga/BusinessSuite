# Migration Runbook: Hybrid Cache System

**Document Version**: 1.0  
**Last Updated**: 2024  
**System**: Django 6 + Angular 19 Application  
**Migration**: LocMemCache → Redis-based Hybrid Cache System

---

## Table of Contents

1. [Overview](#overview)
2. [Pre-Migration Requirements](#pre-migration-requirements)
3. [Migration Timeline](#migration-timeline)
4. [Phase 1: Pre-Migration Verification](#phase-1-pre-migration-verification)
5. [Phase 2: Database Migration](#phase-2-database-migration)
6. [Phase 3: Application Deployment](#phase-3-application-deployment)
7. [Phase 4: Post-Migration Validation](#phase-4-post-migration-validation)
8. [Phase 5: Monitoring and Optimization](#phase-5-monitoring-and-optimization)
9. [Rollback Procedures](#rollback-procedures)
10. [Troubleshooting Guide](#troubleshooting-guide)
11. [Success Criteria](#success-criteria)

---

## Overview

### Purpose

This runbook provides step-by-step instructions for migrating from LocMemCache to the Redis-based hybrid cache system in production. The migration has been thoroughly tested and validated - all existing cache patterns work without code changes.

### Migration Scope

**What Changes**:
- Cache backend: LocMemCache → Redis (django-redis)
- Cache architecture: Single-layer → 4-layer hybrid system
- Cache isolation: None → Per-user namespace versioning
- Invalidation: Manual → Automatic (cacheops) + O(1) per-user

**What Stays the Same**:
- All existing cache usage patterns (tokens, locks, sequences, cursors)
- Database schema (migration adds one field only)
- Application code (no changes to business logic)
- API endpoints (extended, not replaced)

### Key Points

✅ **Validated**: All 27 existing cache patterns tested and working  
✅ **Backward Compatible**: No code changes required  
✅ **Zero Data Loss**: Only cache cleared, database unchanged  
✅ **Graceful Fallback**: System works if Redis fails  
⚠️ **Cache Reset**: All cache data will be cleared (by design)  
⚠️ **Memory Limit**: Production Redis limited to 256MB RAM


---

## Pre-Migration Requirements

### Required Artifacts

Before starting migration, ensure you have:

- [ ] **Pre-Migration Checklist**: `backend/cache/PRE_MIGRATION_CHECKLIST.md` completed
- [ ] **Database Backup**: Recent backup verified and tested
- [ ] **Configuration Backup**: Settings files backed up
- [ ] **Redis Access**: REDIS_URL environment variable configured
- [ ] **Team Notification**: All stakeholders informed
- [ ] **Rollback Plan**: Documented and understood by team

### Environment Variables

Verify these are set in production:

```bash
# Required
REDIS_URL=redis://redis:6379/1

# Optional (with defaults)
CACHE_KEY_PREFIX=revisbali
CACHE_DEFAULT_TIMEOUT=300
```

### Team Readiness

- [ ] Migration lead identified: __________
- [ ] Backup operator identified: __________
- [ ] On-call engineer available: __________
- [ ] Communication channel established: __________

---

## Migration Timeline

### Estimated Duration

| Phase | Duration | Downtime Required |
|-------|----------|-------------------|
| Pre-Migration Verification | 15 minutes | No |
| Database Migration | 5 minutes | No |
| Application Deployment | 10 minutes | Optional (5 min) |
| Post-Migration Validation | 15 minutes | No |
| **Total** | **45 minutes** | **0-5 minutes** |

### Recommended Schedule

**Best Time**: Low-traffic period (e.g., 2 AM - 4 AM local time)

**Maintenance Window**: 1 hour (includes buffer for issues)

**Rollback Time**: 15 minutes if needed


---

## Phase 1: Pre-Migration Verification

**Duration**: 15 minutes  
**Downtime**: No

### Step 1.1: Verify Pre-Migration Checklist

**Command**:
```bash
# Ensure checklist is complete
cat backend/cache/PRE_MIGRATION_CHECKLIST.md | grep "\[ \]" | wc -l
# Expected: 0 (all items checked)
```

**Verification**:
- [ ] All checklist sections completed
- [ ] All validation tests passed (27/27)
- [ ] No outstanding issues

**Time**: 2 minutes

---

### Step 1.2: Verify Redis Connectivity

**Commands**:
```bash
# Test Redis connection
redis-cli -u $REDIS_URL ping
# Expected output: PONG

# Check Redis version
redis-cli -u $REDIS_URL INFO server | grep redis_version
# Expected: redis_version:7.x.x

# Test read/write operations
redis-cli -u $REDIS_URL SET migration_test "success" EX 60
redis-cli -u $REDIS_URL GET migration_test
# Expected: "success"

redis-cli -u $REDIS_URL DEL migration_test
```

**Verification**:
- [ ] Redis responds to PING
- [ ] Redis version is 7.x or higher
- [ ] Read/write operations work
- [ ] No connection errors

**Time**: 3 minutes

**Troubleshooting**: If Redis is unreachable, see [Troubleshooting Guide](#troubleshooting-guide)

---

### Step 1.3: Capture Current System State

**Commands**:
```bash
# Create state capture directory
mkdir -p migration_state/$(date +%Y%m%d_%H%M%S)
cd migration_state/$(date +%Y%m%d_%H%M%S)

# Capture current cache backend
python manage.py shell -c "from django.conf import settings; print(settings.CACHES['default']['BACKEND'])" > cache_backend.txt

# Capture Redis key count
redis-cli -u $REDIS_URL DBSIZE > redis_keys_before.txt

# Capture Redis memory usage
redis-cli -u $REDIS_URL INFO memory | grep used_memory_human > redis_memory_before.txt

# Capture application logs (last 100 lines)
tail -100 /path/to/application.log > app_logs_before.txt

# Test key application functions
curl -s http://localhost:8000/health > health_check_before.txt
```

**Verification**:
- [ ] Current cache backend documented
- [ ] Redis key count recorded: __________
- [ ] Redis memory usage recorded: __________
- [ ] Application logs captured
- [ ] Health check successful

**Time**: 5 minutes

---

### Step 1.4: Create Backups

**Commands**:
```bash
# Database backup
pg_dump -h $DB_HOST -U $DB_USER -d $DB_NAME -F c \
  -f migration_backup_$(date +%Y%m%d_%H%M%S).dump

# Verify backup
ls -lh migration_backup_*.dump

# Configuration backup
cp backend/business_suite/settings/base.py migration_state/$(date +%Y%m%d_%H%M%S)/
cp backend/business_suite/settings/cache_backends.py migration_state/$(date +%Y%m%d_%H%M%S)/

# Environment variables backup
env | grep -E "REDIS|CACHE" > migration_state/$(date +%Y%m%d_%H%M%S)/env_vars.txt
```

**Verification**:
- [ ] Database backup created
- [ ] Backup file size is reasonable: __________ MB
- [ ] Configuration files backed up
- [ ] Environment variables documented

**Time**: 5 minutes

**Expected Output**:
```
migration_backup_20240101_020000.dump  (size: ~500MB)
```


---

## Phase 2: Database Migration

**Duration**: 5 minutes  
**Downtime**: No (migration runs while app is live)

### Step 2.1: Review Migration

**Command**:
```bash
# View migration SQL (dry run)
python manage.py sqlmigrate core 0022

# Expected output:
# ALTER TABLE "core_userprofile" ADD COLUMN "cache_enabled" boolean DEFAULT true NOT NULL;
# CREATE INDEX "core_userprofile_cache_enabled_idx" ON "core_userprofile" ("cache_enabled");
```

**Verification**:
- [ ] Migration adds `cache_enabled` field
- [ ] Default value is `true`
- [ ] Index is created
- [ ] No destructive operations (DROP, DELETE)

**Time**: 1 minute

---

### Step 2.2: Check Migration Status

**Command**:
```bash
# Check if migration already applied
python manage.py showmigrations core | grep 0022

# Expected output (if not applied):
# [ ] 0022_add_cache_enabled_to_userprofile

# Expected output (if already applied):
# [X] 0022_add_cache_enabled_to_userprofile
```

**Verification**:
- [ ] Migration status checked
- [ ] If already applied, skip to Phase 3

**Time**: 1 minute

---

### Step 2.3: Apply Migration

**Command**:
```bash
# Apply migration
python manage.py migrate core 0022

# Expected output:
# Running migrations:
#   Applying core.0022_add_cache_enabled_to_userprofile... OK
```

**Verification**:
- [ ] Migration applied successfully
- [ ] No errors in output
- [ ] Migration marked as applied

**Time**: 2 minutes

**Expected Duration**: 1-2 seconds (adds one column with default value)

---

### Step 2.4: Verify Database Schema

**Commands**:
```bash
# Verify column exists
python manage.py dbshell
```

**SQL Verification**:
```sql
-- Check cache_enabled column
SELECT column_name, data_type, is_nullable, column_default 
FROM information_schema.columns 
WHERE table_name = 'core_userprofile' 
  AND column_name = 'cache_enabled';

-- Expected output:
-- column_name   | data_type | is_nullable | column_default
-- cache_enabled | boolean   | NO          | true

-- Verify index exists
SELECT indexname, indexdef 
FROM pg_indexes 
WHERE tablename = 'core_userprofile' 
  AND indexdef LIKE '%cache_enabled%';

-- Expected: One index named 'core_userprofile_cache_enabled_idx'

-- Check sample users
SELECT id, username, cache_enabled 
FROM auth_user 
JOIN core_userprofile ON auth_user.id = core_userprofile.user_id 
LIMIT 5;

-- Expected: All users have cache_enabled = true

\q
```

**Verification**:
- [ ] `cache_enabled` column exists
- [ ] Column type is boolean
- [ ] Default value is true
- [ ] Index exists
- [ ] Sample users show cache_enabled=true

**Time**: 1 minute


---

## Phase 3: Application Deployment

**Duration**: 10 minutes  
**Downtime**: Optional (0-5 minutes)

### Deployment Strategy

**Option A: Zero-Downtime Deployment** (Recommended)
- Rolling restart of application servers
- No user-facing downtime
- Cache will rebuild gradually

**Option B: Maintenance Window Deployment**
- Brief maintenance window (5 minutes)
- Clean cache reset
- Faster cache warmup

**Choose**: Option __________ (A or B)

---

### Step 3.1: Announce Maintenance (Option B Only)

**If using Option B**:

```bash
# Enable maintenance page (if available)
# Method depends on your infrastructure
# Example: nginx maintenance mode
```

**Notification**:
- [ ] Users notified via email/banner
- [ ] Maintenance page enabled
- [ ] Start time recorded: __________

**Time**: 2 minutes (Option B only)

---

### Step 3.2: Stop Application (Option B Only)

**If using Option B**:

```bash
# Stop Django application
# Method depends on your process manager

# Example: systemd
sudo systemctl stop django-app

# Example: supervisor
sudo supervisorctl stop django-app

# Example: Docker
docker-compose stop web

# Verify application stopped
curl http://localhost:8000/health
# Expected: Connection refused or 503
```

**Verification**:
- [ ] Application stopped
- [ ] No active requests
- [ ] Health check fails

**Time**: 1 minute (Option B only)

---

### Step 3.3: Clear Cache Data

**Commands**:
```bash
# Clear Redis database 1 (Django cache)
redis-cli -u $REDIS_URL FLUSHDB
# Expected: OK

# Clear Redis database 2 (Cacheops - will be populated after deployment)
redis-cli -u $REDIS_URL -n 2 FLUSHDB
# Expected: OK

# Verify databases are empty
redis-cli -u $REDIS_URL DBSIZE
# Expected: 0

redis-cli -u $REDIS_URL -n 2 DBSIZE
# Expected: 0
```

**Verification**:
- [ ] Database 1 cleared
- [ ] Database 2 cleared
- [ ] Key count is 0

**Time**: 1 minute

**Note**: This clears ALL cache data. Cache will rebuild automatically as users access the system.

---

### Step 3.4: Verify Configuration

**Commands**:
```bash
# Check Django settings
python manage.py check --deploy

# Expected output:
# System check identified no issues (0 silenced).

# Verify cache configuration
python manage.py shell
```

**Python Verification**:
```python
from django.conf import settings

# Check cache backend
print(settings.CACHES['default']['BACKEND'])
# Expected: 'django_redis.cache.RedisCache'

# Check Redis URL
print(settings.CACHES['default']['LOCATION'])
# Expected: Your REDIS_URL value

# Check cacheops configuration
print(settings.CACHEOPS_REDIS)
# Expected: Redis URL with /2 database

# Test cache operations
from django.core.cache import cache
cache.set('migration_verify', 'success', 60)
result = cache.get('migration_verify')
print(result)
# Expected: 'success'

cache.delete('migration_verify')
exit()
```

**Verification**:
- [ ] No deployment issues found
- [ ] Cache backend is django-redis
- [ ] Redis URL is correct
- [ ] Cacheops configured
- [ ] Test cache operations work

**Time**: 2 minutes

---

### Step 3.5: Start Application

**Commands**:

**Option A (Rolling Restart)**:
```bash
# Restart application servers one by one
# Method depends on your infrastructure

# Example: Kubernetes rolling update
kubectl rollout restart deployment/django-app

# Example: systemd with multiple instances
sudo systemctl restart django-app@1
sleep 30
sudo systemctl restart django-app@2
sleep 30
sudo systemctl restart django-app@3
```

**Option B (Full Restart)**:
```bash
# Start Django application
# Method depends on your process manager

# Example: systemd
sudo systemctl start django-app

# Example: supervisor
sudo supervisorctl start django-app

# Example: Docker
docker-compose up -d web
```

**Verification**:
- [ ] Application started
- [ ] No errors in startup logs
- [ ] Health check passes

**Time**: 2 minutes

---

### Step 3.6: Monitor Startup

**Commands**:
```bash
# Watch application logs
tail -f /path/to/application.log | grep -E "cache|redis|error"

# In another terminal, check Redis connections
watch -n 5 'redis-cli -u $REDIS_URL CLIENT LIST | grep django | wc -l'

# Check health endpoint
curl http://localhost:8000/health
# Expected: 200 OK

# Monitor Redis key creation
redis-cli -u $REDIS_URL MONITOR | grep -E "SET|GET"
# Should see cache keys being created
```

**Verification**:
- [ ] Application logs show no errors
- [ ] Redis connections established
- [ ] Health check returns 200 OK
- [ ] Cache keys being created

**Time**: 2 minutes

**Expected Logs**:
```
INFO: Cache middleware initialized
INFO: Namespace manager initialized
INFO: Cacheops configured with Redis DB 2
INFO: Application ready
```

---

### Step 3.7: Disable Maintenance Mode (Option B Only)

**If using Option B**:

```bash
# Disable maintenance page
# Method depends on your infrastructure
```

**Notification**:
- [ ] Maintenance page disabled
- [ ] Users notified of completion
- [ ] End time recorded: __________

**Time**: 1 minute (Option B only)


---

## Phase 4: Post-Migration Validation

**Duration**: 15 minutes  
**Downtime**: No

### Step 4.1: Immediate Health Checks (First 5 Minutes)

**Commands**:
```bash
# 1. Application health
curl http://localhost:8000/health
# Expected: 200 OK

# 2. Redis connections
redis-cli -u $REDIS_URL CLIENT LIST | grep django
# Expected: Multiple connections from Django

# 3. Cache operations
python manage.py shell
```

**Python Verification**:
```python
from django.core.cache import cache

# Test basic cache operations
cache.set('health_check', 'success', 60)
result = cache.get('health_check')
print(f"Cache test: {result}")
# Expected: Cache test: success

cache.delete('health_check')
exit()
```

**4. User Login Test**:
```bash
# Test user authentication
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","password":"testpass"}'
# Expected: 200 OK with token
```

**5. Monitor Redis Key Creation**:
```bash
# Watch cache keys being created
redis-cli -u $REDIS_URL MONITOR | head -20
# Should see keys with format: cache:{user_id}:v{version}:cacheops:{hash}
```

**Verification**:
- [ ] Application responds to requests
- [ ] Redis connections established
- [ ] Cache operations work
- [ ] User login successful
- [ ] Cache keys have correct format
- [ ] No errors in application logs

**Time**: 5 minutes

---

### Step 4.2: Validate Existing Cache Patterns

**Commands**:
```bash
# Run existing cache validation tests
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
# ----------------------------------------------------------------------
# Ran 27 tests in 2.5s
# OK
```

**Verification**:
- [ ] All 27 tests pass
- [ ] No test failures
- [ ] No errors or warnings

**Time**: 3 minutes

**Troubleshooting**: If tests fail, see [Troubleshooting Guide](#troubleshooting-guide)

---

### Step 4.3: Test Key Application Functions

**Manual Testing Checklist**:

1. **User Authentication**:
   - [ ] Log in as test user
   - [ ] Verify session works
   - [ ] Log out and log back in

2. **Invoice Operations**:
   - [ ] View invoice list
   - [ ] View invoice detail
   - [ ] Create new invoice (if safe in production)
   - [ ] Verify invoice sequence increments

3. **Calendar Reminders**:
   - [ ] View calendar
   - [ ] Check reminder notifications
   - [ ] Verify no duplicate reminders

4. **Workflow Notifications**:
   - [ ] View workflow list
   - [ ] Check notification stream
   - [ ] Verify notifications delivered

5. **WhatsApp Integration**:
   - [ ] Send test message (if safe)
   - [ ] Verify token caching works
   - [ ] Check no authentication errors

**Verification**:
- [ ] All key functions work
- [ ] No user-facing errors
- [ ] Performance is acceptable

**Time**: 5 minutes

---

### Step 4.4: Verify Cache Metrics

**Commands**:
```bash
# Check Redis key count (should be growing)
redis-cli -u $REDIS_URL DBSIZE
# Expected: > 0 and increasing

# Check Redis memory usage
redis-cli -u $REDIS_URL INFO memory | grep used_memory_human
# Expected: < 256MB (production limit)

# Check cache hit/miss stats
redis-cli -u $REDIS_URL INFO stats | grep -E "keyspace|hits|misses"

# Monitor cache key creation rate
watch -n 10 'redis-cli -u $REDIS_URL DBSIZE'
# Should see steady increase as cache warms up
```

**Verification**:
- [ ] Redis key count is increasing
- [ ] Memory usage is within limits
- [ ] Cache hit rate is improving
- [ ] No memory warnings

**Time**: 2 minutes

**Expected Metrics** (after 15 minutes):
- Key count: 100-1000 keys
- Memory usage: 10-50 MB
- Cache hit rate: 20-40% (will improve over time)


---

## Phase 5: Monitoring and Optimization

**Duration**: First 24 hours  
**Downtime**: No

### Step 5.1: Continuous Monitoring (First Hour)

**Monitoring Points**:

1. **Application Logs**:
```bash
# Monitor for cache-related errors
tail -f /path/to/application.log | grep -iE "cache|redis|error"
```

2. **Redis Memory**:
```bash
# Monitor memory usage every 5 minutes
watch -n 300 'redis-cli -u $REDIS_URL INFO memory | grep used_memory_human'
```

3. **Cache Hit Rate**:
```bash
# Check cache effectiveness
redis-cli -u $REDIS_URL INFO stats | grep -E "keyspace_hits|keyspace_misses"
```

4. **Application Performance**:
```bash
# Monitor response times (method depends on your monitoring setup)
# Example: Check application metrics dashboard
```

**Verification Checklist** (check every 15 minutes):
- [ ] No increase in error rate
- [ ] Memory usage stable and < 256MB
- [ ] Cache hit rate increasing
- [ ] Response times acceptable
- [ ] No user complaints

**Time**: 1 hour (periodic checks)

---

### Step 5.2: Cache Warmup Monitoring

**Expected Cache Warmup Timeline**:

| Time After Migration | Expected Cache Hit Rate | Expected Key Count |
|---------------------|------------------------|-------------------|
| 5 minutes | 10-20% | 50-200 |
| 15 minutes | 30-40% | 200-500 |
| 1 hour | 50-60% | 500-2000 |
| 4 hours | 70-80% | 2000-5000 |
| 24 hours | 80-90% | 5000-10000 |

**Commands**:
```bash
# Calculate cache hit rate
redis-cli -u $REDIS_URL INFO stats | grep -E "keyspace_hits|keyspace_misses" | \
  awk '{sum+=$2} END {print "Hit rate: " (sum>0 ? $1/$2*100 : 0) "%"}'

# Check key count growth
redis-cli -u $REDIS_URL DBSIZE
```

**Verification**:
- [ ] Cache hit rate following expected timeline
- [ ] Key count growing steadily
- [ ] No sudden drops in hit rate

**Time**: Periodic checks over 24 hours

---

### Step 5.3: Memory Usage Optimization

**Monitor Memory Usage**:
```bash
# Detailed memory breakdown
redis-cli -u $REDIS_URL INFO memory

# Key metrics to watch:
# - used_memory_human: Total memory used
# - used_memory_peak_human: Peak memory usage
# - mem_fragmentation_ratio: Memory fragmentation (ideal: 1.0-1.5)
```

**If Memory Exceeds 200MB** (80% of 256MB limit):

1. **Check Key Distribution**:
```bash
# Sample keys to see what's being cached
redis-cli -u $REDIS_URL --scan --pattern "cache:*" | head -20
```

2. **Adjust TTL Values** (if needed):
```python
# Edit settings/base.py
CACHEOPS = {
    # Reduce TTL for high-volume models
    'invoices.invoice': {'ops': 'all', 'timeout': 60 * 2},  # 2 min instead of 5
    'customer_applications.docapplication': {'ops': 'all', 'timeout': 60 * 2},
}
```

3. **Configure Maxmemory Policy**:
```bash
# Set eviction policy (if not already set)
redis-cli -u $REDIS_URL CONFIG SET maxmemory 256mb
redis-cli -u $REDIS_URL CONFIG SET maxmemory-policy allkeys-lru

# Verify
redis-cli -u $REDIS_URL CONFIG GET maxmemory-policy
# Expected: allkeys-lru
```

**Verification**:
- [ ] Memory usage stable
- [ ] No memory warnings
- [ ] Eviction policy configured
- [ ] TTL values appropriate

**Time**: As needed

---

### Step 5.4: Performance Benchmarking

**Run Benchmark** (after 4 hours of warmup):

```bash
# Run cache benchmark
python manage.py benchmark_cache --users 50 --queries 500 --report benchmark_post_migration.json

# Expected output:
# Benchmark Results:
# - Cache hit rate: 70-80%
# - Avg response time (cached): 5-15ms
# - Avg response time (uncached): 50-150ms
# - Cache invalidation time: < 1ms (O(1))
# - Memory per user: 100-500KB
```

**Compare with Pre-Migration Baseline**:
```bash
# Compare with baseline (if available)
diff benchmark_baseline.json benchmark_post_migration.json
```

**Verification**:
- [ ] Cache hit rate > 70%
- [ ] Cached response time < 20ms
- [ ] Invalidation time < 1ms (O(1))
- [ ] No performance regression

**Time**: 10 minutes

---

### Step 5.5: Extended Monitoring (24 Hours)

**Daily Monitoring Checklist**:

**Morning Check** (8 AM):
- [ ] Review overnight logs for errors
- [ ] Check Redis memory usage
- [ ] Verify cache hit rate
- [ ] Check application performance metrics

**Afternoon Check** (2 PM):
- [ ] Monitor peak traffic performance
- [ ] Check for any user-reported issues
- [ ] Verify cache effectiveness

**Evening Check** (8 PM):
- [ ] Review daily error logs
- [ ] Check memory usage trends
- [ ] Verify system stability

**Metrics to Track**:
```bash
# Daily summary script
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
EOF

chmod +x daily_cache_summary.sh
./daily_cache_summary.sh
```

**Verification**:
- [ ] No critical errors
- [ ] Memory usage stable
- [ ] Performance acceptable
- [ ] User satisfaction maintained

**Time**: 3 checks per day, 5 minutes each


---

## Rollback Procedures

### When to Rollback

**Rollback Triggers**:
- Critical errors preventing application startup
- Data corruption or loss
- Unacceptable performance degradation (> 50% slower)
- Redis connection failures that don't resolve
- Memory usage exceeding limits causing crashes
- User-facing errors affecting > 10% of users

**Decision Point**: Within 30 minutes of deployment

---

### Rollback Procedure

**Duration**: 15 minutes

### Step R1: Stop Application

```bash
# Stop Django application
sudo systemctl stop django-app
# or
docker-compose stop web
```

**Time**: 1 minute

---

### Step R2: Restore Database (If Migration Applied)

**Only if database migration was applied**:

```bash
# Drop current database
dropdb $DB_NAME

# Restore from backup
pg_restore -h $DB_HOST -U $DB_USER -d $DB_NAME -c \
  migration_backup_YYYYMMDD_HHMMSS.dump

# Verify restoration
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "\dt" | grep userprofile
```

**Alternative** (if drop not possible):

```bash
# Rollback migration only
python manage.py migrate core 0021

# Verify
python manage.py showmigrations core | grep 0022
# Expected: [ ] 0022_add_cache_enabled_to_userprofile
```

**Time**: 5 minutes

---

### Step R3: Restore Configuration

```bash
# Restore old settings files
cp migration_state/YYYYMMDD_HHMMSS/base.py backend/business_suite/settings/
cp migration_state/YYYYMMDD_HHMMSS/cache_backends.py backend/business_suite/settings/

# Verify old cache backend restored
grep "BACKEND" backend/business_suite/settings/base.py
# Expected: 'django.core.cache.backends.locmem.LocMemCache'
```

**Time**: 2 minutes

---

### Step R4: Clear Redis (Optional)

```bash
# Clear Redis databases to avoid confusion
redis-cli -u $REDIS_URL FLUSHDB
redis-cli -u $REDIS_URL -n 2 FLUSHDB
```

**Time**: 1 minute

---

### Step R5: Restart Application

```bash
# Start Django application
sudo systemctl start django-app
# or
docker-compose up -d web

# Verify startup
curl http://localhost:8000/health
# Expected: 200 OK
```

**Time**: 2 minutes

---

### Step R6: Verify Rollback

```bash
# Check cache backend
python manage.py shell -c "from django.conf import settings; print(settings.CACHES['default']['BACKEND'])"
# Expected: django.core.cache.backends.locmem.LocMemCache

# Test application
curl http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","password":"testpass"}'
# Expected: 200 OK

# Check logs for errors
tail -50 /path/to/application.log
```

**Verification**:
- [ ] Old cache backend active
- [ ] Application responds
- [ ] User login works
- [ ] No errors in logs

**Time**: 4 minutes

---

### Step R7: Notify Team

```bash
# Send rollback notification
echo "Migration rolled back at $(date). System restored to previous state." | \
  mail -s "Cache Migration Rollback" team@example.com
```

**Notification Checklist**:
- [ ] Team notified of rollback
- [ ] Reason for rollback documented
- [ ] Next steps identified
- [ ] Post-mortem scheduled

**Time**: 1 minute

---

### Post-Rollback Actions

1. **Document Issues**:
   - What went wrong?
   - What were the symptoms?
   - What logs/metrics showed the problem?

2. **Analyze Root Cause**:
   - Review error logs
   - Check Redis logs
   - Examine application metrics

3. **Plan Retry**:
   - Address root cause
   - Update runbook if needed
   - Schedule new migration attempt


---

## Troubleshooting Guide

### Issue 1: Redis Connection Failures

**Symptoms**:
- Application logs show "Redis connection refused"
- Cache operations fail
- Application slow or unresponsive

**Diagnosis**:
```bash
# Check Redis is running
redis-cli -u $REDIS_URL ping
# If fails: Redis is down

# Check network connectivity
telnet redis-host 6379
# If fails: Network issue

# Check Redis logs
tail -50 /var/log/redis/redis-server.log
```

**Solutions**:

1. **Redis is down**:
```bash
# Start Redis
sudo systemctl start redis
# or
docker-compose start redis
```

2. **Network issue**:
```bash
# Check firewall rules
sudo iptables -L | grep 6379

# Check Redis bind address
redis-cli CONFIG GET bind
# Should include your application server IP
```

3. **Connection pool exhausted**:
```bash
# Check active connections
redis-cli CLIENT LIST | wc -l

# Increase max_connections in settings if needed
# Edit settings/cache_backends.py:
# "max_connections": 100  # Increase from 50
```

**Fallback**: Application will automatically fall back to database queries

---

### Issue 2: High Memory Usage

**Symptoms**:
- Redis memory usage > 200MB
- Redis evicting keys frequently
- Application performance degrading

**Diagnosis**:
```bash
# Check memory usage
redis-cli -u $REDIS_URL INFO memory | grep used_memory_human

# Check eviction stats
redis-cli -u $REDIS_URL INFO stats | grep evicted_keys

# Sample keys to see what's cached
redis-cli -u $REDIS_URL --scan --pattern "cache:*" | head -50
```

**Solutions**:

1. **Reduce TTL values**:
```python
# Edit settings/base.py
CACHEOPS = {
    # Reduce timeout for high-volume models
    'invoices.invoice': {'ops': 'all', 'timeout': 60 * 2},  # 2 min
    'customer_applications.docapplication': {'ops': 'all', 'timeout': 60 * 2},
}

# Restart application
sudo systemctl restart django-app
```

2. **Configure maxmemory policy**:
```bash
# Set memory limit and eviction policy
redis-cli -u $REDIS_URL CONFIG SET maxmemory 256mb
redis-cli -u $REDIS_URL CONFIG SET maxmemory-policy allkeys-lru

# Make permanent in redis.conf
echo "maxmemory 256mb" >> /etc/redis/redis.conf
echo "maxmemory-policy allkeys-lru" >> /etc/redis/redis.conf
```

3. **Clear cache if needed**:
```bash
# Clear all cache data
redis-cli -u $REDIS_URL FLUSHDB
redis-cli -u $REDIS_URL -n 2 FLUSHDB

# Cache will rebuild automatically
```

---

### Issue 3: Cache Keys Not Being Created

**Symptoms**:
- Redis MONITOR shows no cache keys
- Cache hit rate is 0%
- All requests hitting database

**Diagnosis**:
```bash
# Check middleware is active
python manage.py shell
>>> from django.conf import settings
>>> 'cache.middleware.CacheMiddleware' in settings.MIDDLEWARE
# Expected: True

# Check cacheops is configured
>>> settings.CACHEOPS
# Expected: Dictionary with model configs

# Check user has caching enabled
>>> from core.models import UserProfile
>>> profile = UserProfile.objects.first()
>>> profile.cache_enabled
# Expected: True
```

**Solutions**:

1. **Middleware not active**:
```python
# Add to settings/base.py MIDDLEWARE list
MIDDLEWARE = [
    # ... other middleware
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'cache.middleware.CacheMiddleware',  # Add after auth
    # ... other middleware
]

# Restart application
```

2. **Cacheops not configured**:
```python
# Add to settings/base.py
CACHEOPS_REDIS = os.getenv("REDIS_URL", "redis://redis:6379/1").replace("/1", "/2")
CACHEOPS = {
    'auth.user': {'ops': 'get', 'timeout': 60 * 15},
    # ... other models
}

# Restart application
```

3. **User caching disabled**:
```python
# Enable caching for user
python manage.py shell
>>> from core.models import UserProfile
>>> profile = UserProfile.objects.get(user__username='testuser')
>>> profile.cache_enabled = True
>>> profile.save()
```

---

### Issue 4: Slow Performance After Migration

**Symptoms**:
- Application slower than before migration
- Response times > 2x pre-migration baseline
- Users complaining about slowness

**Diagnosis**:
```bash
# Check cache hit rate
redis-cli -u $REDIS_URL INFO stats | grep -E "keyspace_hits|keyspace_misses"

# Check Redis latency
redis-cli -u $REDIS_URL --latency
# Should be < 5ms

# Check database query count
# (Method depends on your monitoring setup)
```

**Solutions**:

1. **Cache not warmed up yet**:
```
# Wait 15-30 minutes for cache to populate
# Monitor cache hit rate improvement
watch -n 60 'redis-cli -u $REDIS_URL INFO stats | grep keyspace_hits'
```

2. **Redis latency high**:
```bash
# Check Redis server load
redis-cli -u $REDIS_URL INFO cpu

# Check network latency
ping redis-host

# Consider moving Redis closer to application servers
```

3. **Database queries not being cached**:
```python
# Verify cacheops is working
python manage.py shell
>>> from cacheops import invalidate_all
>>> invalidate_all()  # Clear and rebuild cache
```

---

### Issue 5: Existing Cache Patterns Broken

**Symptoms**:
- WhatsApp token errors
- Cron jobs running multiple times
- Invoice sequence errors
- Stream cursor issues

**Diagnosis**:
```bash
# Run validation tests
python manage.py test backend.cache.tests.test_existing_cache_validation -v 2

# Check specific pattern
python manage.py shell
>>> from django.core.cache import cache
>>> cache.set('test_key', 'test_value', 60)
>>> cache.get('test_key')
# Expected: 'test_value'
```

**Solutions**:

1. **Cache operations failing**:
```bash
# Check Redis is accessible
redis-cli -u $REDIS_URL ping

# Check cache backend configuration
python manage.py shell
>>> from django.conf import settings
>>> settings.CACHES['default']['BACKEND']
# Expected: 'django_redis.cache.RedisCache'
```

2. **Key prefix conflicts**:
```bash
# Check key prefix
redis-cli -u $REDIS_URL KEYS "*" | head -20

# Verify no conflicts with namespace keys
# Namespace keys: cache:{user_id}:v{version}:cacheops:*
# Existing keys: META_*, CLEAR_CACHE_*, invoice_seq_*, etc.
```

3. **Database issue**:
```bash
# Check Redis database number
redis-cli -u $REDIS_URL CLIENT LIST | grep db=1
# Existing patterns should use db=1
```

---

### Issue 6: Migration Validation Tests Failing

**Symptoms**:
- Some of the 27 validation tests fail
- Specific cache patterns not working

**Diagnosis**:
```bash
# Run tests with verbose output
python manage.py test backend.cache.tests.test_existing_cache_validation -v 3

# Check which tests fail
python manage.py test backend.cache.tests.test_existing_cache_validation 2>&1 | grep FAIL
```

**Solutions**:

1. **Redis not accessible**:
```bash
# Verify Redis connection
redis-cli -u $REDIS_URL ping
```

2. **Test database issue**:
```bash
# Tests use Redis DB 15
redis-cli -u $REDIS_URL -n 15 FLUSHDB

# Re-run tests
python manage.py test backend.cache.tests.test_existing_cache_validation
```

3. **Configuration issue**:
```bash
# Check test settings
python manage.py test --settings=business_suite.settings.test
```

---

### Issue 7: Frontend Cache Not Synchronizing

**Symptoms**:
- Frontend shows stale data
- Cache version headers missing
- IndexedDB not clearing on version change

**Diagnosis**:
```bash
# Check response headers
curl -I http://localhost:8000/api/invoices/
# Should include: X-Cache-Version: {number}

# Check middleware is active
python manage.py shell
>>> from django.conf import settings
>>> 'cache.middleware.CacheMiddleware' in settings.MIDDLEWARE
# Expected: True
```

**Solutions**:

1. **Headers not being added**:
```python
# Verify middleware order
# cache.middleware.CacheMiddleware must be after auth middleware
```

2. **Frontend interceptor not active**:
```typescript
// Check Angular app.config.ts
// HTTP_INTERCEPTORS should include CacheInterceptor
```

3. **Manual frontend cache clear**:
```javascript
// In browser console
indexedDB.deleteDatabase('hybrid-cache');
location.reload();
```

---

### Getting Help

**If issues persist**:

1. **Collect diagnostic information**:
```bash
# Create diagnostic bundle
mkdir -p diagnostics/$(date +%Y%m%d_%H%M%S)
cd diagnostics/$(date +%Y%m%d_%H%M%S)

# Application logs
tail -500 /path/to/application.log > app_logs.txt

# Redis info
redis-cli -u $REDIS_URL INFO > redis_info.txt

# Redis keys sample
redis-cli -u $REDIS_URL --scan --pattern "*" | head -100 > redis_keys.txt

# Django settings
python manage.py diffsettings > django_settings.txt

# System info
uname -a > system_info.txt
free -h >> system_info.txt
df -h >> system_info.txt
```

2. **Contact support**:
   - Email: support@example.com
   - Slack: #cache-migration
   - On-call: +1-XXX-XXX-XXXX

3. **Escalation path**:
   - Level 1: Development team
   - Level 2: Technical lead
   - Level 3: System administrator


---

## Success Criteria

### Technical Success Metrics

**Immediate** (within 1 hour):
- [ ] Application starts without errors
- [ ] Redis connections established
- [ ] Cache operations work correctly
- [ ] All 27 validation tests pass
- [ ] No increase in error rate
- [ ] Response times ≤ pre-migration baseline

**Short-term** (within 24 hours):
- [ ] Cache hit rate > 70%
- [ ] Memory usage < 200MB (80% of limit)
- [ ] No cache-related errors in logs
- [ ] User-reported issues = 0
- [ ] Performance meets or exceeds baseline

**Long-term** (within 1 week):
- [ ] Cache hit rate > 80%
- [ ] Memory usage stable
- [ ] No performance degradation
- [ ] System stability maintained
- [ ] User satisfaction maintained

---

### Functional Success Metrics

**Core Functionality**:
- [ ] Users can log in
- [ ] Invoice generation works
- [ ] Calendar reminders work
- [ ] Workflow notifications work
- [ ] WhatsApp integration works
- [ ] Cron jobs execute correctly

**Cache Functionality**:
- [ ] Per-user cache isolation works
- [ ] Cache clear functionality works
- [ ] Automatic invalidation works
- [ ] Frontend cache synchronization works
- [ ] Existing cache patterns work

---

### Performance Success Metrics

**Response Times**:
- [ ] Cached requests: < 20ms (target: 5-15ms)
- [ ] Uncached requests: < 200ms (target: 50-150ms)
- [ ] Cache invalidation: < 1ms (O(1) operation)

**Cache Effectiveness**:
- [ ] Hit rate: > 80% (after warmup)
- [ ] Miss rate: < 20%
- [ ] Eviction rate: < 5% of total operations

**Resource Usage**:
- [ ] Redis memory: < 200MB
- [ ] Redis CPU: < 20%
- [ ] Application CPU: No increase
- [ ] Database load: Reduced by 50-80%

---

### Business Success Metrics

**User Experience**:
- [ ] No user complaints about performance
- [ ] No increase in support tickets
- [ ] User satisfaction maintained or improved

**System Reliability**:
- [ ] Uptime: 99.9%+
- [ ] Error rate: < 0.1%
- [ ] No data loss
- [ ] No security incidents

---

## Migration Sign-Off

### Pre-Migration Sign-Off

**Completed By**: _____________  
**Date**: _____________  
**Time**: _____________

**Checklist**:
- [ ] Pre-migration checklist completed
- [ ] Backups created and verified
- [ ] Team notified
- [ ] Rollback plan ready

**Approvals**:
- [ ] Migration Lead: _____________ Date: _______
- [ ] Technical Lead: _____________ Date: _______
- [ ] Operations: _____________ Date: _______

---

### Post-Migration Sign-Off

**Completed By**: _____________  
**Date**: _____________  
**Time**: _____________

**Verification**:
- [ ] All phases completed successfully
- [ ] All validation tests passed
- [ ] No critical issues
- [ ] System is stable
- [ ] Success criteria met

**Approvals**:
- [ ] Migration Lead: _____________ Date: _______
- [ ] Technical Lead: _____________ Date: _______
- [ ] Operations: _____________ Date: _______

---

### Migration Summary

**Migration Details**:
- Start Time: _____________
- End Time: _____________
- Total Duration: _____________
- Downtime: _____________ (if any)

**Issues Encountered**:
1. _____________
2. _____________
3. _____________

**Resolutions**:
1. _____________
2. _____________
3. _____________

**Lessons Learned**:
1. _____________
2. _____________
3. _____________

**Recommendations for Future**:
1. _____________
2. _____________
3. _____________

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

## Appendix B: Configuration Reference

### Environment Variables

```bash
REDIS_URL=redis://redis:6379/1
CACHE_KEY_PREFIX=revisbali
CACHE_DEFAULT_TIMEOUT=300
```

### Redis Databases

- DB 0: PgQueuer task queue
- DB 1: Django cache (default)
- DB 2: Cacheops ORM cache
- DB 3: Benchmark system
- DB 15: Test environment

### Key Patterns

- Django cache: `revisbali:cache:*`
- Cacheops: `cache:{user_id}:v{version}:cacheops:{hash}`
- User version: `cache_user_version:{user_id}`
- Existing patterns: `META_*`, `CLEAR_CACHE_*`, `invoice_seq_*`, etc.

### Important Files

- Settings: `backend/business_suite/settings/base.py`
- Cache backends: `backend/business_suite/settings/cache_backends.py`
- Middleware: `backend/cache/middleware.py`
- Namespace: `backend/cache/namespace.py`
- Validation tests: `backend/cache/tests/test_existing_cache_validation.py`

---

## Appendix C: Contact Information

### Support Contacts

**Technical Issues**:
- Development Team: _____________
- Operations Team: _____________
- On-Call Engineer: _____________

**Escalation**:
- Technical Lead: _____________
- System Administrator: _____________
- CTO: _____________

### Communication Channels

- Email: support@example.com
- Slack: #cache-migration
- Phone: +1-XXX-XXX-XXXX
- Emergency: +1-XXX-XXX-XXXX

---

## Appendix D: Additional Resources

### Documentation

- **Architecture**: `backend/cache/ARCHITECTURE.md`
- **API Documentation**: `backend/cache/API_DOCUMENTATION.md`
- **Pre-Migration Checklist**: `backend/cache/PRE_MIGRATION_CHECKLIST.md`
- **Validation Results**: `backend/cache/tests/VALIDATION_RESULTS.md`
- **Benchmark Results**: `backend/cache/tests/BENCHMARK_RESULTS.md`
- **Optimization Notes**: `backend/cache/OPTIMIZATION_NOTES.md`

### Specifications

- **Requirements**: `.kiro/specs/hybrid-cache-system/requirements.md`
- **Design**: `.kiro/specs/hybrid-cache-system/design.md`
- **Tasks**: `.kiro/specs/hybrid-cache-system/tasks.md`

### External Resources

- **Django Cache Framework**: https://docs.djangoproject.com/en/stable/topics/cache/
- **django-redis**: https://github.com/jazzband/django-redis
- **django-cacheops**: https://github.com/Suor/django-cacheops
- **Redis Documentation**: https://redis.io/documentation

---

**END OF RUNBOOK**

*This runbook should be followed step-by-step during production migration. Keep this document accessible during the migration process.*

