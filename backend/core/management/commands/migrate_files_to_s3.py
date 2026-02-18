import shutil
import tempfile
from pathlib import Path

from core.models import DocumentOCRJob, OCRJob
from django.apps import apps
from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db.models import FileField, ImageField
from django.utils._os import safe_join
from invoices.models.import_job import InvoiceImportItem


class Command(BaseCommand):
    help = (
        "Migrate local media files to default storage (S3/R2), including FileField/ImageField references "
        "and extra directories (default_documents/tmpfiles), then rewire DB path/url fields."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be migrated without writing to object storage or DB.",
        )
        parser.add_argument(
            "--source-root",
            default=str(settings.MEDIA_ROOT),
            help="Local media root to read source files from (defaults to settings.MEDIA_ROOT).",
        )
        parser.add_argument(
            "--extra-dir",
            action="append",
            dest="extra_dirs",
            default=None,
            help="Extra directory (relative to source root) to migrate recursively. Can be used multiple times.",
        )

    def handle(self, *args, **options):
        dry_run = bool(options["dry_run"])
        source_root = Path(options["source_root"]).expanduser().resolve()
        extra_dirs = list(options.get("extra_dirs") or [])
        default_extra_dirs = ["default_documents", getattr(settings, "TMPFILES_FOLDER", "tmpfiles")]
        for extra_dir in default_extra_dirs:
            if extra_dir and extra_dir not in extra_dirs:
                extra_dirs.append(extra_dir)

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

        error_log_handle = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix="migrate-files-to-s3-",
            suffix=".log",
            delete=False,
        )
        error_log_path = error_log_handle.name

        counters = {
            "checked": 0,
            "uploaded": 0,
            "would_upload": 0,
            "already_present": 0,
            "missing_local": 0,
            "extra_files_discovered": 0,
            "db_rows_rewired": 0,
            "errors": 0,
        }
        path_mappings: dict[str, str] = {}

        self.stdout.write(
            f"Scanning files using source root: {source_root} "
            f"(dry_run={dry_run}, bucket={getattr(settings, 'AWS_STORAGE_BUCKET_NAME', 'N/A')})"
        )
        self.stdout.write(f"Including extra directories: {', '.join(extra_dirs) if extra_dirs else '(none)'}")
        self.stdout.write(f"Error log file: {error_log_path}")

        def _record_error(message: str):
            counters["errors"] += 1
            self.stderr.write(message)
            error_log_handle.write(message + "\n")
            error_log_handle.flush()

        def _normalize_storage_key(raw_path: str) -> str:
            normalized = (raw_path or "").strip().replace("\\", "/")
            if normalized.startswith("./"):
                normalized = normalized[2:]
            return normalized.lstrip("/")

        def _to_storage_key(path_or_key: str) -> str:
            normalized = (path_or_key or "").strip()
            if not normalized:
                return ""
            candidate = Path(normalized)
            if candidate.is_absolute():
                try:
                    return candidate.resolve().relative_to(source_root).as_posix()
                except Exception:
                    return _normalize_storage_key(normalized)
            return _normalize_storage_key(normalized)

        def _migrate_path(storage_key: str):
            if not storage_key:
                return
            counters["checked"] += 1
            if storage_key in path_mappings:
                return

            try:
                local_path = safe_join(str(source_root), storage_key)
            except SuspiciousFileOperation:
                _record_error(f"[ERROR] Suspicious storage key: {storage_key}")
                return

            local_file = Path(local_path)
            if not local_file.exists():
                counters["missing_local"] += 1
                return

            try:
                object_exists = default_storage.exists(storage_key)
            except Exception as exc:
                _record_error(f"[ERROR] Could not check destination object for {storage_key}: {exc}")
                return

            if object_exists:
                counters["already_present"] += 1
                path_mappings[storage_key] = storage_key
                return

            if dry_run:
                counters["would_upload"] += 1
                path_mappings[storage_key] = storage_key
                self.stdout.write(f"[DRY RUN] Would upload: {storage_key}")
                return

            try:
                with local_file.open("rb") as source_handle, default_storage.open(storage_key, "wb") as target_handle:
                    shutil.copyfileobj(source_handle, target_handle, length=1024 * 1024)
            except Exception as exc:
                _record_error(f"[ERROR] Failed to upload {storage_key}: {exc}")
                return

            counters["uploaded"] += 1
            path_mappings[storage_key] = storage_key
            self.stdout.write(f"[UPLOADED] {storage_key}")

        # Pass 1: FileField/ImageField references.
        for model in apps.get_models():
            if model._meta.proxy:
                continue

            file_fields = [field for field in model._meta.concrete_fields if isinstance(field, (FileField, ImageField))]
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
                    raw_path = getattr(file_attr, "name", None) or ""
                    storage_key = _to_storage_key(raw_path)
                    if not storage_key:
                        continue

                    _migrate_path(storage_key)

                    if raw_path != storage_key:
                        if dry_run:
                            self.stdout.write(
                                f"[DRY RUN] Would rewire {model._meta.label}#{obj.pk}.{field.name}: "
                                f"{raw_path} -> {storage_key}"
                            )
                        else:
                            setattr(obj, field.name, storage_key)
                            try:
                                obj.save(update_fields=[field.name])
                                counters["db_rows_rewired"] += 1
                            except Exception as exc:
                                _record_error(
                                    f"[ERROR] Failed rewiring {model._meta.label}#{obj.pk}.{field.name}: {exc}"
                                )

        # Pass 2: extra directories.
        for extra_dir in extra_dirs:
            extra_dir_norm = _normalize_storage_key(extra_dir)
            if not extra_dir_norm:
                continue
            local_extra_dir = source_root / extra_dir_norm
            if not local_extra_dir.exists() or not local_extra_dir.is_dir():
                self.stdout.write(f"[WARN] Extra directory not found, skipping: {local_extra_dir}")
                continue

            for local_file in local_extra_dir.rglob("*"):
                if not local_file.is_file():
                    continue
                try:
                    storage_key = local_file.resolve().relative_to(source_root).as_posix()
                except Exception:
                    _record_error(f"[ERROR] Could not compute relative key for {local_file}")
                    continue
                counters["extra_files_discovered"] += 1
                _migrate_path(storage_key)

        # Pass 3: path/url rewiring for non-FileField path users.
        migrated_keys = set(path_mappings.keys())

        def _rewire_path_url_model(model, path_field: str, url_field: str | None):
            queryset = model.objects.exclude(**{f"{path_field}": ""}).exclude(**{f"{path_field}__isnull": True})
            for obj in queryset.iterator(chunk_size=500):
                raw_path = getattr(obj, path_field, "") or ""
                storage_key = _to_storage_key(raw_path)
                if storage_key not in migrated_keys:
                    continue

                update_fields = []
                if raw_path != storage_key:
                    setattr(obj, path_field, storage_key)
                    update_fields.append(path_field)

                if url_field:
                    try:
                        new_url = default_storage.url(storage_key)
                    except Exception as exc:
                        _record_error(f"[ERROR] Failed generating URL for {model.__name__}#{obj.pk}: {exc}")
                        continue
                    current_url = getattr(obj, url_field, "") or ""
                    if current_url != new_url:
                        setattr(obj, url_field, new_url)
                        update_fields.append(url_field)

                if not update_fields:
                    continue

                if dry_run:
                    self.stdout.write(
                        f"[DRY RUN] Would rewire {model.__name__}#{obj.pk}: {', '.join(update_fields)}"
                    )
                    continue

                if hasattr(obj, "updated_at") and "updated_at" not in update_fields:
                    update_fields.append("updated_at")
                try:
                    obj.save(update_fields=update_fields)
                    counters["db_rows_rewired"] += 1
                except Exception as exc:
                    _record_error(f"[ERROR] Failed rewiring {model.__name__}#{obj.pk}: {exc}")

        _rewire_path_url_model(OCRJob, "file_path", "file_url")
        _rewire_path_url_model(DocumentOCRJob, "file_path", "file_url")
        _rewire_path_url_model(InvoiceImportItem, "file_path", None)

        error_log_handle.close()

        summary = (
            "Migration summary: "
            f"checked={counters['checked']}, "
            f"uploaded={counters['uploaded']}, "
            f"would_upload={counters['would_upload']}, "
            f"already_present={counters['already_present']}, "
            f"extra_files_discovered={counters['extra_files_discovered']}, "
            f"missing_local={counters['missing_local']}, "
            f"db_rows_rewired={counters['db_rows_rewired']}, "
            f"errors={counters['errors']}"
        )
        if counters["errors"] > 0:
            self.stdout.write(self.style.WARNING(summary))
            self.stdout.write(self.style.WARNING(f"Migration errors logged to: {error_log_path}"))
        else:
            self.stdout.write(self.style.SUCCESS(summary))
            self.stdout.write(f"No migration errors logged. Error log file: {error_log_path}")
