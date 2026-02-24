import os
import posixpath
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.files.storage import storages
from django.core.management.base import BaseCommand, CommandError

from core.services.logger_service import Logger

logger = Logger.get_logger(__name__)


class Command(BaseCommand):
    help = "Uploads media files to the configured S3 backup storage."

    def add_arguments(self, parser):
        parser.add_argument(
            "backup_dir",
            type=str,
            help="Destination directory under the backup storage location (e.g. media_YYYYMMDD).",
        )

    def handle(self, *args, **kwargs):
        backup_dir = self._normalize_prefix(kwargs["backup_dir"])
        media_root = Path(settings.MEDIA_ROOT)

        if not media_root.exists():
            raise CommandError(f"Media root does not exist: {media_root}")
        if not media_root.is_dir():
            raise CommandError(f"Media root is not a directory: {media_root}")

        backup_storage = storages["dbbackup"]
        deleted_count = self._delete_prefix_tree(backup_storage, backup_dir)
        uploaded_count = self._upload_media_tree(
            backup_storage,
            media_root=media_root,
            destination_prefix=backup_dir,
            exclude_folders=set(getattr(settings, "DBBACKUP_EXCLUDE_MEDIA_FODERS", [])),
        )

        logger.info(
            "Uploaded %s media files to backup directory '%s' (deleted %s existing files first).",
            uploaded_count,
            backup_dir,
            deleted_count,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Uploaded {uploaded_count} media files to backup directory '{backup_dir}' (deleted {deleted_count})."
            )
        )

    @staticmethod
    def _normalize_prefix(value: str) -> str:
        normalized = (value or "").strip().replace("\\", "/").strip("/")
        if not normalized:
            raise CommandError("backup_dir cannot be empty.")
        return normalized

    def _delete_prefix_tree(self, storage, prefix: str) -> int:
        deleted_count = 0
        pending_paths = [prefix]

        while pending_paths:
            current = pending_paths.pop()
            try:
                directories, files = storage.listdir(current)
            except (FileNotFoundError, NotADirectoryError, OSError):
                continue

            for file_name in files:
                storage_path = posixpath.join(current, file_name) if current else file_name
                storage.delete(storage_path)
                deleted_count += 1

            for directory_name in directories:
                storage_path = posixpath.join(current, directory_name) if current else directory_name
                pending_paths.append(storage_path)

        return deleted_count

    def _upload_media_tree(self, storage, *, media_root: Path, destination_prefix: str, exclude_folders: set[str]) -> int:
        file_count = 0
        for root, dirs, files in os.walk(media_root):
            dirs[:] = [directory for directory in dirs if directory not in exclude_folders]
            root_path = Path(root)

            for file_name in files:
                local_file_path = root_path / file_name
                relative_path = local_file_path.relative_to(media_root).as_posix()
                storage_path = posixpath.join(destination_prefix, relative_path)

                with local_file_path.open("rb") as file_handle:
                    storage.save(storage_path, File(file_handle))
                file_count += 1

        return file_count
