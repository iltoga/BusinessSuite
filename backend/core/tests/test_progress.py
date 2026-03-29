"""Tests for task progress helpers and progress state updates."""

from core.tasks.progress import persist_progress
from django.test import SimpleTestCase


class _DummyProgressRecord:
    def __init__(self, *, progress=0, status="queued"):
        self.progress = progress
        self.status = status
        self.updated_at = None
        self.saved_update_fields: list[list[str]] = []

    def save(self, *, update_fields):
        self.saved_update_fields.append(list(update_fields))


class PersistProgressTests(SimpleTestCase):
    def test_skips_small_progress_delta_without_force(self):
        record = _DummyProgressRecord(progress=40)

        saved = persist_progress(record, progress=43, min_delta=5)

        self.assertFalse(saved)
        self.assertEqual(record.saved_update_fields, [])
        self.assertEqual(record.progress, 40)

    def test_persists_meaningful_progress_delta(self):
        record = _DummyProgressRecord(progress=40)

        saved = persist_progress(record, progress=45, min_delta=5)

        self.assertTrue(saved)
        self.assertEqual(record.progress, 45)
        self.assertEqual(record.saved_update_fields, [["progress", "updated_at"]])

    def test_status_change_forces_persist_even_without_large_delta(self):
        record = _DummyProgressRecord(progress=40, status="queued")

        saved = persist_progress(record, progress=42, status="processing", min_delta=5)

        self.assertTrue(saved)
        self.assertEqual(record.status, "processing")
        self.assertEqual(record.progress, 42)
        self.assertEqual(record.saved_update_fields, [["status", "progress", "updated_at"]])
