from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings


class _FakeBackupStorage:
    def __init__(self, initial_files=None):
        self.files = {self._normalize(path): b"existing" for path in (initial_files or [])}

    @staticmethod
    def _normalize(path: str) -> str:
        return str(path).replace("\\", "/").strip("/")

    def listdir(self, path):
        normalized_prefix = self._normalize(path)
        prefix = f"{normalized_prefix}/" if normalized_prefix else ""

        matches = [storage_key for storage_key in self.files if storage_key.startswith(prefix)]
        if not matches:
            return [], []

        directories = set()
        files = []
        for storage_key in matches:
            remainder = storage_key[len(prefix) :]
            if "/" in remainder:
                directories.add(remainder.split("/", 1)[0])
            elif remainder:
                files.append(remainder)

        return sorted(directories), sorted(files)

    def delete(self, path):
        self.files.pop(self._normalize(path), None)

    def save(self, path, content):
        self.files[self._normalize(path)] = content.read()
        return path


class UploadMediaToS3CommandTests(SimpleTestCase):
    def test_uploads_media_tree_to_backup_prefix_and_excludes_configured_folders(self):
        with TemporaryDirectory() as tmpdir:
            media_root = Path(tmpdir)
            (media_root / "nested").mkdir(parents=True, exist_ok=True)
            (media_root / "tmpfiles").mkdir(parents=True, exist_ok=True)
            (media_root / "readme.txt").write_text("hello", encoding="utf-8")
            (media_root / "nested" / "inside.bin").write_bytes(b"123")
            (media_root / "tmpfiles" / "secret.txt").write_text("skip me", encoding="utf-8")

            storage = _FakeBackupStorage(
                initial_files=[
                    "media_20260224/obsolete.txt",
                    "media_20260224/nested/legacy.txt",
                    "other-prefix/keep.txt",
                ]
            )

            with (
                override_settings(MEDIA_ROOT=str(media_root), DBBACKUP_EXCLUDE_MEDIA_FODERS=["tmpfiles"]),
                patch("core.management.commands.uploadmediatos3.storages", {"dbbackup": storage}),
            ):
                call_command("uploadmediatos3", "media_20260224")

            self.assertEqual(storage.files["media_20260224/readme.txt"], b"hello")
            self.assertEqual(storage.files["media_20260224/nested/inside.bin"], b"123")
            self.assertNotIn("media_20260224/tmpfiles/secret.txt", storage.files)
            self.assertNotIn("media_20260224/obsolete.txt", storage.files)
            self.assertNotIn("media_20260224/nested/legacy.txt", storage.files)
            self.assertIn("other-prefix/keep.txt", storage.files)

    def test_fails_when_media_root_is_missing(self):
        with TemporaryDirectory() as tmpdir:
            missing_media_root = Path(tmpdir) / "missing"
            with override_settings(MEDIA_ROOT=str(missing_media_root)):
                with self.assertRaises(CommandError):
                    call_command("uploadmediatos3", "media_20260224")
