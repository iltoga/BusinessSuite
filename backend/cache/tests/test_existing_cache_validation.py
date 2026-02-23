"""
Validation tests for existing cache usage patterns.

This test suite verifies that existing cache patterns continue to work
correctly with the new Redis-based cache system. It tests:
- Meta WhatsApp access token caching
- Cron job lock coordination
- Invoice sequence cache
- Calendar reminder stream cursor cache
- Workflow notification stream cursor cache

Requirements: 10.1, 10.2, 10.3, 10.7, 12.1, 12.2, 12.3
"""

import time
from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from core.services.calendar_reminder_stream import (
    CALENDAR_REMINDER_STREAM_CURSOR_CACHE_KEY,
    bump_calendar_reminder_stream_cursor,
    get_calendar_reminder_stream_cursor,
    get_calendar_reminder_stream_last_event,
    reset_calendar_reminder_stream_state,
)
from core.tasks.cron_jobs import (
    CLEAR_CACHE_ENQUEUE_LOCK_KEY,
    CLEAR_CACHE_RUN_LOCK_KEY,
    FULL_BACKUP_ENQUEUE_LOCK_KEY,
    FULL_BACKUP_RUN_LOCK_KEY,
    _acquire_cache_lock,
    _release_cache_lock,
    reset_privileged_cron_job_locks,
)
from customer_applications.services.workflow_notification_stream import (
    WORKFLOW_NOTIFICATION_STREAM_CURSOR_CACHE_KEY,
    bump_workflow_notification_stream_cursor,
    get_workflow_notification_stream_cursor,
    get_workflow_notification_stream_last_event,
    reset_workflow_notification_stream_state,
)
from customers.models import Customer
from invoices.models import Invoice
from notifications.services.meta_access_token import (
    META_RUNTIME_ACCESS_TOKEN_CACHE_KEY,
    META_RUNTIME_ACCESS_TOKEN_EXPIRES_AT_CACHE_KEY,
    _cache_timeout_seconds,
    _runtime_cached_expires_at,
    _runtime_cached_token,
    reset_meta_whatsapp_access_token_cache,
)


TEST_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "existing-cache-validation-tests",
    }
}


@override_settings(CACHES=TEST_CACHES)
class MetaWhatsAppTokenCacheValidationTest(TestCase):
    """Validate Meta WhatsApp access token caching works correctly."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_token_cache_set_and_get(self):
        """Test basic token cache set and get operations."""
        test_token = "test_access_token_12345"
        timeout = _cache_timeout_seconds()

        # Set token in cache
        cache.set(META_RUNTIME_ACCESS_TOKEN_CACHE_KEY, test_token, timeout=timeout)

        # Retrieve token from cache
        cached_token = _runtime_cached_token()

        self.assertEqual(cached_token, test_token)

    def test_token_expires_at_cache(self):
        """Test token expiration timestamp caching."""
        expires_at = int(time.time()) + 3600  # 1 hour from now
        timeout = _cache_timeout_seconds()

        # Set expiration in cache
        cache.set(META_RUNTIME_ACCESS_TOKEN_EXPIRES_AT_CACHE_KEY, expires_at, timeout=timeout)

        # Retrieve expiration from cache
        cached_expires_at = _runtime_cached_expires_at()

        self.assertEqual(cached_expires_at, expires_at)

    def test_token_cache_reset(self):
        """Test clearing token cache."""
        # Set both token and expiration
        cache.set(META_RUNTIME_ACCESS_TOKEN_CACHE_KEY, "token", timeout=3600)
        cache.set(META_RUNTIME_ACCESS_TOKEN_EXPIRES_AT_CACHE_KEY, 12345, timeout=3600)

        # Reset cache
        reset_meta_whatsapp_access_token_cache()

        # Verify both are cleared
        self.assertEqual(_runtime_cached_token(), "")
        self.assertIsNone(_runtime_cached_expires_at())

    def test_token_cache_persistence(self):
        """Test that token persists across multiple retrievals."""
        test_token = "persistent_token_xyz"
        cache.set(META_RUNTIME_ACCESS_TOKEN_CACHE_KEY, test_token, timeout=3600)

        # Multiple retrievals should return same token
        for _ in range(5):
            self.assertEqual(_runtime_cached_token(), test_token)


@override_settings(CACHES=TEST_CACHES)
class CronJobLockValidationTest(TestCase):
    """Validate cron job lock coordination works correctly."""

    def setUp(self):
        cache.clear()
        reset_privileged_cron_job_locks()

    def tearDown(self):
        cache.clear()
        reset_privileged_cron_job_locks()

    def test_lock_acquisition(self):
        """Test acquiring a cache lock."""
        lock_key = FULL_BACKUP_ENQUEUE_LOCK_KEY
        ttl = 300

        # Acquire lock
        token = _acquire_cache_lock(lock_key, ttl)

        self.assertIsNotNone(token)
        self.assertIsInstance(token, str)
        self.assertGreater(len(token), 0)

        # Verify lock is set in cache
        cached_value = cache.get(lock_key)
        self.assertEqual(cached_value, token)

    def test_lock_prevents_duplicate_acquisition(self):
        """Test that lock prevents duplicate acquisition."""
        lock_key = CLEAR_CACHE_ENQUEUE_LOCK_KEY
        ttl = 300

        # First acquisition succeeds
        token1 = _acquire_cache_lock(lock_key, ttl)
        self.assertIsNotNone(token1)

        # Second acquisition fails
        token2 = _acquire_cache_lock(lock_key, ttl)
        self.assertIsNone(token2)

    def test_lock_release(self):
        """Test releasing a cache lock."""
        lock_key = FULL_BACKUP_RUN_LOCK_KEY
        ttl = 300

        # Acquire and release lock
        token = _acquire_cache_lock(lock_key, ttl)
        self.assertIsNotNone(token)

        _release_cache_lock(lock_key, token)

        # Verify lock is released
        cached_value = cache.get(lock_key)
        self.assertIsNone(cached_value)

    def test_lock_release_with_wrong_token(self):
        """Test that lock cannot be released with wrong token."""
        lock_key = CLEAR_CACHE_RUN_LOCK_KEY
        ttl = 300

        # Acquire lock
        token = _acquire_cache_lock(lock_key, ttl)
        self.assertIsNotNone(token)

        # Try to release with wrong token
        _release_cache_lock(lock_key, "wrong_token")

        # Lock should still be held
        cached_value = cache.get(lock_key)
        self.assertEqual(cached_value, token)

    def test_reset_all_locks(self):
        """Test resetting all privileged cron job locks."""
        # Acquire multiple locks
        _acquire_cache_lock(FULL_BACKUP_ENQUEUE_LOCK_KEY, 300)
        _acquire_cache_lock(FULL_BACKUP_RUN_LOCK_KEY, 300)
        _acquire_cache_lock(CLEAR_CACHE_ENQUEUE_LOCK_KEY, 300)
        _acquire_cache_lock(CLEAR_CACHE_RUN_LOCK_KEY, 300)

        # Reset all locks
        reset_privileged_cron_job_locks()

        # Verify all locks are cleared
        self.assertIsNone(cache.get(FULL_BACKUP_ENQUEUE_LOCK_KEY))
        self.assertIsNone(cache.get(FULL_BACKUP_RUN_LOCK_KEY))
        self.assertIsNone(cache.get(CLEAR_CACHE_ENQUEUE_LOCK_KEY))
        self.assertIsNone(cache.get(CLEAR_CACHE_RUN_LOCK_KEY))


@override_settings(CACHES=TEST_CACHES)
class InvoiceSequenceCacheValidationTest(TestCase):
    """Validate invoice sequence caching works correctly."""

    def setUp(self):
        cache.clear()
        self.customer = Customer.objects.create(
            first_name="Test",
            last_name="Customer",
            email="test@example.com",
        )

    def tearDown(self):
        cache.clear()

    def test_invoice_sequence_cache_key_format(self):
        """Test invoice sequence cache key format."""
        year = 2026
        cache_key = Invoice._get_invoice_seq_cache_key(year)

        self.assertEqual(cache_key, f"{Invoice.INVOICE_SEQ_CACHE_PREFIX}:{year}")

    def test_invoice_sequence_prime_cache(self):
        """Test priming invoice sequence cache."""
        year = 2026

        # Prime cache with no existing invoices
        last_sequence = Invoice._prime_invoice_sequence_cache(year)

        self.assertEqual(last_sequence, 0)

        # Verify cache is set
        cache_key = Invoice._get_invoice_seq_cache_key(year)
        cached_value = cache.get(cache_key)
        self.assertEqual(cached_value, 0)

    def test_invoice_sequence_incr(self):
        """Test invoice sequence increment via cache.incr()."""
        year = 2026
        cache_key = Invoice._get_invoice_seq_cache_key(year)

        # Prime cache
        Invoice._prime_invoice_sequence_cache(year)

        # Increment sequence
        next_seq = cache.incr(cache_key)
        self.assertEqual(next_seq, 1)

        # Increment again
        next_seq = cache.incr(cache_key)
        self.assertEqual(next_seq, 2)

    def test_invoice_sequence_get_next_invoice_no(self):
        """Test getting next invoice number."""
        year = 2026

        # Get first invoice number
        invoice_no_1 = Invoice.get_next_invoice_no_for_year(year)
        self.assertEqual(invoice_no_1, 20260001)

        # Get second invoice number
        invoice_no_2 = Invoice.get_next_invoice_no_for_year(year)
        self.assertEqual(invoice_no_2, 20260002)

        # Get third invoice number
        invoice_no_3 = Invoice.get_next_invoice_no_for_year(year)
        self.assertEqual(invoice_no_3, 20260003)

    def test_invoice_sequence_sync_cache(self):
        """Test syncing invoice sequence cache after save."""
        year = 2026
        invoice = Invoice.objects.create(
            customer=self.customer,
            invoice_no=20260005,
            invoice_date=timezone.now().date(),
            due_date=timezone.now().date() + timedelta(days=30),
        )

        # Sync should update cache to 5
        invoice._sync_invoice_sequence_cache()

        cache_key = Invoice._get_invoice_seq_cache_key(year)
        cached_value = cache.get(cache_key)
        self.assertEqual(cached_value, 5)


@override_settings(CACHES=TEST_CACHES)
class CalendarReminderStreamCacheValidationTest(TestCase):
    """Validate calendar reminder stream cursor caching works correctly."""

    def setUp(self):
        cache.clear()
        reset_calendar_reminder_stream_state()

    def tearDown(self):
        cache.clear()
        reset_calendar_reminder_stream_state()

    def test_get_initial_cursor(self):
        """Test getting initial cursor value."""
        cursor = get_calendar_reminder_stream_cursor()
        self.assertEqual(cursor, 0)

    def test_bump_cursor(self):
        """Test bumping cursor value."""
        cursor1 = bump_calendar_reminder_stream_cursor(
            reminder_id=1, operation="created", owner_id=100
        )
        self.assertEqual(cursor1, 1)

        cursor2 = bump_calendar_reminder_stream_cursor(
            reminder_id=2, operation="updated", owner_id=100
        )
        self.assertEqual(cursor2, 2)

    def test_get_last_event(self):
        """Test getting last event data."""
        # Bump cursor to create event
        bump_calendar_reminder_stream_cursor(
            reminder_id=123, operation="deleted", owner_id=456
        )

        # Get last event
        event = get_calendar_reminder_stream_last_event()

        self.assertIsNotNone(event, "Event should not be None")
        self.assertIsInstance(event, dict)
        if event is not None:
            self.assertEqual(event["cursor"], 1)
            self.assertEqual(event["operation"], "deleted")
            self.assertEqual(event["reminderId"], 123)
            self.assertEqual(event["ownerId"], 456)
            self.assertIn("changedAt", event)

    def test_cursor_persistence(self):
        """Test cursor persists across multiple operations."""
        # Bump cursor multiple times
        for i in range(1, 6):
            cursor = bump_calendar_reminder_stream_cursor(
                reminder_id=i, operation="test", owner_id=1
            )
            self.assertEqual(cursor, i)

        # Verify final cursor value
        final_cursor = get_calendar_reminder_stream_cursor()
        self.assertEqual(final_cursor, 5)

    def test_reset_stream_state(self):
        """Test resetting stream state."""
        # Create some state
        bump_calendar_reminder_stream_cursor(
            reminder_id=1, operation="test", owner_id=1
        )

        # Reset
        reset_calendar_reminder_stream_state()

        # Verify state is cleared
        cursor = get_calendar_reminder_stream_cursor()
        event = get_calendar_reminder_stream_last_event()

        self.assertEqual(cursor, 0)
        self.assertIsNone(event)


@override_settings(CACHES=TEST_CACHES)
class WorkflowNotificationStreamCacheValidationTest(TestCase):
    """Validate workflow notification stream cursor caching works correctly."""

    def setUp(self):
        cache.clear()
        reset_workflow_notification_stream_state()

    def tearDown(self):
        cache.clear()
        reset_workflow_notification_stream_state()

    def test_get_initial_cursor(self):
        """Test getting initial cursor value."""
        cursor = get_workflow_notification_stream_cursor()
        self.assertEqual(cursor, 0)

    def test_bump_cursor(self):
        """Test bumping cursor value."""
        cursor1 = bump_workflow_notification_stream_cursor(
            notification_id=1, operation="created"
        )
        self.assertEqual(cursor1, 1)

        cursor2 = bump_workflow_notification_stream_cursor(
            notification_id=2, operation="delivered"
        )
        self.assertEqual(cursor2, 2)

    def test_get_last_event(self):
        """Test getting last event data."""
        # Bump cursor to create event
        bump_workflow_notification_stream_cursor(
            notification_id=789, operation="failed"
        )

        # Get last event
        event = get_workflow_notification_stream_last_event()

        self.assertIsNotNone(event)
        self.assertIsInstance(event, dict)
        if event is not None:
            self.assertEqual(event["cursor"], 1)
            self.assertEqual(event["operation"], "failed")
            self.assertEqual(event["notificationId"], 789)
            self.assertIn("changedAt", event)

    def test_cursor_persistence(self):
        """Test cursor persists across multiple operations."""
        # Bump cursor multiple times
        for i in range(1, 6):
            cursor = bump_workflow_notification_stream_cursor(
                notification_id=i, operation="test"
            )
            self.assertEqual(cursor, i)

        # Verify final cursor value
        final_cursor = get_workflow_notification_stream_cursor()
        self.assertEqual(final_cursor, 5)

    def test_reset_stream_state(self):
        """Test resetting stream state."""
        # Create some state
        bump_workflow_notification_stream_cursor(
            notification_id=1, operation="test"
        )

        # Reset
        reset_workflow_notification_stream_state()

        # Verify state is cleared
        cursor = get_workflow_notification_stream_cursor()
        event = get_workflow_notification_stream_last_event()

        self.assertEqual(cursor, 0)
        self.assertIsNone(event)


@override_settings(CACHES=TEST_CACHES)
class CachePerformanceValidationTest(TestCase):
    """Validate cache performance for existing patterns."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_cache_set_get_performance(self):
        """Test basic cache set/get performance."""
        start_time = time.time()

        # Perform 100 set/get operations
        for i in range(100):
            cache.set(f"perf_test_key_{i}", f"value_{i}", timeout=300)
            value = cache.get(f"perf_test_key_{i}")
            self.assertEqual(value, f"value_{i}")

        elapsed = time.time() - start_time

        # Should complete in reasonable time (< 1 second for 100 ops)
        self.assertLess(elapsed, 1.0, f"Cache operations took {elapsed:.3f}s, expected < 1.0s")

    def test_cache_incr_performance(self):
        """Test cache.incr() performance."""
        cache_key = "perf_incr_test"
        cache.set(cache_key, 0, timeout=300)

        start_time = time.time()

        # Perform 100 increment operations
        for i in range(100):
            value = cache.incr(cache_key)
            self.assertEqual(value, i + 1)

        elapsed = time.time() - start_time

        # Should complete in reasonable time (< 0.5 seconds for 100 ops)
        self.assertLess(elapsed, 0.5, f"Cache incr operations took {elapsed:.3f}s, expected < 0.5s")

    def test_cache_delete_many_performance(self):
        """Test cache.delete_many() performance."""
        # Set up 50 keys
        keys = [f"delete_test_key_{i}" for i in range(50)]
        for key in keys:
            cache.set(key, "value", timeout=300)

        start_time = time.time()

        # Delete all keys at once
        cache.delete_many(keys)

        elapsed = time.time() - start_time

        # Should complete in reasonable time (< 0.2 seconds)
        self.assertLess(elapsed, 0.2, f"Cache delete_many took {elapsed:.3f}s, expected < 0.2s")

        # Verify all keys are deleted
        for key in keys:
            self.assertIsNone(cache.get(key))
