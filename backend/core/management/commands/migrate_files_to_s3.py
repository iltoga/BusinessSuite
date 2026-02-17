import shutil
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db.models import FileField, ImageField
from django.utils._os import safe_join


class Command(BaseCommand):
    help = (
        "Upload local media files referenced by FileField/ImageField values to the current default storage "
        "(intended for S3/R2 migrations)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be uploaded without writing anything to S3.",
        )
        parser.add_argument(
            "--source-root",
            default=str(settings.MEDIA_ROOT),
            help="Local media root to read source files from (defaults to settings.MEDIA_ROOT).",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        source_root = Path(options["source_root"]).expanduser().resolve()

        if not source_root.exists():
            raise CommandError(f"Source root does not exist: {source_root}")
        if not source_root.is_dir():
            raise CommandError(f"Source root is not a directory: {source_root}")

        if not getattr(settings, "USE_CLOUD_STORAGE", False):
            message = (
                "USE_CLOUD_STORAGE is False. This command is intended for S3/R2 migration. "
                "Enable USE_CLOUD_STORAGE=True, or run only with --dry-run."
            )
            if dry_run:
                self.stdout.write(self.style.WARNING(message))
            else:
                raise CommandError(message)

        counters = {
            "checked": 0,
            "uploaded": 0,
            "would_upload": 0,
            "already_present": 0,
            "missing_local": 0,
            "errors": 0,
        }

        self.stdout.write(
            f"Scanning FileField/ImageField values using source root: {source_root} "
            f"(dry_run={dry_run}, bucket={getattr(settings, 'AWS_STORAGE_BUCKET_NAME', 'N/A')})"
        )

        for model in apps.get_models():
            if model._meta.proxy:
                continue

            file_fields = [
                field
                for field in model._meta.concrete_fields
                if isinstance(field, (FileField, ImageField))
            ]
            if not file_fields:
                continue

            for field in file_fields:
                queryset = (
                    model._default_manager.exclude(**{f"{field.name}": ""})
                    .exclude(**{f"{field.name}__isnull": True})
                    .only("pk", field.name)
                )

                for obj in queryset.iterator(chunk_size=500):
                    file_attr = getattr(obj, field.name)
                    file_name = getattr(file_attr, "name", None)
                    if not file_name:
                        continue

                    counters["checked"] += 1

                    try:
                        local_path = safe_join(str(source_root), file_name)
                    except SuspiciousFileOperation:
                        counters["errors"] += 1
                        self.stderr.write(
                            f"[ERROR] Suspicious file path for {model._meta.label}#{obj.pk}.{field.name}: {file_name}"
                        )
                        continue

                    local_file = Path(local_path)
                    if not local_file.exists():
                        counters["missing_local"] += 1
                        continue

                    try:
                        if default_storage.exists(file_name):
                            counters["already_present"] += 1
                            continue
                    except Exception as exc:
                        counters["errors"] += 1
                        self.stderr.write(
                            f"[ERROR] Could not check destination object for {file_name}: {exc}"
                        )
                        continue

                    if dry_run:
                        counters["would_upload"] += 1
                        self.stdout.write(f"[DRY RUN] Would upload: {file_name}")
                        continue

                    try:
                        with local_file.open("rb") as source_handle, default_storage.open(file_name, "wb") as target_handle:
                            shutil.copyfileobj(source_handle, target_handle, length=1024 * 1024)
                    except Exception as exc:
                        counters["errors"] += 1
                        self.stderr.write(f"[ERROR] Failed to upload {file_name}: {exc}")
                        continue

                    counters["uploaded"] += 1
                    self.stdout.write(f"[UPLOADED] {file_name}")

        summary = (
            "Migration summary: "
            f"checked={counters['checked']}, "
            f"uploaded={counters['uploaded']}, "
            f"would_upload={counters['would_upload']}, "
            f"already_present={counters['already_present']}, "
            f"missing_local={counters['missing_local']}, "
            f"errors={counters['errors']}"
        )
        self.stdout.write(self.style.SUCCESS(summary))
