# Vanilla Django backup/restore using only dumpdata/loaddata/flush
import datetime
import gzip
import importlib
import io
import json
import os
import shutil
import tarfile
import tempfile
import time
import uuid
from contextlib import contextmanager, nullcontext
from pathlib import Path
from urllib.parse import unquote, urlparse

from django.apps import apps
from django.conf import settings
from django.core.cache import caches
from django.core.files import File
from django.core.files.storage import FileSystemStorage, default_storage
from django.core.management import call_command
from django.db import connections
from django.db.models.fields.files import FileField
from django.utils import timezone
from django.utils.module_loading import import_string

try:
    from django_redis import get_redis_connection
except Exception:  # pragma: no cover - optional import fallback
    get_redis_connection = None

BACKUPS_DIR = getattr(settings, "BACKUPS_ROOT", os.path.join(settings.BASE_DIR, "backups"))
USER_RELATED_MODELS = {"core.userprofile", "core.usersettings", "core.webpushsubscription"}
_MISSING = object()
_LEGACY_FIELD_RENAMES: dict[str, dict[str, str]] = {
    # products.DocumentType.has_ocr_check -> products.DocumentType.ai_validation
    "products.documenttype": {"has_ocr_check": "ai_validation"},
    # customer_applications.Document.ocr_check -> customer_applications.Document.ai_validation
    "customer_applications.document": {"ocr_check": "ai_validation"},
}


def _get_zstd_module():
    """Return a module exposing ``open`` for .zst streams, if available."""
    for module_name in ("compression.zstd", "zstandard", "backports.zstd"):
        try:
            module = importlib.import_module(module_name)
            if hasattr(module, "open"):
                return module
        except Exception:
            continue
    return None


def _supports_tarfile_zstd_write() -> bool:
    """Whether current Python/tarfile supports mode 'w:zst'."""
    try:
        with tarfile.open(fileobj=io.BytesIO(), mode="w:zst"):
            pass
        return True
    except Exception:
        return False


def _safe_extract_tar(tar: tarfile.TarFile, destination_dir: str) -> None:
    """Extract a tar archive only when every member resolves under destination_dir."""
    destination_abs = os.path.abspath(destination_dir)
    for member in tar.getmembers():
        member_name = member.name
        if not member_name:
            continue

        normalized_name = member_name.replace("\\", "/")
        target_path = os.path.abspath(os.path.join(destination_abs, normalized_name))
        try:
            is_within_destination = os.path.commonpath([destination_abs, target_path]) == destination_abs
        except ValueError:
            is_within_destination = False
        if not is_within_destination:
            raise RuntimeError(f"Unsafe backup archive member path detected: {member_name!r}")

        # Prevent symlink/hardlink path tricks during restore extraction.
        if member.issym() or member.islnk():
            raise RuntimeError(f"Unsafe backup archive link entry detected: {member_name!r}")
        if not (member.isdir() or member.isfile()):
            raise RuntimeError(f"Unsafe backup archive member type detected: {member_name!r}")

    tar.extractall(path=destination_abs)


def _extract_archive_to_dir(path: str, extracted_tmp: str, comp: str) -> None:
    """
    Extract tar archive to a directory.

    For .tar.zst, prefer native tarfile support and fall back to
    backports.zstd/zstandard decompression for Python runtimes that
    do not support mode 'r:zst' (e.g. Python 3.13).
    """
    if comp != "zst":
        with tarfile.open(path, f"r:{comp}") as tar:
            _safe_extract_tar(tar, extracted_tmp)
        return

    try:
        with tarfile.open(path, "r:zst") as tar:
            _safe_extract_tar(tar, extracted_tmp)
        return
    except (tarfile.CompressionError, tarfile.ReadError, ValueError):
        pass

    zstd = _get_zstd_module()
    if not zstd:
        raise RuntimeError(
            "Cannot extract .tar.zst backup: no zstd support available. "
            "Install 'backports-zstd' (or 'zstandard') or restore from .tar.gz."
        )

    decompressed_tar_path = None
    try:
        with tempfile.NamedTemporaryFile(prefix="restore-zst-", suffix=".tar", delete=False) as temp_tar:
            decompressed_tar_path = temp_tar.name

        with zstd.open(path, "rb") as f_in, open(decompressed_tar_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)

        with tarfile.open(decompressed_tar_path, "r:") as tar:
            _safe_extract_tar(tar, extracted_tmp)
    finally:
        if decompressed_tar_path and os.path.exists(decompressed_tar_path):
            try:
                os.unlink(decompressed_tar_path)
            except Exception:
                pass


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


def _normalized_descriptor_value(value):
    if value is None:
        return ""
    return str(value).strip()


def _storage_descriptors_match(source_meta: dict, target_meta: dict) -> bool:
    """
    Determine whether source/target storage descriptors represent the same object storage.

    We intentionally match on provider/bucket plus optional endpoint/location metadata,
    instead of strict backend class equality, so compatible custom storage subclasses
    are still recognized as the same storage.
    """
    if not isinstance(source_meta, dict) or not isinstance(target_meta, dict):
        return False

    source_provider = _normalized_descriptor_value(source_meta.get("provider")).lower()
    target_provider = _normalized_descriptor_value(target_meta.get("provider")).lower()
    if source_provider and target_provider and source_provider != target_provider:
        return False

    compared_any = False
    for key in ("bucket", "endpoint_url", "location", "region_name", "custom_domain"):
        source_value = _normalized_descriptor_value(source_meta.get(key))
        target_value = _normalized_descriptor_value(target_meta.get(key))
        if source_value and target_value:
            compared_any = True
            if source_value != target_value:
                return False

    if compared_any:
        return True

    source_backend = _normalized_descriptor_value(source_meta.get("backend"))
    target_backend = _normalized_descriptor_value(target_meta.get("backend"))
    if source_backend and target_backend:
        return source_backend == target_backend

    return False


def _is_missing_source_error(exc: Exception) -> bool:
    if isinstance(exc, FileNotFoundError):
        return True

    if getattr(exc, "errno", None) == 2:
        return True

    text = str(exc).strip().lower()
    if not text:
        return False

    return any(
        marker in text
        for marker in (
            "nosuchkey",
            "no such key",
            "not found",
            "no such file",
            "does not exist",
        )
    )


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


def _customer_full_name_from_fields(fields: dict) -> str:
    customer_type = fields.get("customer_type")
    first_name = fields.get("first_name")
    last_name = fields.get("last_name")
    company_name = fields.get("company_name")

    if customer_type == "company" and not (first_name and last_name):
        return company_name or "Unknown Company"
    if first_name and last_name:
        return f"{first_name} {last_name}"
    return company_name or "Unknown"


def _resolve_field_like_value(model_label: str, fields: dict, key: str):
    if key in fields:
        return fields.get(key)
    if model_label == "customers.customer" and key == "full_name":
        return _customer_full_name_from_fields(fields)
    return _MISSING


def _normalize_legacy_natural_key_fixture(fixture_path: str) -> tuple[str | None, int, int, int, int]:
    """
    Normalize legacy fixtures generated with broken dict-based natural keys.

    The legacy format can contain:
    - dict-valued FK/M2M references
    - missing primary keys for objects serialized with --natural-primary

    Returns (
        normalized_path,
        assigned_pk_count,
        converted_ref_count,
        unresolved_ref_count,
        ambiguous_ref_count,
    ).
    """
    try:
        with open(fixture_path, "r", encoding="utf-8") as handle:
            objects = json.load(handle)
    except Exception:
        return None, 0, 0, 0, 0

    if not isinstance(objects, list):
        return None, 0, 0, 0, 0

    objects_by_model = {}
    needs_normalization = False

    for obj in objects:
        if not isinstance(obj, dict):
            continue
        model_label = obj.get("model")
        fields = obj.get("fields")
        if not isinstance(model_label, str) or not isinstance(fields, dict):
            continue
        objects_by_model.setdefault(model_label, []).append(obj)

        if "pk" not in obj:
            needs_normalization = True
        for value in fields.values():
            if isinstance(value, dict):
                needs_normalization = True
                break
            if isinstance(value, list) and any(isinstance(item, dict) for item in value):
                needs_normalization = True
                break

    if not needs_normalization:
        return None, 0, 0, 0, 0

    assigned_pk_count = 0
    converted_ref_count = 0
    unresolved_ref_count = 0
    ambiguous_ref_count = 0

    # Step 1: assign synthetic PKs when omitted by legacy natural-primary dumps.
    for model_label, entries in objects_by_model.items():
        try:
            model = apps.get_model(model_label)
        except Exception:
            continue

        pk_field = model._meta.pk
        if pk_field.get_internal_type() not in {
            "AutoField",
            "BigAutoField",
            "SmallAutoField",
            "IntegerField",
            "PositiveIntegerField",
            "PositiveSmallIntegerField",
        }:
            continue

        current_max = 0
        for entry in entries:
            if "pk" not in entry:
                continue
            try:
                current_max = max(current_max, int(entry.get("pk")))
            except Exception:
                continue

        for entry in entries:
            if "pk" in entry:
                continue
            current_max += 1
            entry["pk"] = current_max
            assigned_pk_count += 1

    # Cached candidate maps keyed by (model_label, sorted_keys_tuple)
    lookup_cache: dict[tuple[str, tuple[str, ...]], dict[tuple[str, ...], list[object]]] = {}

    def _value_signature(value) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def _build_lookup(model_label: str, keys_tuple: tuple[str, ...]) -> dict[tuple[str, ...], list[object]]:
        cache_key = (model_label, keys_tuple)
        if cache_key in lookup_cache:
            return lookup_cache[cache_key]

        lookup: dict[tuple[str, ...], list[object]] = {}
        for candidate in objects_by_model.get(model_label, []):
            fields = candidate.get("fields")
            if not isinstance(fields, dict):
                continue
            if "pk" not in candidate:
                continue

            signature_values = []
            missing_key = False
            for key in keys_tuple:
                value = _resolve_field_like_value(model_label, fields, key)
                if value is _MISSING:
                    missing_key = True
                    break
                signature_values.append(_value_signature(value))

            if missing_key:
                continue

            signature = tuple(signature_values)
            lookup.setdefault(signature, []).append(candidate.get("pk"))

        lookup_cache[cache_key] = lookup
        return lookup

    def _resolve_pk(model_label: str, natural_dict: dict):
        nonlocal ambiguous_ref_count
        keys_tuple = tuple(sorted(str(key) for key in natural_dict.keys()))
        lookup = _build_lookup(model_label, keys_tuple)
        signature = tuple(_value_signature(natural_dict.get(key)) for key in keys_tuple)
        matches = lookup.get(signature, [])
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            # Legacy fixtures can contain non-unique natural-key dicts.
            # Pick first deterministic fixture-order match so restore can proceed.
            ambiguous_ref_count += 1
            return matches[0]
        return None

    # Step 2: convert dict FK/M2M references into plain PK values.
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        model_label = obj.get("model")
        fields = obj.get("fields")
        if not isinstance(model_label, str) or not isinstance(fields, dict):
            continue

        try:
            model = apps.get_model(model_label)
        except Exception:
            continue

        for field_name, field_value in list(fields.items()):
            try:
                field = model._meta.get_field(field_name)
            except Exception:
                continue

            if field.remote_field and hasattr(field.remote_field, "model"):
                target_model = field.remote_field.model
                target_label = target_model._meta.label_lower

                # FK / OneToOne
                if field.one_to_one or field.many_to_one:
                    if isinstance(field_value, dict):
                        resolved_pk = _resolve_pk(target_label, field_value)
                        if resolved_pk is not None:
                            fields[field_name] = resolved_pk
                            converted_ref_count += 1
                        else:
                            unresolved_ref_count += 1

                # M2M
                elif field.many_to_many and isinstance(field_value, list):
                    updated_values = []
                    changed = False
                    for item in field_value:
                        if isinstance(item, dict):
                            resolved_pk = _resolve_pk(target_label, item)
                            if resolved_pk is not None:
                                updated_values.append(resolved_pk)
                                converted_ref_count += 1
                                changed = True
                            else:
                                updated_values.append(item)
                                unresolved_ref_count += 1
                        else:
                            updated_values.append(item)
                    if changed:
                        fields[field_name] = updated_values

    if assigned_pk_count == 0 and converted_ref_count == 0:
        return None, 0, 0, unresolved_ref_count, ambiguous_ref_count

    fd, normalized_path = tempfile.mkstemp(prefix="restore-normalized-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(objects, out)
    except Exception:
        try:
            os.unlink(normalized_path)
        except Exception:
            pass
        return None, 0, 0, unresolved_ref_count, ambiguous_ref_count

    return normalized_path, assigned_pk_count, converted_ref_count, unresolved_ref_count, ambiguous_ref_count


def _sanitize_fixture_model_fields(
    fixture_path: str,
) -> tuple[str | None, int, int, dict[str, int]]:
    """
    Sanitize fixture field payloads to match the current Django schema.

    - Applies known legacy field renames.
    - Drops unknown fields to prevent loaddata hard-failures after refactors.
    """
    try:
        with open(fixture_path, "r", encoding="utf-8") as handle:
            objects = json.load(handle)
    except Exception:
        return None, 0, 0, {}

    if not isinstance(objects, list):
        return None, 0, 0, {}

    changed = False
    renamed_count = 0
    dropped_count = 0
    dropped_by_model: dict[str, int] = {}
    valid_field_cache: dict[str, set[str]] = {}

    for obj in objects:
        if not isinstance(obj, dict):
            continue

        model_label = obj.get("model")
        fields = obj.get("fields")
        if not isinstance(model_label, str) or not isinstance(fields, dict):
            continue

        # 1) Apply explicit legacy rename mappings.
        rename_map = _LEGACY_FIELD_RENAMES.get(model_label, {})
        for old_name, new_name in rename_map.items():
            if old_name not in fields:
                continue
            if new_name not in fields:
                fields[new_name] = fields[old_name]
                renamed_count += 1
            fields.pop(old_name, None)
            changed = True

        # 2) Drop unknown fields against current model metadata.
        if model_label not in valid_field_cache:
            try:
                model = apps.get_model(model_label)
            except Exception:
                valid_field_cache[model_label] = set()
            else:
                valid_field_cache[model_label] = {
                    field.name
                    for field in model._meta.get_fields()
                    if not (getattr(field, "auto_created", False) and not getattr(field, "concrete", False))
                }

        valid_fields = valid_field_cache.get(model_label, set())
        if not valid_fields:
            continue

        for field_name in list(fields.keys()):
            if field_name in valid_fields:
                continue
            fields.pop(field_name, None)
            dropped_count += 1
            dropped_by_model[model_label] = dropped_by_model.get(model_label, 0) + 1
            changed = True

    if not changed:
        return None, 0, 0, {}

    fd, sanitized_path = tempfile.mkstemp(prefix="restore-schema-sanitized-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(objects, out)
    except Exception:
        try:
            os.unlink(sanitized_path)
        except Exception:
            pass
        return None, 0, 0, {}

    return sanitized_path, renamed_count, dropped_count, dropped_by_model


def _format_bytes(size_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(max(size_bytes, 0))
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size_bytes} B"


def _top_postgres_table_sizes(limit: int = 10) -> list[tuple[str, int]]:
    from django.db import connection

    if connection.vendor != "postgresql":
        return []

    sql = """
        SELECT
            n.nspname || '.' || c.relname AS table_name,
            pg_total_relation_size(c.oid) AS total_bytes
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r'
          AND n.nspname NOT IN ('pg_catalog', 'information_schema')
        ORDER BY total_bytes DESC
        LIMIT %s;
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [limit])
        rows = cursor.fetchall()
    return [(str(name), int(total_bytes or 0)) for name, total_bytes in rows]


def ensure_backups_dir():
    os.makedirs(BACKUPS_DIR, exist_ok=True)


def _is_missing_userprofile_cache_enabled_column_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "core_userprofile.cache_enabled" in text and "does not exist" in text


@contextmanager
def _temporarily_disable_postgres_server_side_cursors(database_alias: str = "default"):
    connection = connections[database_alias]
    if connection.vendor != "postgresql":
        yield
        return

    previous_value = connection.settings_dict.get("DISABLE_SERVER_SIDE_CURSORS", _MISSING)
    connection.settings_dict["DISABLE_SERVER_SIDE_CURSORS"] = True
    try:
        yield
    finally:
        if previous_value is _MISSING:
            connection.settings_dict.pop("DISABLE_SERVER_SIDE_CURSORS", None)
        else:
            connection.settings_dict["DISABLE_SERVER_SIDE_CURSORS"] = previous_value


def backup_all(include_users=False):
    """Backup all Django model data using dumpdata, compress to gzipped JSON.
    If include_users is False, exclude system/user tables.
    Returns a generator of progress messages. Final yielding is the path.
    """
    ensure_backups_dir()
    ts = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d-%H%M%S")
    suffix = "_with_users" if include_users else ""
    use_zst_archive = _supports_tarfile_zstd_write()
    archive_ext = "tar.zst" if use_zst_archive else "tar.gz"
    archive_mode = "w:zst" if use_zst_archive else "w:gz"
    filename = f"backup-{ts}{suffix}.{archive_ext}"
    out_path = os.path.join(BACKUPS_DIR, filename)

    yield "Starting Django dumpdata backup..."

    # Build dumpdata args
    tmp_path = os.path.join(BACKUPS_DIR, f"tmp-{ts}.json")
    # Use PK-based dumpdata for compatibility:
    # some legacy model natural_key() implementations are not loaddata-safe.
    dump_args = ["dumpdata"]
    excluded_prefixes = ("auth", "admin", "sessions", "contenttypes", "debug_toolbar")
    if not include_users:
        for prefix in excluded_prefixes:
            dump_args.append(f"--exclude={prefix}")
        for model_label in USER_RELATED_MODELS:
            dump_args.append(f"--exclude={model_label}")
    with open(tmp_path, "w+") as tmpf:
        try:
            with _temporarily_disable_postgres_server_side_cursors("default"):
                call_command(*dump_args, stdout=tmpf)
        except Exception as exc:
            if include_users and _is_missing_userprofile_cache_enabled_column_error(exc):
                yield (
                    "Warning: detected schema drift (missing core_userprofile.cache_enabled). "
                    "Retrying backup while excluding core.userprofile."
                )
                tmpf.seek(0)
                tmpf.truncate(0)
                fallback_args = [*dump_args, "--exclude=core.userprofile"]
                with _temporarily_disable_postgres_server_side_cursors("default"):
                    call_command(*fallback_args, stdout=tmpf)
            else:
                raise
    try:
        json_size = os.path.getsize(tmp_path)
        yield f"DB dump JSON size (uncompressed): {_format_bytes(json_size)}"
    except Exception:
        pass
    try:
        for idx, (table_name, total_bytes) in enumerate(_top_postgres_table_sizes(limit=10), start=1):
            yield f"Top table {idx}: {table_name} ({_format_bytes(total_bytes)})"
    except Exception as e:
        yield f"Warning: could not compute top PostgreSQL table sizes: {e}"

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

        # Create tar archive with JSON, manifest and files under 'media/' prefix.
        with tarfile.open(out_path, archive_mode) as tar:
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

    try:
        archive_size = os.path.getsize(out_path)
        yield f"Backup archive size: {_format_bytes(archive_size)}"
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

    sync_apply_ctx = nullcontext
    try:
        # Prevent local sync capture signals from writing to SyncChangeLog while fixtures load.
        from core.services.sync_service import sync_apply_context

        sync_apply_ctx = sync_apply_context
    except Exception:
        pass

    tmp_path = None
    extracted_tmp = None
    extracted_media_tmpdir = None
    normalized_fixture_path = None
    sanitized_fixture_path = None
    schema_sanitized_fixture_path = None
    manifest = {}
    signals_disconnected = False

    try:
        # Handle tar-backed archives that include files (.tar.gz or .tar.zst).
        if path.endswith((".tar.gz", ".tar.zst")):
            yield "Extracting archive..."
            comp = "zst" if path.endswith(".tar.zst") else "gz"
            extracted_tmp = tempfile.mkdtemp(prefix="restore-")
            extracted_media_tmpdir = os.path.join(extracted_tmp, "media")
            os.makedirs(extracted_media_tmpdir, exist_ok=True)
            _extract_archive_to_dir(path, extracted_tmp, comp)
            manifest = _load_manifest(extracted_tmp)
            fixture_path = os.path.join(extracted_tmp, "data.json")
        elif path.endswith((".gz", ".zst")):
            zstd = _get_zstd_module()

            yield f"Decompressing {path.split('.')[-1]} JSON..."
            tmp_path = path + ".decompressed.json"

            if path.endswith(".zst") and zstd:
                with zstd.open(path, "rb") as f_in, open(tmp_path, "wb") as f_out:
                    f_out.write(f_in.read())
            elif path.endswith(".zst"):
                raise RuntimeError(
                    "Cannot decompress .zst backup: no zstd support available. "
                    "Install the 'zstandard' package or restore from a .gz/.tar.gz archive."
                )
            else:
                with gzip.open(path, "rb") as f_in, open(tmp_path, "wb") as f_out:
                    f_out.write(f_in.read())
            fixture_path = tmp_path
        else:
            fixture_path = path

        normalized_fixture_path, assigned_pk_count, converted_ref_count, unresolved_ref_count, ambiguous_ref_count = (
            _normalize_legacy_natural_key_fixture(fixture_path)
        )
        if normalized_fixture_path:
            fixture_path = normalized_fixture_path
            yield (
                "Normalized legacy fixture references: "
                f"assigned_pks={assigned_pk_count}, converted_refs={converted_ref_count}, "
                f"ambiguous_refs={ambiguous_ref_count}"
            )
            if ambiguous_ref_count:
                yield (
                    "Warning: some legacy natural-key references were ambiguous; "
                    f"using deterministic first match (count={ambiguous_ref_count})."
                )
            if unresolved_ref_count:
                yield (
                    "Warning: some legacy natural-key references could not be normalized "
                    f"(count={unresolved_ref_count})."
                )

        (
            schema_sanitized_fixture_path,
            renamed_field_count,
            dropped_field_count,
            dropped_fields_by_model,
        ) = _sanitize_fixture_model_fields(fixture_path)
        if schema_sanitized_fixture_path:
            fixture_path = schema_sanitized_fixture_path
            yield (
                "Sanitized fixture fields for current schema: "
                f"renamed_fields={renamed_field_count}, dropped_unknown_fields={dropped_field_count}"
            )
            if dropped_fields_by_model:
                dropped_preview = ", ".join(
                    f"{label}={count}" for label, count in sorted(dropped_fields_by_model.items())[:5]
                )
                yield f"Warning: dropped unknown fields by model: {dropped_preview}"

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

        # Ensure flush + loaddata are atomic so failed restores cannot leave DB half-empty.
        with transaction.atomic():
            sid = transaction.savepoint()
            try:
                if includes_users:
                    call_command("flush", "--noinput")
                    try:
                        from django.contrib.auth import get_user_model
                        from django.contrib.auth.models import Permission
                        from django.contrib.contenttypes.models import ContentType

                        yield "Clearing content types, permissions, users, and profiles..."
                        # Delete in order to respect FK constraints. Guard each delete by
                        # table existence to avoid breaking the transaction on partially
                        # migrated/test databases.
                        existing_tables = set(connection.introspection.table_names())
                        user_model = get_user_model()

                        if UserProfile._meta.db_table in existing_tables:
                            UserProfile.objects.all().delete()
                        if Permission._meta.db_table in existing_tables:
                            Permission.objects.all().delete()
                        if user_model._meta.db_table in existing_tables:
                            user_model.objects.all().delete()
                        if ContentType._meta.db_table in existing_tables:
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
                    existing_tables = set(connection.introspection.table_names())
                    for model in apps.get_models():
                        label = model._meta.label_lower
                        if not label.startswith(excluded_prefixes) and label not in USER_RELATED_MODELS:
                            table_name = model._meta.db_table
                            if table_name in existing_tables:
                                tables_to_flush.append(table_name)
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
                with sync_apply_ctx():
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
        media_summary = {
            "copied": 0,
            "skipped_existing": 0,
            "missing_source": 0,
        }

        # If archive included media files, restore them from archive payload.
        # Never delete destination files during restore: copy only missing objects.
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
                        if default_storage.exists(rel):
                            media_summary["skipped_existing"] += 1
                            if (i + 1) % 10 == 0 or (i + 1) == total_files:
                                progress = int(((i + 1) / total_files) * 100)
                                yield f"PROGRESS:{progress}"
                                yield f"Processed {i + 1}/{total_files} files..."
                            continue

                        with open(src, "rb") as fsrc:
                            django_file = File(fsrc)
                            saved_path = default_storage.save(rel, django_file)
                            if saved_path != rel:
                                saved_path_map[rel] = saved_path
                            media_summary["copied"] += 1

                        if (i + 1) % 10 == 0 or (i + 1) == total_files:
                            progress = int(((i + 1) / total_files) * 100)
                            yield f"PROGRESS:{progress}"
                            yield f"Processed {i + 1}/{total_files} files..."
                    except Exception as e:
                        if _is_missing_source_error(e):
                            media_summary["missing_source"] += 1
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
            source_storage_info = media_meta.get("storage", {}) if isinstance(media_meta, dict) else {}
            target_storage_info = _build_storage_descriptor(default_storage)
            if _storage_descriptors_match(source_storage_info, target_storage_info):
                existing_count = 0
                missing_count = 0
                for rel in manifest_filepaths:
                    try:
                        if default_storage.exists(rel):
                            existing_count += 1
                        else:
                            missing_count += 1
                    except Exception:
                        missing_count += 1
                yield (
                    "Source and target object storage are identical; "
                    "skipping media copy to avoid destructive self-overwrite "
                    f"(existing={existing_count}, missing={missing_count})."
                )
                media_summary["skipped_existing"] += existing_count
                media_summary["missing_source"] += missing_count
            else:
                source_storage, storage_error = _build_source_storage_from_manifest(manifest)
                if source_storage is None:
                    yield f"Warning: cannot restore external media files: {storage_error}"
                else:
                    source_provider = source_storage_info.get("provider", "unknown")
                    source_bucket = source_storage_info.get("bucket", "unknown")
                    total_files = len(manifest_filepaths)
                    yield (
                        f"Restoring {total_files} media files from source object storage "
                        f"(provider={source_provider}, bucket={source_bucket})..."
                    )
                    for i, rel in enumerate(manifest_filepaths):
                        try:
                            if default_storage.exists(rel):
                                media_summary["skipped_existing"] += 1
                                if (i + 1) % 10 == 0 or (i + 1) == total_files:
                                    progress = int(((i + 1) / total_files) * 100)
                                    yield f"PROGRESS:{progress}"
                                    yield f"Processed {i + 1}/{total_files} files..."
                                continue

                            with source_storage.open(rel, "rb") as source_handle:
                                django_file = File(source_handle)
                                saved_path = default_storage.save(rel, django_file)
                                if saved_path != rel:
                                    saved_path_map[rel] = saved_path
                                media_summary["copied"] += 1

                            if (i + 1) % 10 == 0 or (i + 1) == total_files:
                                progress = int(((i + 1) / total_files) * 100)
                                yield f"PROGRESS:{progress}"
                                yield f"Processed {i + 1}/{total_files} files..."
                        except Exception as e:
                            if _is_missing_source_error(e):
                                media_summary["missing_source"] += 1
                            yield f"Warning: could not copy media file {rel} from source storage: {e}"

        yield (
            "RESTORE_SUMMARY: "
            f"copied={media_summary['copied']} "
            f"skipped_existing={media_summary['skipped_existing']} "
            f"missing_source={media_summary['missing_source']}"
        )

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
        if schema_sanitized_fixture_path and os.path.exists(schema_sanitized_fixture_path):
            try:
                os.unlink(schema_sanitized_fixture_path)
            except Exception:
                pass
        if normalized_fixture_path and os.path.exists(normalized_fixture_path):
            try:
                os.unlink(normalized_fixture_path)
            except Exception:
                pass
        if extracted_tmp and os.path.exists(extracted_tmp):
            try:
                shutil.rmtree(extracted_tmp)
            except Exception:
                pass


def check_media_files():
    """Verify storage presence for files referenced in FileFields."""

    def _append_unique(values: list[str], seen: set[str], value: str | None) -> None:
        normalized = _normalize_storage_key(value)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        values.append(normalized)

    def _known_storage_prefixes() -> list[str]:
        prefixes: list[str] = []
        seen: set[str] = set()

        _append_unique(prefixes, seen, getattr(default_storage, "location", ""))

        media_url = urlparse(str(getattr(settings, "MEDIA_URL", "") or "")).path
        _append_unique(prefixes, seen, media_url)

        raw_media_root = str(getattr(settings, "MEDIA_ROOT", "") or "").replace("\\", "/").strip().strip("/")
        if raw_media_root:
            parts = [part for part in raw_media_root.split("/") if part]
            for depth in (1, 2, 3):
                if len(parts) >= depth:
                    _append_unique(prefixes, seen, "/".join(parts[-depth:]))

        return prefixes

    def _strip_prefix(path: str, prefix: str) -> str:
        if not prefix:
            return path
        if path == prefix:
            return ""
        prefixed = f"{prefix}/"
        if path.startswith(prefixed):
            return path[len(prefixed) :]
        return path

    def _normalize_storage_key(raw_path: str | None) -> str:
        if raw_path is None:
            return ""

        value = str(raw_path).strip().strip("'").strip('"')
        if not value:
            return ""

        parsed = urlparse(value)
        if parsed.scheme and parsed.netloc:
            value = parsed.path or ""
        else:
            value = value.split("?", 1)[0]

        value = unquote(value).replace("\\", "/")
        while "//" in value:
            value = value.replace("//", "/")

        media_root = str(getattr(settings, "MEDIA_ROOT", "") or "").replace("\\", "/").rstrip("/")
        if media_root and value.startswith(media_root):
            value = value[len(media_root) :]

        media_url_path = urlparse(str(getattr(settings, "MEDIA_URL", "") or "")).path.replace("\\", "/").strip()
        if media_url_path and value.startswith(media_url_path):
            value = value[len(media_url_path) :]

        return value.strip().strip("/")

    def _candidate_storage_keys(raw_path: str | None) -> list[str]:
        base = _normalize_storage_key(raw_path)
        if not base:
            return []

        prefixes = _known_storage_prefixes()
        candidates: list[str] = []
        seen: set[str] = set()

        _append_unique(candidates, seen, base)
        queue = [base]

        while queue:
            current = queue.pop(0)
            for prefix in prefixes:
                stripped = _strip_prefix(current, prefix)
                normalized = _normalize_storage_key(stripped)
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    candidates.append(normalized)
                    queue.append(normalized)

        documents_folder = _normalize_storage_key(getattr(settings, "DOCUMENTS_FOLDER", "documents"))
        if documents_folder:
            marker = f"{documents_folder}/"
            for current in list(candidates):
                marker_index = current.find(marker)
                if marker_index > 0:
                    _append_unique(candidates, seen, current[marker_index:])

        for current in list(candidates):
            for prefix in prefixes:
                if not prefix:
                    continue
                prefixed = f"{prefix}/{current}"
                _append_unique(candidates, seen, prefixed)

        return candidates

    def _join_storage_key(*parts: str) -> str:
        normalized_parts = []
        for part in parts:
            normalized = _normalize_storage_key(part)
            if normalized:
                normalized_parts.append(normalized)
        return "/".join(normalized_parts)

    def _extract_file_name(value) -> str:
        if not value:
            return ""
        return _normalize_storage_key(getattr(value, "name", str(value)))

    def _resolve_path_hints(obj, field, current_path: str) -> list[str]:
        hints: list[str] = []
        seen: set[str] = set()

        def add_hint(path: str | None) -> None:
            normalized = _normalize_storage_key(path)
            if not normalized or normalized in seen:
                return
            seen.add(normalized)
            hints.append(normalized)

        current_name = _normalize_storage_key(current_path)
        add_hint(current_name)

        filename = os.path.basename(current_name) if current_name else ""
        file_extension = os.path.splitext(filename)[1] if filename else ""

        if filename:
            try:
                generated = field.generate_filename(obj, filename)
                add_hint(generated)
            except Exception:
                pass

        expected_dirs: set[str] = set()
        upload_folder = getattr(obj, "upload_folder", None)
        if upload_folder:
            expected_dirs.add(_normalize_storage_key(upload_folder))

        parent_application = getattr(obj, "doc_application", None)
        if parent_application is not None:
            parent_upload_folder = getattr(parent_application, "upload_folder", None)
            if parent_upload_folder:
                expected_dirs.add(_normalize_storage_key(parent_upload_folder))

        customer = getattr(obj, "customer", None)
        if customer is not None:
            customer_upload_folder = getattr(customer, "upload_folder", None)
            if customer_upload_folder:
                expected_dirs.add(_normalize_storage_key(customer_upload_folder))

        if filename:
            for expected_dir in expected_dirs:
                add_hint(_join_storage_key(expected_dir, filename))

        if file_extension and "passport" in str(field.name).lower():
            passport_filename = f"passport{file_extension}"
            for expected_dir in expected_dirs:
                add_hint(_join_storage_key(expected_dir, passport_filename))

        return hints

    def _find_existing_storage_key(
        raw_path: str | None,
        *,
        exists_cache: dict[str, bool],
        extra_hints: list[str] | None = None,
    ) -> str | None:
        candidates: list[str] = []
        seen: set[str] = set()

        for candidate in _candidate_storage_keys(raw_path):
            if candidate not in seen:
                seen.add(candidate)
                candidates.append(candidate)

        for hint in extra_hints or []:
            for candidate in _candidate_storage_keys(hint):
                if candidate not in seen:
                    seen.add(candidate)
                    candidates.append(candidate)

        for candidate in candidates:
            if candidate in exists_cache:
                exists = exists_cache[candidate]
            else:
                try:
                    exists = bool(default_storage.exists(candidate))
                except Exception:
                    exists = False
                exists_cache[candidate] = exists

            if exists:
                return candidate

        return None

    results = []
    exists_cache: dict[str, bool] = {}
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
                    file_value = getattr(obj, field_name)
                    current_path = _extract_file_name(file_value)
                    if not current_path:
                        continue

                    resolved_path = _find_existing_storage_key(
                        current_path,
                        exists_cache=exists_cache,
                        extra_hints=_resolve_path_hints(obj, field, current_path),
                    )
                    exists = bool(resolved_path)

                    path_for_url = resolved_path or current_path
                    try:
                        url = default_storage.url(path_for_url) if path_for_url else ""
                    except Exception as e:
                        url = f"ERROR: {str(e)}"
                    try:
                        abs_path = default_storage.path(path_for_url) if path_for_url else ""
                    except Exception:
                        abs_path = "N/A (not on local filesystem)"

                    # Check for file_link discrepancy if it exists on the model
                    file_link = getattr(obj, "file_link", None)
                    discrepancy = False
                    if file_link and url and not str(url).startswith("ERROR:") and file_link != url:
                        discrepancy = True
                    if resolved_path and resolved_path != current_path:
                        discrepancy = True

                    results.append(
                        {
                            "model": model._meta.label,
                            "id": obj.pk,
                            "field": field_name,
                            "path": current_path,
                            "resolved_path": resolved_path,
                            "abs_path": abs_path,
                            "exists": exists,
                            "url": url,
                            "file_link": file_link,
                            "discrepancy": discrepancy,
                        }
                    )
    return results


def repair_media_paths():
    """Repair DB file paths/file links by resolving existing storage object keys."""

    def _append_unique(values: list[str], seen: set[str], value: str | None) -> None:
        normalized = _normalize_storage_key(value)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        values.append(normalized)

    def _known_storage_prefixes() -> list[str]:
        prefixes: list[str] = []
        seen: set[str] = set()

        _append_unique(prefixes, seen, getattr(default_storage, "location", ""))

        media_url = urlparse(str(getattr(settings, "MEDIA_URL", "") or "")).path
        _append_unique(prefixes, seen, media_url)

        raw_media_root = str(getattr(settings, "MEDIA_ROOT", "") or "").replace("\\", "/").strip().strip("/")
        if raw_media_root:
            parts = [part for part in raw_media_root.split("/") if part]
            for depth in (1, 2, 3):
                if len(parts) >= depth:
                    _append_unique(prefixes, seen, "/".join(parts[-depth:]))

        return prefixes

    def _strip_prefix(path: str, prefix: str) -> str:
        if not prefix:
            return path
        if path == prefix:
            return ""
        prefixed = f"{prefix}/"
        if path.startswith(prefixed):
            return path[len(prefixed) :]
        return path

    def _normalize_storage_key(raw_path: str | None) -> str:
        if raw_path is None:
            return ""

        value = str(raw_path).strip().strip("'").strip('"')
        if not value:
            return ""

        parsed = urlparse(value)
        if parsed.scheme and parsed.netloc:
            value = parsed.path or ""
        else:
            value = value.split("?", 1)[0]

        value = unquote(value).replace("\\", "/")
        while "//" in value:
            value = value.replace("//", "/")

        media_root = str(getattr(settings, "MEDIA_ROOT", "") or "").replace("\\", "/").rstrip("/")
        if media_root and value.startswith(media_root):
            value = value[len(media_root) :]

        media_url_path = urlparse(str(getattr(settings, "MEDIA_URL", "") or "")).path.replace("\\", "/").strip()
        if media_url_path and value.startswith(media_url_path):
            value = value[len(media_url_path) :]

        return value.strip().strip("/")

    def _candidate_storage_keys(raw_path: str | None) -> list[str]:
        base = _normalize_storage_key(raw_path)
        if not base:
            return []

        prefixes = _known_storage_prefixes()
        candidates: list[str] = []
        seen: set[str] = set()

        _append_unique(candidates, seen, base)
        queue = [base]

        while queue:
            current = queue.pop(0)
            for prefix in prefixes:
                stripped = _strip_prefix(current, prefix)
                normalized = _normalize_storage_key(stripped)
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    candidates.append(normalized)
                    queue.append(normalized)

        documents_folder = _normalize_storage_key(getattr(settings, "DOCUMENTS_FOLDER", "documents"))
        if documents_folder:
            marker = f"{documents_folder}/"
            for current in list(candidates):
                marker_index = current.find(marker)
                if marker_index > 0:
                    _append_unique(candidates, seen, current[marker_index:])

        for current in list(candidates):
            for prefix in prefixes:
                if not prefix:
                    continue
                prefixed = f"{prefix}/{current}"
                _append_unique(candidates, seen, prefixed)

        return candidates

    def _join_storage_key(*parts: str) -> str:
        normalized_parts = []
        for part in parts:
            normalized = _normalize_storage_key(part)
            if normalized:
                normalized_parts.append(normalized)
        return "/".join(normalized_parts)

    def _extract_file_name(value) -> str:
        if not value:
            return ""
        return _normalize_storage_key(getattr(value, "name", str(value)))

    def _resolve_path_hints(obj, field, current_path: str) -> list[str]:
        hints: list[str] = []
        seen: set[str] = set()

        def add_hint(path: str | None) -> None:
            normalized = _normalize_storage_key(path)
            if not normalized or normalized in seen:
                return
            seen.add(normalized)
            hints.append(normalized)

        current_name = _normalize_storage_key(current_path)
        add_hint(current_name)

        filename = os.path.basename(current_name) if current_name else ""
        file_extension = os.path.splitext(filename)[1] if filename else ""

        if filename:
            try:
                generated = field.generate_filename(obj, filename)
                add_hint(generated)
            except Exception:
                pass

        expected_dirs: set[str] = set()
        upload_folder = getattr(obj, "upload_folder", None)
        if upload_folder:
            expected_dirs.add(_normalize_storage_key(upload_folder))

        parent_application = getattr(obj, "doc_application", None)
        if parent_application is not None:
            parent_upload_folder = getattr(parent_application, "upload_folder", None)
            if parent_upload_folder:
                expected_dirs.add(_normalize_storage_key(parent_upload_folder))

        customer = getattr(obj, "customer", None)
        if customer is not None:
            customer_upload_folder = getattr(customer, "upload_folder", None)
            if customer_upload_folder:
                expected_dirs.add(_normalize_storage_key(customer_upload_folder))

        if filename:
            for expected_dir in expected_dirs:
                add_hint(_join_storage_key(expected_dir, filename))

        if file_extension and "passport" in str(field.name).lower():
            passport_filename = f"passport{file_extension}"
            for expected_dir in expected_dirs:
                add_hint(_join_storage_key(expected_dir, passport_filename))

        return hints

    def _find_existing_storage_key(
        raw_path: str | None,
        *,
        exists_cache: dict[str, bool],
        extra_hints: list[str] | None = None,
    ) -> str | None:
        candidates: list[str] = []
        seen: set[str] = set()

        for candidate in _candidate_storage_keys(raw_path):
            if candidate not in seen:
                seen.add(candidate)
                candidates.append(candidate)

        for hint in extra_hints or []:
            for candidate in _candidate_storage_keys(hint):
                if candidate not in seen:
                    seen.add(candidate)
                    candidates.append(candidate)

        for candidate in candidates:
            if candidate in exists_cache:
                exists = exists_cache[candidate]
            else:
                try:
                    exists = bool(default_storage.exists(candidate))
                except Exception:
                    exists = False
                exists_cache[candidate] = exists

            if exists:
                return candidate

        return None

    repairs = []
    exists_cache: dict[str, bool] = {}
    for model in apps.get_models():
        for field in model._meta.get_fields():
            if isinstance(field, FileField):
                field_name = field.name
                try:
                    qs = model.objects.exclude(**{field_name: ""})
                except Exception:
                    continue
                for obj in qs:
                    file_value = getattr(obj, field_name)
                    current_path = _extract_file_name(file_value)
                    if not current_path:
                        continue

                    resolved_path = _find_existing_storage_key(
                        current_path,
                        exists_cache=exists_cache,
                        extra_hints=_resolve_path_hints(obj, field, current_path),
                    )
                    if not resolved_path:
                        continue

                    needs_path_update = resolved_path != current_path
                    has_file_link = hasattr(obj, "file_link")
                    needs_link_update = False
                    desired_file_link = None

                    if has_file_link:
                        try:
                            desired_file_link = default_storage.url(resolved_path)
                        except Exception:
                            desired_file_link = None
                        current_file_link = getattr(obj, "file_link", None)
                        needs_link_update = bool(desired_file_link and current_file_link != desired_file_link)

                    if not needs_path_update and not needs_link_update:
                        continue

                    update_fields: list[str] = []
                    old_path = current_path

                    if needs_path_update:
                        setattr(obj, field_name, resolved_path)
                        update_fields.append(field_name)
                    if needs_link_update and desired_file_link is not None:
                        obj.file_link = desired_file_link
                        update_fields.append("file_link")

                    if update_fields:
                        obj.save(update_fields=update_fields)
                        if needs_path_update and needs_link_update:
                            repairs.append(
                                f"Fixed {model._meta.label} #{obj.pk}: relinked {old_path} -> {resolved_path} and "
                                "refreshed file_link"
                            )
                        elif needs_path_update:
                            repairs.append(f"Fixed {model._meta.label} #{obj.pk}: relinked {old_path} -> {resolved_path}")
                        else:
                            repairs.append(
                                f"Fixed {model._meta.label} #{obj.pk}: refreshed file_link for {resolved_path}"
                            )

    return repairs


def get_cache_health_status(user_id: int | None = None) -> dict:
    """
    Run a live cache probe against the configured default cache backend.

    The probe performs:
    - Redis ping (when Redis is configured as the default cache backend)
    - Write/read/delete round-trip against Django cache backend
    """
    default_cache = caches["default"]
    cache_settings = settings.CACHES.get("default", {})
    backend_path = cache_settings.get("BACKEND", "")
    location = str(cache_settings.get("LOCATION", ""))
    checked_at = timezone.now().isoformat()

    redis_configured = "redis" in backend_path.lower() or location.startswith("redis://")
    redis_connected = None
    errors: list[str] = []

    if redis_configured:
        if get_redis_connection is None:
            redis_connected = False
            errors.append("django-redis connection helper is unavailable.")
        else:
            try:
                redis_connected = bool(get_redis_connection("default").ping())
            except Exception as exc:
                redis_connected = False
                errors.append(f"Redis ping failed: {exc}")

    probe_key = f"cache-health:{uuid.uuid4().hex}"
    probe_value = uuid.uuid4().hex
    probe_latency_ms = 0.0
    user_cache_enabled = True
    probe_skipped = False
    if user_id is not None:
        try:
            from cache.namespace import namespace_manager

            user_cache_enabled = namespace_manager.is_cache_enabled(int(user_id))
        except Exception as exc:
            errors.append(f"Failed to read user cache status: {exc}")

    write_read_delete_ok = False
    probe_skipped = not user_cache_enabled
    if not probe_skipped:
        start = time.perf_counter()
        try:
            default_cache.set(probe_key, probe_value, timeout=30)
            cached_value = default_cache.get(probe_key)
            write_read_delete_ok = cached_value == probe_value
            if not write_read_delete_ok:
                errors.append("Cache probe value mismatch after read.")
        except Exception as exc:
            errors.append(f"Cache write/read probe failed: {exc}")
        finally:
            probe_latency_ms = round((time.perf_counter() - start) * 1000, 2)
            try:
                default_cache.delete(probe_key)
            except Exception as exc:
                errors.append(f"Cache probe cleanup failed: {exc}")

    if probe_skipped:
        if redis_connected is False:
            ok = False
            message = "Cache is disabled for your user. Redis connectivity check failed."
        else:
            ok = True
            message = (
                "Cache is disabled for your user. Backend connectivity is healthy; write/read/delete probe was skipped."
            )
    else:
        ok = write_read_delete_ok and (redis_connected is not False)
        if ok:
            message = "Cache probe succeeded."
        elif not write_read_delete_ok:
            message = "Cache probe failed."
        else:
            message = "Redis ping failed."

    return {
        "ok": ok,
        "message": message,
        "checkedAt": checked_at,
        "cacheBackend": backend_path,
        "cacheLocation": location,
        "redisConfigured": redis_configured,
        "redisConnected": redis_connected,
        "userCacheEnabled": user_cache_enabled,
        "probeSkipped": probe_skipped,
        "writeReadDeleteOk": write_read_delete_ok,
        "probeLatencyMs": probe_latency_ms,
        "errors": errors,
    }
