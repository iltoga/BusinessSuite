# Vanilla Django backup/restore using only dumpdata/loaddata/flush
import datetime
import gzip
import io
import json
import os
import shutil
import tarfile
import tempfile
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.files import File
from django.core.files.storage import FileSystemStorage
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.db.models.fields.files import FileField
from django.utils.module_loading import import_string

BACKUPS_DIR = getattr(settings, "BACKUPS_ROOT", os.path.join(settings.BASE_DIR, "backups"))
USER_RELATED_MODELS = {"core.userprofile", "core.usersettings", "core.webpushsubscription"}


def _is_external_object_storage(storage) -> bool:
    # Treat non-filesystem storage as external object storage.
    return not isinstance(storage, FileSystemStorage)


def _detect_storage_provider(storage) -> str:
    backend_path = f"{storage.__class__.__module__}.{storage.__class__.__name__}".lower()
    if "s3" in backend_path:
        return "s3"
    if "azure" in backend_path:
        return "azure"
    if "gcloud" in backend_path or "google" in backend_path:
        return "gcs"
    if "dropbox" in backend_path:
        return "dropbox"
    return "unknown"


def _build_storage_descriptor(storage) -> dict:
    return {
        "backend": f"{storage.__class__.__module__}.{storage.__class__.__name__}",
        "provider": _detect_storage_provider(storage),
        "bucket": (
            getattr(storage, "bucket_name", None)
            or getattr(storage, "container_name", None)
            or getattr(settings, "AWS_STORAGE_BUCKET_NAME", None)
        ),
        "location": getattr(storage, "location", ""),
        "endpoint_url": getattr(storage, "endpoint_url", None) or getattr(settings, "AWS_S3_ENDPOINT_URL", None),
        "region_name": getattr(storage, "region_name", None) or getattr(settings, "AWS_S3_REGION_NAME", None),
        "signature_version": getattr(storage, "signature_version", None)
        or getattr(settings, "AWS_S3_SIGNATURE_VERSION", None),
        "addressing_style": getattr(storage, "addressing_style", None)
        or getattr(settings, "AWS_S3_ADDRESSING_STYLE", None),
        "custom_domain": getattr(storage, "custom_domain", None) or getattr(settings, "AWS_S3_CUSTOM_DOMAIN", None),
    }


def _collect_referenced_filepaths() -> list[str]:
    filepaths = set()
    for model in apps.get_models():
        for field in model._meta.get_fields():
            if not isinstance(field, FileField):
                continue
            field_name = field.name
            try:
                qs = model.objects.exclude(**{f"{field_name}": ""}).values_list(field_name, flat=True)
            except Exception:
                continue
            for rel_path in qs:
                if rel_path:
                    filepaths.add(rel_path)
    return sorted(filepaths)


def _manifest_filepaths(manifest: dict) -> list[str]:
    paths = []
    for entry in manifest.get("files", []):
        if isinstance(entry, str):
            if entry:
                paths.append(entry)
            continue
        if isinstance(entry, dict):
            path = entry.get("path")
            if path:
                paths.append(path)
    return paths


def _load_manifest(extracted_tmp: str | None) -> dict:
    if not extracted_tmp:
        return {}
    manifest_path = os.path.join(extracted_tmp, "manifest.json")
    if not os.path.exists(manifest_path):
        return {}
    try:
        with open(manifest_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, dict):
                return data
    except Exception:
        return {}
    return {}


def _build_source_storage_from_manifest(manifest: dict):
    media_meta = manifest.get("media", {}) if isinstance(manifest, dict) else {}
    storage_meta = media_meta.get("storage", {}) if isinstance(media_meta, dict) else {}

    backend_path = storage_meta.get("backend")
    provider = storage_meta.get("provider")

    if not backend_path:
        if provider == "s3":
            backend_path = "storages.backends.s3boto3.S3Boto3Storage"
        else:
            return None, "Missing source storage backend in backup manifest"

    try:
        storage_cls = import_string(backend_path)
    except Exception as exc:
        return None, f"Cannot import source storage backend '{backend_path}': {exc}"

    options = {}
    if storage_meta.get("bucket"):
        options["bucket_name"] = storage_meta.get("bucket")
    if storage_meta.get("location"):
        options["location"] = storage_meta.get("location")
    if storage_meta.get("endpoint_url"):
        options["endpoint_url"] = storage_meta.get("endpoint_url")
    if storage_meta.get("region_name"):
        options["region_name"] = storage_meta.get("region_name")
    if storage_meta.get("signature_version"):
        options["signature_version"] = storage_meta.get("signature_version")
    if storage_meta.get("addressing_style"):
        options["addressing_style"] = storage_meta.get("addressing_style")
    if storage_meta.get("custom_domain"):
        options["custom_domain"] = storage_meta.get("custom_domain")

    # Explicit restore-source overrides for cross-bucket / cross-account migrations.
    if "s3" in backend_path.lower() or provider == "s3":
        options["access_key"] = os.getenv("RESTORE_SOURCE_AWS_ACCESS_KEY_ID", os.getenv("AWS_ACCESS_KEY_ID"))
        options["secret_key"] = os.getenv("RESTORE_SOURCE_AWS_SECRET_ACCESS_KEY", os.getenv("AWS_SECRET_ACCESS_KEY"))
        options["bucket_name"] = os.getenv(
            "RESTORE_SOURCE_AWS_STORAGE_BUCKET_NAME",
            options.get("bucket_name") or os.getenv("AWS_STORAGE_BUCKET_NAME"),
        )
        options["endpoint_url"] = os.getenv(
            "RESTORE_SOURCE_AWS_S3_ENDPOINT_URL",
            options.get("endpoint_url") or os.getenv("AWS_S3_ENDPOINT_URL"),
        )
        options["region_name"] = os.getenv(
            "RESTORE_SOURCE_AWS_S3_REGION_NAME",
            options.get("region_name") or os.getenv("AWS_S3_REGION_NAME"),
        )
        options["signature_version"] = os.getenv(
            "RESTORE_SOURCE_AWS_S3_SIGNATURE_VERSION",
            options.get("signature_version") or os.getenv("AWS_S3_SIGNATURE_VERSION"),
        )
        options["addressing_style"] = os.getenv(
            "RESTORE_SOURCE_AWS_S3_ADDRESSING_STYLE",
            options.get("addressing_style") or os.getenv("AWS_S3_ADDRESSING_STYLE"),
        )
        options["location"] = os.getenv("RESTORE_SOURCE_AWS_LOCATION", options.get("location"))

    options = {key: value for key, value in options.items() if value not in (None, "")}
    try:
        storage = storage_cls(**options)
    except Exception as exc:
        return None, f"Failed to initialize source storage backend '{backend_path}': {exc}"
    return storage, None


def _strip_user_related_objects_from_fixture(fixture_path: str, model_labels: set[str]) -> tuple[str | None, int]:
    """Remove user-bound objects from a fixture used for partial (no-users) restores."""
    try:
        with open(fixture_path, "r", encoding="utf-8") as handle:
            objects = json.load(handle)
    except Exception:
        return None, 0

    if not isinstance(objects, list):
        return None, 0

    filtered = []
    removed = 0
    for obj in objects:
        if isinstance(obj, dict) and obj.get("model") in model_labels:
            removed += 1
            continue
        filtered.append(obj)

    if removed == 0:
        return None, 0

    fd, sanitized_path = tempfile.mkstemp(prefix="restore-sanitized-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(filtered, out)
    except Exception:
        try:
            os.unlink(sanitized_path)
        except Exception:
            pass
        return None, 0

    return sanitized_path, removed


def ensure_backups_dir():
    os.makedirs(BACKUPS_DIR, exist_ok=True)


def backup_all(include_users=False):
    """Backup all Django model data using dumpdata, compress to gzipped JSON.
    If include_users is False, exclude system/user tables.
    Returns a generator of progress messages. Final yielding is the path.
    """
    ensure_backups_dir()
    ts = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    suffix = "_with_users" if include_users else ""
    # Use tar.zst archive (Python 3.14+) to store JSON dump + manifest (+ media payload only for local storage).
    filename = f"backup-{ts}{suffix}.tar.zst"
    out_path = os.path.join(BACKUPS_DIR, filename)

    yield "Starting Django dumpdata backup..."

    # Build dumpdata args
    tmp_path = os.path.join(BACKUPS_DIR, f"tmp-{ts}.json")
    dump_args = ["dumpdata", "--natural-foreign", "--natural-primary"]
    excluded_prefixes = ("auth", "admin", "sessions", "contenttypes", "debug_toolbar")
    if not include_users:
        for prefix in excluded_prefixes:
            dump_args.append(f"--exclude={prefix}")
        for model_label in USER_RELATED_MODELS:
            dump_args.append(f"--exclude={model_label}")
    with open(tmp_path, "w+") as tmpf:
        call_command(*dump_args, stdout=tmpf)

    # Build a temporary directory to assemble our tar
    temp_dir = tempfile.mkdtemp(prefix=f"backup-{ts}-")
    try:
        # Copy JSON dump into temp dir
        temp_json = os.path.join(temp_dir, "data.json")
        shutil.copy(tmp_path, temp_json)

        filepaths = _collect_referenced_filepaths()
        uses_external_media_storage = _is_external_object_storage(default_storage)
        storage_descriptor = _build_storage_descriptor(default_storage)

        yield f"Found {len(filepaths)} media files referenced in DB"
        if uses_external_media_storage:
            yield (
                "Media storage is external object storage "
                f"({storage_descriptor.get('provider')}:{storage_descriptor.get('bucket')}); "
                "skipping media file embedding in backup archive."
            )
        else:
            yield "Media storage is local filesystem; embedding media files in backup archive."

        # Create tar.zst with JSON, manifest and files under 'media/' prefix
        with tarfile.open(out_path, "w:zst") as tar:
            tar.add(temp_json, arcname="data.json")

            embedded_file_count = 0
            if not uses_external_media_storage:
                for i, rel_path in enumerate(filepaths):
                    # store under media/relative_path so we can restore to MEDIA_ROOT
                    arcname = os.path.join("media", rel_path)
                    # open via default_storage and add as fileobj
                    try:
                        with default_storage.open(rel_path, "rb") as f:
                            info = tarfile.TarInfo(name=arcname)
                            # Get size from fileobj if possible
                            try:
                                f.seek(0, os.SEEK_END)
                                size = f.tell()
                                f.seek(0)
                            except Exception:
                                size = None
                            if size is None:
                                # read to memory
                                data = f.read()
                                info.size = len(data)
                                tar.addfile(info, io.BytesIO(data))
                            else:
                                info.size = size
                                tar.addfile(info, f)
                            embedded_file_count += 1
                    except Exception:
                        yield f"Warning: could not include file: {rel_path}"

                    if (i + 1) % 10 == 0 or (i + 1) == len(filepaths):
                        yield f"Included {i + 1}/{len(filepaths)} media files in backup"

            # write a manifest.json with included files metadata
            manifest_files = []
            for rel_path in filepaths:
                manifest_entry = {"path": rel_path}
                # Preserve sizes only when we embed media in backup archive.
                if not uses_external_media_storage:
                    try:
                        manifest_entry["size"] = default_storage.size(rel_path)
                    except Exception:
                        manifest_entry["size"] = None
                manifest_files.append(manifest_entry)

            manifest = {
                "timestamp": ts,
                "included_files_count": embedded_file_count,
                "referenced_files_count": len(filepaths),
                "media": {
                    "included_in_archive": not uses_external_media_storage,
                    "mode": "embedded" if not uses_external_media_storage else "external_storage_reference",
                    "storage": storage_descriptor,
                },
                "files": manifest_files,
            }

            manifest_bytes = json.dumps(manifest).encode("utf-8")
            manifest_info = tarfile.TarInfo(name="manifest.json")
            manifest_info.size = len(manifest_bytes)
            tar.addfile(manifest_info, fileobj=io.BytesIO(manifest_bytes))
    finally:
        shutil.rmtree(temp_dir)

    # List all models included in the backup
    from django.apps import apps

    included_models = []
    for model in apps.get_models():
        label = model._meta.label_lower
        if include_users or not label.startswith(excluded_prefixes):
            included_models.append(label)
    included_models.sort()

    try:
        os.unlink(tmp_path)
    except Exception:
        pass

    yield f"Backup written to: {out_path}"
    # Yield the path marked as a special message
    yield f"RESULT_PATH:{out_path}"


def restore_from_file(path, include_users=False):
    """Restore DB from a gzipped dumpdata file (Django JSON). If include_users is False, do not flush system/user tables.
    Returns a generator of progress messages. Wrapped in atomic transaction with rollback on error.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    # Import the signal handlers so we can disconnect them
    from core.models.user_profile import UserProfile, create_user_profile, save_user_profile
    from core.models.user_settings import create_user_settings, save_user_settings
    from django.apps import apps
    from django.contrib.auth.models import User
    from django.db import connection, transaction
    from django.db.models.signals import post_save

    tmp_path = None
    extracted_tmp = None
    extracted_media_tmpdir = None
    sanitized_fixture_path = None
    manifest = {}
    signals_disconnected = False

    try:
        # Handle tar backed up archives that include files (gz or zst for Python 3.14+)
        if path.endswith((".tar.gz", ".tar.zst")):
            yield "Extracting archive..."
            comp = "zst" if path.endswith(".tar.zst") else "gz"
            extracted_tmp = tempfile.mkdtemp(prefix="restore-")
            extracted_media_tmpdir = os.path.join(extracted_tmp, "media")
            os.makedirs(extracted_media_tmpdir, exist_ok=True)
            with tarfile.open(path, f"r:{comp}") as tar:
                tar.extractall(path=extracted_tmp)
            manifest = _load_manifest(extracted_tmp)
            fixture_path = os.path.join(extracted_tmp, "data.json")
        elif path.endswith((".gz", ".zst")):
            try:
                import compression.zstd as zstd
            except ImportError:
                zstd = None

            yield f"Decompressing {path.split('.')[-1]} JSON..."
            tmp_path = path + ".decompressed.json"

            if path.endswith(".zst") and zstd:
                with zstd.open(path, "rb") as f_in, open(tmp_path, "wb") as f_out:
                    f_out.write(f_in.read())
            else:
                with gzip.open(path, "rb") as f_in, open(tmp_path, "wb") as f_out:
                    f_out.write(f_in.read())
            fixture_path = tmp_path
        else:
            fixture_path = path

        # --- Automatic detection of user/system tables in backup ---
        user_system_prefixes = ("auth.", "admin.", "sessions.", "contenttypes.", "debug_toolbar.")
        includes_users = False
        try:
            with open(fixture_path, "r") as f:
                objs = json.load(f)
                for obj in objs:
                    if "model" in obj and obj["model"].startswith(user_system_prefixes):
                        includes_users = True
                        break
        except Exception as e:
            yield f"Warning: Could not inspect backup for user tables: {e}"

        if not includes_users:
            sanitized_fixture_path, removed_count = _strip_user_related_objects_from_fixture(
                fixture_path, USER_RELATED_MODELS
            )
            if sanitized_fixture_path:
                fixture_path = sanitized_fixture_path
                yield f"Skipped {removed_count} user-related records from fixture for partial restore."

        # Disable foreign key checks
        engine = connection.vendor
        yield "Disabling foreign key checks..."
        with connection.cursor() as cursor:
            if engine == "sqlite":
                cursor.execute("PRAGMA foreign_keys = OFF;")
            elif engine == "mysql":
                cursor.execute("SET foreign_key_checks = 0;")
            elif engine == "postgresql":
                cursor.execute("SET session_replication_role = replica;")

        # Only flush the right tables
        if includes_users:
            yield "Flushing database (all tables, including users/groups/permissions)..."
        else:
            yield "Flushing database (only data tables, users/groups/permissions preserved)..."

        excluded_prefixes = ("auth", "admin", "sessions", "contenttypes", "debug_toolbar")

        # Use a savepoint for atomic rollback capability
        sid = transaction.savepoint()
        try:
            if includes_users:
                call_command("flush", "--noinput")
                try:
                    from django.contrib.auth import get_user_model
                    from django.contrib.auth.models import Permission
                    from django.contrib.contenttypes.models import ContentType

                    yield "Clearing content types, permissions, users, and profiles..."
                    # Delete in order to respect FK constraints
                    UserProfile.objects.all().delete()
                    Permission.objects.all().delete()
                    get_user_model().objects.all().delete()
                    ContentType.objects.all().delete()
                except Exception as e:
                    yield f"Warning: Could not clear content types/permissions/users: {e}"

                # Disconnect per-user auto-create/save signals to prevent duplicates during loaddata.
                yield "Disconnecting UserProfile/UserSettings signals for clean restore..."
                post_save.disconnect(create_user_profile, sender=User)
                post_save.disconnect(save_user_profile, sender=User)
                post_save.disconnect(create_user_settings, sender=User)
                post_save.disconnect(save_user_settings, sender=User)
                signals_disconnected = True
            else:
                # Only flush non-system tables
                tables_to_flush = []
                for model in apps.get_models():
                    label = model._meta.label_lower
                    if not label.startswith(excluded_prefixes) and label not in USER_RELATED_MODELS:
                        tables_to_flush.append(model._meta.db_table)
                if tables_to_flush:
                    with connection.cursor() as cursor:
                        for table in tables_to_flush:
                            if engine == "sqlite":
                                # SQLite does not support TRUNCATE; use DELETE
                                cursor.execute(f'DELETE FROM "{table}";')
                                # Reset sqlite sequence if present
                                try:
                                    cursor.execute(
                                        "DELETE FROM sqlite_sequence WHERE name = ?;",
                                        (table,),
                                    )
                                except Exception:
                                    pass
                            else:
                                cursor.execute(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE;')

            yield "Loading data via loaddata (this may take a few minutes)..."
            call_command("loaddata", fixture_path)
            yield "Data loading complete."

            # Commit the savepoint
            transaction.savepoint_commit(sid)

        except Exception as e:
            # Rollback to savepoint on any error
            yield f"Error during restore, rolling back: {e}"
            transaction.savepoint_rollback(sid)
            raise

        finally:
            # Reconnect signals regardless of success/failure
            if signals_disconnected:
                yield "Reconnecting UserProfile/UserSettings signals..."
                post_save.connect(create_user_profile, sender=User)
                post_save.connect(save_user_profile, sender=User)
                post_save.connect(create_user_settings, sender=User)
                post_save.connect(save_user_settings, sender=User)

        saved_path_map = {}

        # If archive included media files, restore them from archive payload.
        embedded_media_present = False
        if extracted_media_tmpdir and os.path.exists(extracted_media_tmpdir):
            embedded_files = []
            for root, dirs, files in Path(extracted_media_tmpdir).walk():
                for fname in files:
                    embedded_files.append(str(root / fname))

            if embedded_files:
                embedded_media_present = True
                total_files = len(embedded_files)
                yield f"Restoring {total_files} media files from backup archive..."

                for i, src in enumerate(embedded_files):
                    rel = os.path.relpath(src, extracted_media_tmpdir)
                    try:
                        with open(src, "rb") as fsrc:
                            django_file = File(fsrc)
                            if default_storage.exists(rel):
                                try:
                                    default_storage.delete(rel)
                                except Exception:
                                    pass
                            saved_path = default_storage.save(rel, django_file)
                            if saved_path != rel:
                                saved_path_map[rel] = saved_path

                        if (i + 1) % 10 == 0 or (i + 1) == total_files:
                            progress = int(((i + 1) / total_files) * 100)
                            yield f"PROGRESS:{progress}"
                            yield f"Restored {i + 1}/{total_files} files..."
                    except Exception as e:
                        yield f"Warning: could not restore media file {rel}: {e}"

        # If media was intentionally not embedded (cloud/object storage), copy it from source storage.
        media_meta = manifest.get("media", {}) if isinstance(manifest, dict) else {}
        manifest_filepaths = _manifest_filepaths(manifest)
        uses_external_reference = bool(
            manifest_filepaths
            and (
                not media_meta
                or media_meta.get("mode") == "external_storage_reference"
                or not media_meta.get("included_in_archive", True)
            )
        )
        if uses_external_reference and not embedded_media_present:
            source_storage, storage_error = _build_source_storage_from_manifest(manifest)
            if source_storage is None:
                yield f"Warning: cannot restore external media files: {storage_error}"
            else:
                source_storage_info = media_meta.get("storage", {}) if isinstance(media_meta, dict) else {}
                source_provider = source_storage_info.get("provider", "unknown")
                source_bucket = source_storage_info.get("bucket", "unknown")
                total_files = len(manifest_filepaths)
                yield (
                    f"Restoring {total_files} media files from source object storage "
                    f"(provider={source_provider}, bucket={source_bucket})..."
                )
                for i, rel in enumerate(manifest_filepaths):
                    try:
                        with source_storage.open(rel, "rb") as source_handle:
                            django_file = File(source_handle)
                            if default_storage.exists(rel):
                                try:
                                    default_storage.delete(rel)
                                except Exception:
                                    pass
                            saved_path = default_storage.save(rel, django_file)
                            if saved_path != rel:
                                saved_path_map[rel] = saved_path

                        if (i + 1) % 10 == 0 or (i + 1) == total_files:
                            progress = int(((i + 1) / total_files) * 100)
                            yield f"PROGRESS:{progress}"
                            yield f"Restored {i + 1}/{total_files} files..."
                    except Exception as e:
                        yield f"Warning: could not copy media file {rel} from source storage: {e}"

        # Sync renamed media paths in DB
        if saved_path_map:
            try:
                yield f"Syncing {len(saved_path_map)} renamed media paths..."
                with transaction.atomic():
                    for model in apps.get_models():
                        for field in model._meta.get_fields():
                            if isinstance(field, FileField):
                                field_name = field.name
                                old_paths = list(saved_path_map.keys())
                                try:
                                    qs = model.objects.filter(**{f"{field_name}__in": old_paths})
                                except Exception:
                                    continue
                                for obj in qs:
                                    current_value = getattr(obj, field_name)
                                    if not current_value:
                                        continue
                                    old_path = current_value.name
                                    new_path = saved_path_map.get(old_path)
                                    if new_path and new_path != old_path:
                                        setattr(obj, field_name, new_path)
                                        obj.save(update_fields=[field_name])
            except Exception as e:
                yield f"Warning: could not sync renamed media paths: {e}"

        yield "Restore completed successfully."
        return True
    finally:
        # Re-enable foreign key checks
        try:
            with connection.cursor() as cursor:
                engine = connection.vendor
                if engine == "sqlite":
                    cursor.execute("PRAGMA foreign_keys = ON;")
                elif engine == "mysql":
                    cursor.execute("SET foreign_key_checks = 1;")
                elif engine == "postgresql":
                    cursor.execute("SET session_replication_role = DEFAULT;")
        except Exception:
            pass
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        if sanitized_fixture_path and os.path.exists(sanitized_fixture_path):
            try:
                os.unlink(sanitized_fixture_path)
            except Exception:
                pass
        if extracted_tmp and os.path.exists(extracted_tmp):
            try:
                shutil.rmtree(extracted_tmp)
            except Exception:
                pass


def check_media_files():
    """Verify disk presence for files referenced in FileFields. Returns list of dicts."""
    from django.apps import apps
    from django.core.files.storage import default_storage
    from django.db.models.fields.files import FileField

    results = []
    for model in apps.get_models():
        for field in model._meta.get_fields():
            if isinstance(field, FileField):
                field_name = field.name
                try:
                    # Check first 100 entries only for performance
                    qs = model.objects.exclude(**{field_name: ""})[:100]
                except Exception:
                    continue
                for obj in qs:
                    file_field = getattr(obj, field_name)
                    if not file_field:
                        continue
                    path = file_field.name
                    exists = default_storage.exists(path)
                    try:
                        url = file_field.url
                        try:
                            abs_path = file_field.path
                        except Exception:
                            abs_path = "N/A (not on local filesystem)"
                    except Exception as e:
                        url = f"ERROR: {str(e)}"
                        abs_path = "ERROR"

                    # Check for file_link discrepancy if it exists on the model
                    file_link = getattr(obj, "file_link", None)
                    discrepancy = False
                    if file_link and url and file_link != url:
                        discrepancy = True

                    results.append(
                        {
                            "model": model._meta.label,
                            "id": obj.pk,
                            "field": field_name,
                            "path": path,
                            "abs_path": abs_path,
                            "exists": exists,
                            "url": url,
                            "file_link": file_link,
                            "discrepancy": discrepancy,
                        }
                    )
    return results


def repair_media_paths():
    """Attempt to find missing files if customer name changed. Returns repair log."""
    from django.apps import apps
    from django.core.files.storage import default_storage
    from django.db.models.fields.files import FileField

    repairs = []
    for model in apps.get_models():
        for field in model._meta.get_fields():
            if isinstance(field, FileField):
                field_name = field.name
                try:
                    qs = model.objects.exclude(**{field_name: ""})
                except Exception:
                    continue
                for obj in qs:
                    file_field = getattr(obj, field_name)
                    if not file_field or default_storage.exists(file_field.name):
                        continue

                    # File is missing. Check if the model has a property 'upload_folder' or similar
                    # that suggests where it SHOULD be now.
                    expected_dir = None
                    if hasattr(obj, "upload_folder"):
                        expected_dir = obj.upload_folder
                    elif hasattr(obj, "doc_application") and hasattr(obj.doc_application, "upload_folder"):
                        # For Document model
                        expected_dir = obj.doc_application.upload_folder

                    if expected_dir:
                        filename = os.path.basename(file_field.name)
                        new_path = f"{expected_dir}/{filename}"
                        if default_storage.exists(new_path):
                            old_path = file_field.name
                            setattr(obj, field_name, new_path)
                            # Also update file_link if present
                            if hasattr(obj, "file_link"):
                                obj.file_link = default_storage.url(new_path)
                            obj.save(update_fields=[field_name] + (["file_link"] if hasattr(obj, "file_link") else []))
                            repairs.append(f"Fixed {model._meta.label} #{obj.pk}: moved from {old_path} to {new_path}")

    return repairs
