# Pre-Migration Checklist: Hybrid Cache System

**Migration Date**: _____________  
**Performed By**: _____________  
**System**: Django 6 + Angular 19 Application  
**Migration Type**: LocMemCache → Redis-based Hybrid Cache System

---

## Overview

This checklist ensures a safe migration from the current cache setup to the new Redis-based hybrid cache system with per-user namespace isolation and O(1) invalidation. The migration has been thoroughly tested and validated - all existing cache patterns work without code changes.

**Key Points**:
- ✅ All existing cache usage patterns validated (see `VALIDATION_RESULTS.md`)
- ✅ No code changes required for existing cache logic
- ✅ No performance regression detected
- ⚠️ Current cache data will NOT be preserved (by design - fresh start)
- ✅ System will gracefully fall back to database queries if Redis fails

---

## Section 1: Current Cache Usage Documentation

### 1.1 Existing Cache Patterns ✅ VALIDATED

All patterns below have been tested and work correctly with the new system:

#### Pattern 1: Meta WhatsApp Access Token Caching
**Purpose**: Cache OAuth access tokens for Meta WhatsApp API  
**Cache Keys**:
- `meta_whatsapp:runtime_access_token`
- `meta_whatsapp:runtime_access_token_expires_at`

**Operations Used**:
- `cache.set()` - Store tokens with TTL
- `cache.get()` - Retrieve cached tokens
- `cache.delete_many()` - Clear token cache

**Status**: ✅ 4/4 tests passed


#### Pattern 2: Cron Job Lock Coordination
**Purpose**: Prevent duplicate cron job execution across multiple workers  
**Cache Keys**:
- `cron:full_backup:enqueue_lock`
- `cron:full_backup:run_lock`
- `cron:clear_cache:enqueue_lock`
- `cron:clear_cache:run_lock`

**Operations Used**:
- `cache.add()` - Atomic lock acquisition
- `cache.get()` - Lock status checking
- `cache.delete()` - Lock release
- `cache.delete_many()` - Bulk lock reset

**Status**: ✅ 5/5 tests passed

#### Pattern 3: Invoice Sequence Cache
**Purpose**: Generate sequential invoice numbers with atomic increment  
**Cache Keys**:
- `invoice_seq:2026` (year-based keys)

**Operations Used**:
- `cache.add()` - Initialize sequence
- `cache.incr()` - Atomic increment
- `cache.set()` - Update sequence
- `cache.get()` - Retrieve current sequence

**Status**: ✅ 6/6 tests passed

#### Pattern 4: Calendar Reminder Stream Cursor Cache
**Purpose**: Track event stream position for calendar reminders  
**Cache Keys**:
- `calendar_reminders:stream:cursor`
- `calendar_reminders:stream:last_event`

**Operations Used**:
- `cache.add()` - Initialize cursor
- `cache.incr()` - Increment cursor
- `cache.set()` - Store event data
- `cache.get()` - Retrieve cursor/event
- `cache.delete_many()` - Reset state

**Status**: ✅ 5/5 tests passed

#### Pattern 5: Workflow Notification Stream Cursor Cache
**Purpose**: Track event stream position for workflow notifications  
**Cache Keys**:
- `workflow_notifications:stream:cursor`
- `workflow_notifications:stream:last_event`

**Operations Used**:
- `cache.add()` - Initialize cursor
- `cache.incr()` - Increment cursor
- `cache.set()` - Store event data
- `cache.get()` - Retrieve cursor/event
- `cache.delete_many()` - Reset state

**Status**: ✅ 5/5 tests passed

### 1.2 Cache Usage Summary

**Total Cache Patterns**: 5  
**Total Operations Validated**: 27 tests  
**Backward Compatibility**: 100% - No code changes required

**Reference**: See `backend/cache/tests/VALIDATION_RESULTS.md` for detailed test results

---

## Section 2: Redis Configuration Verification

### 2.1 Environment Variables Check

**Required Environment Variables**:

```bash
# Primary Redis connection URL
REDIS_URL=redis://redis:6379/1

# Optional: Cache key prefix (defaults to 'revisbali')
CACHE_KEY_PREFIX=revisbali
```

**Verification Commands**:

```bash
# Check if REDIS_URL is set
echo $REDIS_URL

# Verify Redis is accessible
redis-cli -u $REDIS_URL ping
# Expected output: PONG

# Check Redis version (should be 7.x or higher)
redis-cli -u $REDIS_URL INFO server | grep redis_version
# Expected: redis_version:7.x.x
```

**Checklist**:
- [ ] `REDIS_URL` environment variable is set
- [ ] Redis server responds to PING command
- [ ] Redis version is 7.x or higher
- [ ] `CACHE_KEY_PREFIX` is set (or using default)


### 2.2 Redis Database Allocation

The system uses multiple Redis databases for isolation:

| Database | Purpose | Configuration |
|----------|---------|---------------|
| DB 0 | PgQueuer task queue | Default PgQueuer configuration |
| DB 1 | Django cache (default) | `REDIS_URL` environment variable |
| DB 2 | Cacheops ORM cache | Auto-configured from `REDIS_URL` |
| DB 15 | Test database | Used during test runs only |

**Verification Commands**:

```bash
# Check database allocation
redis-cli -u $REDIS_URL INFO keyspace
# Should show info for db0, db1, db2 if they have keys

# Verify no key conflicts between databases
redis-cli -u $REDIS_URL SELECT 1
redis-cli -u $REDIS_URL KEYS "cache:*" | head -5

redis-cli -u $REDIS_URL SELECT 2
redis-cli -u $REDIS_URL KEYS "*" | head -5
```

**Checklist**:
- [ ] Redis supports multiple databases (not Redis Cluster)
- [ ] Database 1 is available for Django cache
- [ ] Database 2 is available for Cacheops
- [ ] No key conflicts between databases

### 2.3 Redis Connection Pool Configuration

**Current Configuration** (from `settings/cache_backends.py`):

```python
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.getenv("REDIS_URL", "redis://redis:6379/1"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "CONNECTION_POOL_KWARGS": {
                "max_connections": 50,
                "retry_on_timeout": True,
            },
            "SOCKET_CONNECT_TIMEOUT": 5,
            "SOCKET_TIMEOUT": 5,
        },
        "TIMEOUT": 300,  # 5 minutes default TTL
        "KEY_PREFIX": os.getenv("CACHE_KEY_PREFIX", "revisbali"),
    }
}
```

**Verification**:

```bash
# Check current Redis connections
redis-cli -u $REDIS_URL CLIENT LIST | wc -l
# Should show active connections

# Monitor Redis during application startup
redis-cli -u $REDIS_URL MONITOR
# (Run in separate terminal, then start Django)
```

**Checklist**:
- [ ] Connection pool settings are appropriate for load
- [ ] Timeout values (5 seconds) are acceptable
- [ ] Default TTL (300 seconds) is appropriate
- [ ] Key prefix is set correctly

### 2.4 Redis Memory and Performance

**Verification Commands**:

```bash
# Check Redis memory usage
redis-cli -u $REDIS_URL INFO memory | grep used_memory_human
# Note current usage

# Check Redis performance
redis-cli -u $REDIS_URL --latency
# Should show low latency (< 1ms for local Redis)

# Check Redis configuration
redis-cli -u $REDIS_URL CONFIG GET maxmemory
redis-cli -u $REDIS_URL CONFIG GET maxmemory-policy
# Recommended: maxmemory-policy=allkeys-lru
```

**Checklist**:
- [ ] Redis has sufficient memory allocated
- [ ] Redis latency is acceptable (< 5ms)
- [ ] Maxmemory policy is configured (recommend: allkeys-lru)
- [ ] Redis persistence is configured if needed (RDB/AOF)

---

## Section 3: Database Migration Verification

### 3.1 User Profile Cache Field Migration

**Migration**: `backend/core/migrations/0022_add_cache_enabled_to_userprofile.py`

**Changes**:
- Adds `cache_enabled` boolean field to UserProfile model
- Default value: `True` (caching enabled for all users)
- Indexed for fast lookup

**Verification Commands**:

```bash
# Check if migration exists
ls -la backend/core/migrations/0022_add_cache_enabled_to_userprofile.py

# Check migration status
python manage.py showmigrations core | grep 0022

# Verify database schema (after migration)
python manage.py dbshell
\d core_userprofile
# Should show cache_enabled column
```

**Checklist**:
- [ ] Migration file exists
- [ ] Migration has been applied (`[X]` in showmigrations)
- [ ] `cache_enabled` column exists in database
- [ ] Index on `cache_enabled` exists
- [ ] All existing users have `cache_enabled=True` by default


### 3.2 Database Schema Verification

**SQL Verification** (run in `python manage.py dbshell`):

```sql
-- Verify cache_enabled column
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

-- Check current user cache settings
SELECT id, username, cache_enabled 
FROM auth_user 
JOIN core_userprofile ON auth_user.id = core_userprofile.user_id 
LIMIT 10;
```

**Checklist**:
- [ ] `cache_enabled` column exists with correct type (boolean)
- [ ] Default value is `true`
- [ ] Column is NOT NULL
- [ ] Index exists on `cache_enabled`
- [ ] Sample users show `cache_enabled=true`

---

## Section 4: Application Configuration Verification

### 4.1 Django Settings Check

**Files to Verify**:
- `backend/business_suite/settings/base.py`
- `backend/business_suite/settings/cache_backends.py`

**Verification Commands**:

```bash
# Check cache backend configuration
python manage.py shell
>>> from django.conf import settings
>>> settings.CACHES['default']['BACKEND']
# Expected: 'django_redis.cache.RedisCache'

>>> settings.CACHES['default']['LOCATION']
# Expected: Your REDIS_URL value

>>> settings.CACHEOPS_REDIS
# Expected: Redis URL with /2 database

# Test cache connection
>>> from django.core.cache import cache
>>> cache.set('test_key', 'test_value', 60)
>>> cache.get('test_key')
# Expected: 'test_value'

>>> cache.delete('test_key')
```

**Checklist**:
- [ ] Django cache backend is `django_redis.cache.RedisCache`
- [ ] Cache location points to correct Redis URL
- [ ] Cacheops Redis URL uses database 2
- [ ] Test cache operations work correctly
- [ ] No errors in Django settings validation

### 4.2 Middleware Configuration

**Verify Middleware Order** (in `settings/base.py`):

```python
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'cache.middleware.CacheMiddleware',  # ← Must be AFTER auth
    # ... other middleware
]
```

**Verification**:

```bash
# Check middleware configuration
python manage.py shell
>>> from django.conf import settings
>>> middleware = settings.MIDDLEWARE
>>> auth_index = middleware.index('django.contrib.auth.middleware.AuthenticationMiddleware')
>>> cache_index = middleware.index('cache.middleware.CacheMiddleware')
>>> cache_index > auth_index
# Expected: True (cache middleware must come after auth)
```

**Checklist**:
- [ ] `cache.middleware.CacheMiddleware` is in MIDDLEWARE list
- [ ] Cache middleware comes AFTER authentication middleware
- [ ] No duplicate cache middleware entries

### 4.3 Cacheops Configuration

**Verify Cacheops Settings** (in `settings/base.py`):

```bash
# Check cacheops configuration
python manage.py shell
>>> from django.conf import settings
>>> settings.CACHEOPS_REDIS
# Expected: redis://redis:6379/2

>>> settings.CACHEOPS
# Expected: Dictionary with model configurations

>>> settings.CACHEOPS_DEGRADE_ON_FAILURE
# Expected: True (graceful fallback)

# Test cacheops integration
>>> from cacheops import invalidate_model
>>> from django.contrib.auth.models import User
>>> invalidate_model(User)  # Should not raise errors
```

**Checklist**:
- [ ] `CACHEOPS_REDIS` points to database 2
- [ ] `CACHEOPS` dictionary has model configurations
- [ ] `CACHEOPS_DEGRADE_ON_FAILURE` is True
- [ ] Cacheops can be imported without errors
- [ ] Model invalidation works

---

## Section 5: System Health Checks

### 5.1 Pre-Migration System State

**Capture Current State**:

```bash
# 1. Check current cache backend (before migration)
python manage.py shell -c "from django.conf import settings; print(settings.CACHES['default']['BACKEND'])"

# 2. Capture current Redis key count
redis-cli -u $REDIS_URL DBSIZE

# 3. Check application logs for cache-related errors
tail -100 /path/to/application.log | grep -i cache

# 4. Test application functionality
# - Log in as a user
# - Perform key operations (create invoice, check calendar, etc.)
# - Verify no errors

# 5. Check Redis memory before migration
redis-cli -u $REDIS_URL INFO memory | grep used_memory_human
```

**Checklist**:
- [ ] Current cache backend documented
- [ ] Current Redis key count recorded: __________
- [ ] No cache-related errors in logs
- [ ] Application functions correctly
- [ ] Redis memory usage recorded: __________


### 5.2 Dependency Verification

**Required Python Packages**:

```bash
# Verify packages are installed (use uv)
uv pip list | grep -E "django-redis|django-cacheops|redis"

# Expected packages:
# django-redis     5.x.x
# django-cacheops  7.x.x
# redis            5.x.x
```

**Verification Commands**:

```bash
# Test imports
python manage.py shell
>>> import django_redis
>>> import cacheops
>>> import redis
>>> print(f"django-redis: {django_redis.__version__}")
>>> print(f"redis: {redis.__version__}")
```

**Checklist**:
- [ ] `django-redis` 5.x is installed
- [ ] `django-cacheops` 7.x is installed
- [ ] `redis` 5.x is installed
- [ ] All packages import successfully
- [ ] No version conflicts

### 5.3 Test Suite Execution

**Run Validation Tests**:

```bash
# Run existing cache validation tests
python manage.py test backend.cache.tests.test_existing_cache_validation -v 2

# Expected: 27 tests passed, 0 failed

# Run all cache tests
python manage.py test backend.cache.tests -v 2

# Check for any failures or errors
```

**Checklist**:
- [ ] All 27 validation tests pass
- [ ] No test failures in cache test suite
- [ ] No deprecation warnings
- [ ] Test execution time is reasonable (< 5 seconds)

---

## Section 6: Backup Procedures

### 6.1 Database Backup

**Before Migration**:

```bash
# Create database backup
pg_dump -h $DB_HOST -U $DB_USER -d $DB_NAME -F c -f pre_migration_backup_$(date +%Y%m%d_%H%M%S).dump

# Verify backup
ls -lh pre_migration_backup_*.dump

# Test backup can be read
pg_restore --list pre_migration_backup_*.dump | head -20
```

**Checklist**:
- [ ] Database backup created
- [ ] Backup file size is reasonable
- [ ] Backup can be listed/read
- [ ] Backup location documented: __________

### 6.2 Redis Backup (Optional)

**Note**: Current cache data will NOT be preserved by design. This backup is for reference only.

```bash
# Create Redis snapshot (if persistence is enabled)
redis-cli -u $REDIS_URL BGSAVE

# Check snapshot status
redis-cli -u $REDIS_URL LASTSAVE

# Copy RDB file (if needed)
# Location depends on Redis configuration
# Default: /var/lib/redis/dump.rdb
```

**Checklist**:
- [ ] Redis snapshot created (if desired)
- [ ] Snapshot location documented: __________
- [ ] Understand that cache data will be cleared

### 6.3 Configuration Backup

**Backup Configuration Files**:

```bash
# Create backup directory
mkdir -p backups/pre_migration_$(date +%Y%m%d)

# Backup Django settings
cp backend/business_suite/settings/base.py backups/pre_migration_$(date +%Y%m%d)/
cp backend/business_suite/settings/cache_backends.py backups/pre_migration_$(date +%Y%m%d)/

# Backup environment variables
env | grep -E "REDIS|CACHE" > backups/pre_migration_$(date +%Y%m%d)/env_vars.txt

# Backup Redis configuration
redis-cli -u $REDIS_URL CONFIG GET '*' > backups/pre_migration_$(date +%Y%m%d)/redis_config.txt
```

**Checklist**:
- [ ] Django settings backed up
- [ ] Environment variables documented
- [ ] Redis configuration saved
- [ ] Backup location: __________

---

## Section 7: Rollback Plan Preparation

### 7.1 Rollback Strategy

**If Migration Fails**:

1. **Stop Application**:
   ```bash
   # Stop Django application
   systemctl stop django-app  # or your process manager
   ```

2. **Restore Database** (if needed):
   ```bash
   # Drop current database
   dropdb $DB_NAME
   
   # Restore from backup
   pg_restore -h $DB_HOST -U $DB_USER -d $DB_NAME -c pre_migration_backup_*.dump
   ```

3. **Revert Configuration**:
   ```bash
   # Restore old settings files
   cp backups/pre_migration_*/base.py backend/business_suite/settings/
   cp backups/pre_migration_*/cache_backends.py backend/business_suite/settings/
   ```

4. **Clear Redis** (optional):
   ```bash
   # Clear Redis databases
   redis-cli -u $REDIS_URL FLUSHDB
   ```

5. **Restart Application**:
   ```bash
   systemctl start django-app
   ```

**Checklist**:
- [ ] Rollback procedure documented
- [ ] Team knows how to execute rollback
- [ ] Backup files are accessible
- [ ] Rollback can be executed within 15 minutes

### 7.2 Rollback Testing (Optional)

**Test Rollback Procedure** (in staging environment):

```bash
# 1. Create test backup
# 2. Perform migration
# 3. Execute rollback procedure
# 4. Verify application works
# 5. Document any issues
```

**Checklist**:
- [ ] Rollback tested in staging (if available)
- [ ] Rollback time measured: __________ minutes
- [ ] Any issues documented

---

## Section 8: Migration Execution Checklist

### 8.1 Pre-Migration Final Checks

**Before Starting Migration**:

- [ ] All sections above completed
- [ ] Redis is accessible and healthy
- [ ] Database migration applied
- [ ] Backups created and verified
- [ ] Rollback plan ready
- [ ] Team notified of migration
- [ ] Maintenance window scheduled (if needed)


### 8.2 Migration Steps

**Step-by-Step Execution**:

1. **Announce Maintenance** (if needed):
   - [ ] Users notified
   - [ ] Maintenance page enabled (if applicable)

2. **Stop Application** (if zero-downtime not possible):
   ```bash
   systemctl stop django-app
   ```

3. **Clear Old Cache Data**:
   ```bash
   # Clear Redis database 1 (Django cache)
   redis-cli -u $REDIS_URL FLUSHDB
   
   # Clear Redis database 2 (Cacheops)
   redis-cli -u $REDIS_URL -n 2 FLUSHDB
   ```

4. **Verify Configuration**:
   ```bash
   # Ensure settings are correct
   python manage.py check --deploy
   ```

5. **Run Migrations** (if not already done):
   ```bash
   python manage.py migrate
   ```

6. **Start Application**:
   ```bash
   systemctl start django-app
   ```

7. **Monitor Startup**:
   ```bash
   # Watch logs
   tail -f /path/to/application.log
   
   # Check Redis connections
   redis-cli -u $REDIS_URL CLIENT LIST
   ```

**Checklist**:
- [ ] Application stopped (if needed)
- [ ] Cache data cleared
- [ ] Configuration verified
- [ ] Migrations applied
- [ ] Application started
- [ ] No errors in logs

### 8.3 Post-Migration Verification

**Immediate Checks** (within 5 minutes):

```bash
# 1. Check application is running
curl http://localhost:8000/health  # or your health endpoint

# 2. Verify Redis connections
redis-cli -u $REDIS_URL CLIENT LIST | grep django

# 3. Check cache operations
python manage.py shell
>>> from django.core.cache import cache
>>> cache.set('migration_test', 'success', 60)
>>> cache.get('migration_test')
# Expected: 'success'

# 4. Test user login and basic operations
# - Log in as test user
# - Perform key operations
# - Check for errors

# 5. Monitor Redis key creation
redis-cli -u $REDIS_URL MONITOR
# Should see cache keys being created with correct format
```

**Checklist**:
- [ ] Application responds to requests
- [ ] Redis connections established
- [ ] Cache operations work
- [ ] User login successful
- [ ] No errors in application logs
- [ ] Cache keys have correct format

### 8.4 Extended Monitoring (first 24 hours)

**Monitoring Points**:

1. **Cache Hit Rate**:
   ```bash
   # Monitor cache effectiveness
   redis-cli -u $REDIS_URL INFO stats | grep keyspace
   ```

2. **Application Performance**:
   - Monitor response times
   - Check for slow queries
   - Verify cache is being used

3. **Error Rates**:
   ```bash
   # Check for cache-related errors
   tail -f /path/to/application.log | grep -i "cache\|redis"
   ```

4. **Redis Memory Usage**:
   ```bash
   # Monitor memory growth
   watch -n 60 'redis-cli -u $REDIS_URL INFO memory | grep used_memory_human'
   ```

**Checklist**:
- [ ] Cache hit rate is increasing
- [ ] No performance degradation
- [ ] Error rate is normal
- [ ] Redis memory usage is stable

---

## Section 9: Known Issues and Considerations

### 9.1 Expected Behavior

**Cache Data Loss**:
- ✅ **EXPECTED**: All existing cache data will be cleared during migration
- ✅ **EXPECTED**: Cache will rebuild automatically as users access the system
- ✅ **EXPECTED**: First requests after migration may be slower (cache miss)
- ✅ **EXPECTED**: Performance will improve as cache warms up

**User Experience**:
- ✅ No user action required
- ✅ All users have caching enabled by default
- ✅ Users can disable caching via UI if needed
- ✅ No data loss (only cache cleared, database unchanged)

### 9.2 Potential Issues and Solutions

**Issue 1: Redis Connection Failures**

**Symptoms**: Application logs show Redis connection errors

**Solution**:
```bash
# Check Redis is running
redis-cli -u $REDIS_URL ping

# Check network connectivity
telnet redis-host 6379

# Verify REDIS_URL is correct
echo $REDIS_URL

# Check Redis logs
tail -f /var/log/redis/redis-server.log
```

**Fallback**: Application will automatically fall back to database queries

---

**Issue 2: Slow Performance After Migration**

**Symptoms**: Application is slower than before migration

**Cause**: Cache is empty and needs to warm up

**Solution**:
- Wait 15-30 minutes for cache to populate
- Monitor cache hit rate: `redis-cli -u $REDIS_URL INFO stats`
- Run benchmark: `python manage.py benchmark_cache`

**Expected**: Performance should match or exceed pre-migration after cache warms up

---

**Issue 3: Cache Keys Not Being Created**

**Symptoms**: Redis MONITOR shows no cache keys

**Solution**:
```bash
# Check middleware is active
python manage.py shell
>>> from django.conf import settings
>>> 'cache.middleware.CacheMiddleware' in settings.MIDDLEWARE
# Expected: True

# Check user has caching enabled
>>> from core.models import UserProfile
>>> profile = UserProfile.objects.get(user__username='testuser')
>>> profile.cache_enabled
# Expected: True

# Check cacheops is configured
>>> from django.conf import settings
>>> settings.CACHEOPS
# Expected: Dictionary with model configs
```

---

**Issue 4: Memory Usage Higher Than Expected**

**Symptoms**: Redis memory usage grows rapidly

**Solution**:
```bash
# Check maxmemory policy
redis-cli -u $REDIS_URL CONFIG GET maxmemory-policy
# Recommended: allkeys-lru

# Set maxmemory policy if needed
redis-cli -u $REDIS_URL CONFIG SET maxmemory-policy allkeys-lru

# Check TTL on keys
redis-cli -u $REDIS_URL TTL "cache:1:v1:cacheops:somekey"
# Should show remaining TTL in seconds

# Monitor key expiration
redis-cli -u $REDIS_URL INFO stats | grep expired_keys
```

---

## Section 10: Success Criteria

### 10.1 Migration Success Indicators

**Technical Metrics**:
- [ ] Application starts without errors
- [ ] Redis connections established
- [ ] Cache operations work correctly
- [ ] All validation tests pass
- [ ] No increase in error rate
- [ ] Response times are acceptable

**Functional Metrics**:
- [ ] Users can log in
- [ ] Invoice generation works
- [ ] Calendar reminders work
- [ ] Workflow notifications work
- [ ] WhatsApp integration works
- [ ] Cron jobs execute correctly

**Performance Metrics**:
- [ ] Cache hit rate > 0% (and increasing)
- [ ] Average response time ≤ pre-migration baseline
- [ ] Redis memory usage is stable
- [ ] No database query spikes

### 10.2 Sign-Off

**Migration Completed By**: _____________  
**Date**: _____________  
**Time**: _____________

**Verification**:
- [ ] All checklist items completed
- [ ] No critical issues
- [ ] System is stable
- [ ] Team notified of completion

**Approvals**:
- [ ] Technical Lead: _____________ Date: _______
- [ ] Operations: _____________ Date: _______

---

## Section 11: Additional Resources

### 11.1 Documentation References

- **Architecture**: `backend/cache/ARCHITECTURE.md`
- **API Documentation**: `backend/cache/API_DOCUMENTATION.md`
- **Validation Results**: `backend/cache/tests/VALIDATION_RESULTS.md`
- **Benchmark Results**: `backend/cache/tests/BENCHMARK_RESULTS.md`
- **Optimization Notes**: `backend/cache/OPTIMIZATION_NOTES.md`
- **Requirements**: `.kiro/specs/hybrid-cache-system/requirements.md`
- **Design**: `.kiro/specs/hybrid-cache-system/design.md`

### 11.2 Support Contacts

**Technical Issues**:
- Development Team: _____________
- Operations Team: _____________
- On-Call Engineer: _____________

**Escalation**:
- Technical Lead: _____________
- System Administrator: _____________

### 11.3 Useful Commands

**Quick Health Check**:
```bash
# One-liner to check system health
redis-cli -u $REDIS_URL ping && \
python manage.py check && \
curl -s http://localhost:8000/health && \
echo "✅ System healthy"
```

**Cache Statistics**:
```bash
# Get cache statistics
redis-cli -u $REDIS_URL INFO stats | grep -E "keyspace|hits|misses"
```

**Clear Cache** (if needed):
```bash
# Clear all cache data
redis-cli -u $REDIS_URL FLUSHDB
```

---

## Appendix A: Quick Reference

### Environment Variables
```bash
REDIS_URL=redis://redis:6379/1
CACHE_KEY_PREFIX=revisbali
```

### Redis Databases
- DB 0: PgQueuer task queue
- DB 1: Django cache
- DB 2: Cacheops
- DB 15: Tests

### Key Patterns
- Django cache: `revisbali:cache:*`
- Cacheops: `cache:{user_id}:v{version}:cacheops:{hash}`
- User version: `cache_user_version:{user_id}`

### Important Files
- Settings: `backend/business_suite/settings/base.py`
- Cache backends: `backend/business_suite/settings/cache_backends.py`
- Middleware: `backend/cache/middleware.py`
- Namespace: `backend/cache/namespace.py`

---

**END OF CHECKLIST**

*This checklist should be completed before migrating to production. Keep this document for reference during and after migration.*
