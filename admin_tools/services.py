# Vanilla Django backup/restore using only dumpdata/loaddata/flush
import datetime
import gzip
import io
import os
import shutil
import tarfile
import tempfile

from django.apps import apps
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.db.models.fields.files import FileField

BACKUPS_DIR = os.path.join(settings.BASE_DIR, "backups")


def ensure_backups_dir():
    os.makedirs(BACKUPS_DIR, exist_ok=True)


def backup_all(progress_callback=None, include_users=False):
    """Backup all Django model data using dumpdata, compress to gzipped JSON.
    If include_users is False, exclude system/user tables.
    """
    ensure_backups_dir()
    ts = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    suffix = "_with_users" if include_users else ""
    # Use tar.gz archive to store JSON dump + media files
    filename = f"backup-{ts}{suffix}.tar.gz"
    out_path = os.path.join(BACKUPS_DIR, filename)

    if progress_callback:
        progress_callback("Starting Django dumpdata backup...")

    # Build dumpdata args
    tmp_path = os.path.join(BACKUPS_DIR, f"tmp-{ts}.json")
    dump_args = ["dumpdata"]
    excluded_prefixes = ("auth", "admin", "sessions", "contenttypes", "debug_toolbar")
    if not include_users:
        for prefix in excluded_prefixes:
            dump_args.append(f"--exclude={prefix}")
    with open(tmp_path, "w+") as tmpf:
        call_command(*dump_args, stdout=tmpf)

    # Build a temporary directory to assemble our tar
    temp_dir = tempfile.mkdtemp(prefix=f"backup-{ts}-")
    try:
        # Copy JSON dump into temp dir
        temp_json = os.path.join(temp_dir, "data.json")
        shutil.copy(tmp_path, temp_json)

        # Collect all FileField paths referenced in DB (e.g., Document.file, Customer.passport_file)
        filepaths = set()
        try:
            from django.apps import apps

            for model in apps.get_models():
                for field in model._meta.get_fields():
                    if isinstance(field, FileField):
                        field_name = field.name
                        # Query for non-null/non-empty values
                        try:
                            qs = model.objects.exclude(**{f"{field_name}": ""}).values_list(field_name, flat=True)
                        except Exception:
                            # If model has no data or queryset fails, skip
                            continue
                        for rel_path in qs:
                            if not rel_path:
                                continue
                            # some storage backends may not implement path
                            try:
                                storage_path = default_storage.path(rel_path)
                            except Exception:
                                # Fallback: we can't get filesystem path; we'll include via default_storage.open during tar creation
                                storage_path = None
                            # Keep entries even if storage_path is None (to include via open)
                            filepaths.add((rel_path, storage_path))
        except Exception:
            filepaths = set()

        if progress_callback:
            progress_callback(f"Found {len(filepaths)} media files referenced in DB to include in backup")

        # Create tar.gz with JSON, manifest and files under 'media/' prefix
        with tarfile.open(out_path, "w:gz") as tar:
            tar.add(temp_json, arcname="data.json")
            for rel_path, storage_path in sorted(filepaths):
                # store under media/relative_path so we can restore to MEDIA_ROOT
                arcname = os.path.join("media", rel_path)
                if storage_path and os.path.exists(storage_path):
                    tar.add(storage_path, arcname=arcname)
                else:
                    # open via default_storage and add as fileobj
                    try:
                        f = default_storage.open(rel_path, "rb")
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
                        f.close()
                    except Exception:
                        if progress_callback:
                            progress_callback(f"Warning: could not include file: {rel_path}")
                if progress_callback:
                    progress_callback(f"Included file in backup: {rel_path}")
            # write a manifest.json with included files metadata
            manifest_files = []
            for rel_path, storage_path in sorted(filepaths):
                try:
                    if storage_path:
                        size = os.path.getsize(storage_path)
                    else:
                        size = default_storage.size(rel_path)
                except Exception:
                    size = None
                manifest_files.append({"path": rel_path, "size": size})
            manifest = {"timestamp": ts, "included_files_count": len(filepaths), "files": manifest_files}
            import json as _json

            manifest_bytes = _json.dumps(manifest).encode("utf-8")
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

    if progress_callback:
        progress_callback(f"Backup written to: {out_path}")
        progress_callback("Models included in backup:")
        for m in included_models:
            progress_callback(f"- {m}")
    return out_path


def restore_from_file(path, progress_callback=None, include_users=False):
    """Restore DB from a gzipped dumpdata file (Django JSON). If include_users is False, do not flush system/user tables."""
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    import json

    from django.apps import apps
    from django.db import connection

    tmp_path = None
    extracted_tmp = None
    # temp dir for extracted files
    extracted_media_tmpdir = None
    try:
        # Handle tar.gz backed up archives that include files
        if path.endswith(".tar.gz"):
            # Extract tar to a temp dir and set fixture_path to extracted data.json
            extracted_tmp = tempfile.mkdtemp(prefix="restore-")
            extracted_media_tmpdir = os.path.join(extracted_tmp, "media")
            os.makedirs(extracted_media_tmpdir, exist_ok=True)
            with tarfile.open(path, "r:gz") as tar:
                tar.extractall(path=extracted_tmp)
            fixture_path = os.path.join(extracted_tmp, "data.json")
        elif path.endswith(".gz"):
            import gzip

            tmp_path = path + ".decompressed.json"
            with gzip.open(path, "rb") as f_in, open(tmp_path, "wb") as f_out:
                f_out.write(f_in.read())
            fixture_path = tmp_path
        else:
            fixture_path = path

        # --- Automatic detection of user/system tables in backup ---
        user_system_prefixes = ("auth.", "admin.", "sessions.", "contenttypes.", "debug_toolbar.")
        includes_users = False
        # Only scan the first 1000 objects for performance
        try:
            with open(fixture_path, "r") as f:
                # The file is a JSON array of objects
                objs = json.load(f)
                for obj in objs[:1000]:
                    if "model" in obj and obj["model"].startswith(user_system_prefixes):
                        includes_users = True
                        break
        except Exception as e:
            if progress_callback:
                progress_callback(f"Warning: Could not inspect backup for user tables: {e}")

        # Disable foreign key checks
        engine = connection.vendor
        if progress_callback:
            progress_callback("Disabling foreign key checks...")
        with connection.cursor() as cursor:
            if engine == "sqlite":
                cursor.execute("PRAGMA foreign_keys = OFF;")
            elif engine == "mysql":
                cursor.execute("SET foreign_key_checks = 0;")
            elif engine == "postgresql":
                cursor.execute("SET session_replication_role = replica;")

        # Only flush the right tables
        if progress_callback:
            if includes_users:
                progress_callback("Flushing database (all tables, including users/groups/permissions)...")
            else:
                progress_callback("Flushing database (only data tables, users/groups/permissions will be preserved)...")
        excluded_prefixes = ("auth", "admin", "sessions", "contenttypes", "debug_toolbar")
        if includes_users:
            call_command("flush", "--noinput")
        else:
            # Only flush non-system tables
            tables_to_flush = []
            for model in apps.get_models():
                label = model._meta.label_lower
                if not label.startswith(excluded_prefixes):
                    tables_to_flush.append(model._meta.db_table)
            if tables_to_flush:
                with connection.cursor() as cursor:
                    for table in tables_to_flush:
                        cursor.execute(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE;')

        if progress_callback:
            progress_callback("Loading data via loaddata...")

        call_command("loaddata", fixture_path)

        if progress_callback:
            progress_callback("Restore completed successfully.")

        # If archive included media files, use default_storage to restore them (overwrite existing)
        if extracted_media_tmpdir and os.path.exists(extracted_media_tmpdir):
            from django.core.files import File

            for root, dirs, files in os.walk(extracted_media_tmpdir):
                for fname in files:
                    src = os.path.join(root, fname)
                    # relative path under extracted_media_tmpdir
                    rel = os.path.relpath(src, extracted_media_tmpdir)
                    try:
                        with open(src, "rb") as fsrc:
                            django_file = File(fsrc)
                            # Ensure existing file is removed to allow overwrite
                            if default_storage.exists(rel):
                                try:
                                    default_storage.delete(rel)
                                except Exception:
                                    pass
                            default_storage.save(rel, django_file)
                        if progress_callback:
                            progress_callback(f"Restored media file: {rel}")
                    except Exception as e:
                        if progress_callback:
                            progress_callback(f"Warning: could not restore media file {rel}: {e}")
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
            if progress_callback:
                progress_callback("Warning: Could not re-enable foreign key checks.")
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        if extracted_tmp and os.path.exists(extracted_tmp):
            try:
                shutil.rmtree(extracted_tmp)
            except Exception:
                pass
