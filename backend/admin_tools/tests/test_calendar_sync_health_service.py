"""
FILE_ROLE: Test coverage for the admin tools app.

KEY_COMPONENTS:
- CalendarSyncHealthServiceTests: Module symbol.

INTERACTIONS:
- Depends on: Django settings/bootstrap and adjacent app services or middleware in this module.

AI_GUIDELINES:
- Keep the file focused on its narrow responsibility and avoid mixing in unrelated business logic.
- Preserve existing runtime contracts for app routing, model behavior, and service boundaries.
"""

from datetime import timedelta

from admin_tools import services
from core.models.calendar_event import CalendarEvent
from django.test import TestCase
from django.utils import timezone


class CalendarSyncHealthServiceTests(TestCase):
    def test_health_is_ok_when_no_stuck_or_failed_events(self):
        CalendarEvent.objects.create(
            id="evt-health-ok-1",
            source=CalendarEvent.SOURCE_APPLICATION,
            title="Pending Recent",
            sync_status=CalendarEvent.SYNC_STATUS_PENDING,
        )

        payload = services.get_calendar_sync_health_status(stuck_after_minutes=10, sample_limit=5)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["severity"], "ok")
        self.assertEqual(payload["counts"]["stuckPending"], 0)
        self.assertEqual(payload["stuckPendingSamples"], [])

    def test_health_flags_stuck_pending_events(self):
        old_event = CalendarEvent.objects.create(
            id="evt-health-stuck-1",
            source=CalendarEvent.SOURCE_APPLICATION,
            title="Pending Old",
            sync_status=CalendarEvent.SYNC_STATUS_PENDING,
        )
        recent_event = CalendarEvent.objects.create(
            id="evt-health-stuck-2",
            source=CalendarEvent.SOURCE_APPLICATION,
            title="Pending Recent",
            sync_status=CalendarEvent.SYNC_STATUS_PENDING,
        )

        old_updated_at = timezone.now() - timedelta(minutes=30)
        recent_updated_at = timezone.now() - timedelta(minutes=1)
        CalendarEvent.objects.filter(pk=old_event.pk).update(updated_at=old_updated_at)
        CalendarEvent.objects.filter(pk=recent_event.pk).update(updated_at=recent_updated_at)

        payload = services.get_calendar_sync_health_status(stuck_after_minutes=5, sample_limit=10)

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["severity"], "critical")
        self.assertEqual(payload["counts"]["pending"], 2)
        self.assertEqual(payload["counts"]["stuckPending"], 1)
        self.assertEqual(len(payload["stuckPendingSamples"]), 1)
        self.assertEqual(payload["stuckPendingSamples"][0]["id"], old_event.pk)
