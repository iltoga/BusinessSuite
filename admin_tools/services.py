# Vanilla Django backup/restore using only dumpdata/loaddata/flush
import datetime
import gzip
import os

from django.conf import settings
from django.core.management import call_command

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
    filename = f"backup-{ts}{suffix}.json.gz"
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

    # Compress the temp file to gz
    with open(tmp_path, "rb") as f_in, gzip.open(out_path, "wb") as f_out:
        f_out.writelines(f_in)

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
    try:
        # Decompress if needed
        if path.endswith(".gz"):
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
