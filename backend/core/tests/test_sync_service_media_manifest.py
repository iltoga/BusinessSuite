from __future__ import annotations

import os
import tempfile
from pathlib import Path

from django.test import TestCase, override_settings

from core.models.local_resilience import MediaManifestEntry
from core.services.sync_service import refresh_media_manifest


class RefreshMediaManifestTests(TestCase):
    @override_settings(LOCAL_MEDIA_ENCRYPTION_ENABLED=False)
    def test_refresh_skips_unchanged_media_entries(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                image_path = Path(media_root) / "manifest" / "sample.txt"
                image_path.parent.mkdir(parents=True, exist_ok=True)
                image_path.write_text("v1", encoding="utf-8")

                fixed_timestamp = 1_700_000_000
                os.utime(image_path, (fixed_timestamp, fixed_timestamp))

                refreshed_first = refresh_media_manifest(source_node="node-a")
                self.assertEqual(refreshed_first, 1)

                entry = MediaManifestEntry.objects.get(path="manifest/sample.txt")
                first_updated_at = entry.updated_at

                refreshed_second = refresh_media_manifest(source_node="node-a")
                self.assertEqual(refreshed_second, 0)

                entry.refresh_from_db()
                self.assertEqual(entry.updated_at, first_updated_at)

                image_path.write_text("v2", encoding="utf-8")
                os.utime(image_path, (fixed_timestamp + 120, fixed_timestamp + 120))

                refreshed_third = refresh_media_manifest(source_node="node-a")
                self.assertEqual(refreshed_third, 1)

                entry.refresh_from_db()
                self.assertGreater(entry.updated_at, first_updated_at)
