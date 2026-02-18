from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient


class BackupsApiTimezoneTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser(
            username="backup-admin",
            email="backup-admin@example.com",
            password="password",
        )
        self.client.force_authenticate(user=self.user)
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

    def _touch(self, filename: str) -> None:
        path = Path(self.temp_dir.name) / filename
        path.write_text("{}", encoding="utf-8")

    @override_settings(TIME_ZONE="Asia/Singapore")
    def test_list_parses_backup_and_uploaded_timestamps_with_correct_timezones(self):
        self._touch("backup-20260218-052729.json")
        self._touch("uploaded-20260218-122742-existing-backup.json")

        with patch("api.views_admin.services.BACKUPS_DIR", self.temp_dir.name):
            response = self.client.get("/api/backups/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        backups = payload["backups"]
        self.assertEqual(len(backups), 2)

        by_name = {item["filename"]: item for item in backups}
        self.assertEqual(by_name["backup-20260218-052729.json"]["createdAt"], "2026-02-18T05:27:29+00:00")
        self.assertEqual(
            by_name["uploaded-20260218-122742-existing-backup.json"]["createdAt"],
            "2026-02-18T12:27:42+08:00",
        )

    @override_settings(TIME_ZONE="Asia/Singapore")
    def test_list_sorts_by_real_datetime_not_iso_string(self):
        # 13:27 local (UTC+8) is newer than 12:27 local.
        self._touch("backup-20260218-052729.json")
        self._touch("uploaded-20260218-122742-existing-backup.json")

        with patch("api.views_admin.services.BACKUPS_DIR", self.temp_dir.name):
            response = self.client.get("/api/backups/")

        self.assertEqual(response.status_code, 200)
        backups = response.json()["backups"]
        self.assertEqual(backups[0]["filename"], "backup-20260218-052729.json")
        self.assertEqual(backups[1]["filename"], "uploaded-20260218-122742-existing-backup.json")
