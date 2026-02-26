from __future__ import annotations

import base64
import contextlib
import contextvars
import hashlib
import json
import os
import socket
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID

from core.models.local_resilience import MediaManifestEntry, SyncChangeLog, SyncConflict
from django.apps import apps
from django.conf import settings
from django.core.files.storage import default_storage
from django.db import models
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime, parse_time

_SYNC_APPLY_IN_PROGRESS = contextvars.ContextVar("sync_apply_in_progress", default=False)


def get_local_node_id() -> str:
    value = (getattr(settings, "LOCAL_SYNC_NODE_ID", "") or "").strip()
    if value:
        return value
    return socket.gethostname() or "unknown-node"


def is_sync_apply_in_progress() -> bool:
    return bool(_SYNC_APPLY_IN_PROGRESS.get())


@contextlib.contextmanager
def sync_apply_context():
    token = _SYNC_APPLY_IN_PROGRESS.set(True)
    try:
        yield
    finally:
        _SYNC_APPLY_IN_PROGRESS.reset(token)


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return str(value)


def _payload_checksum(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _serialize_instance(instance: models.Model) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for field in instance._meta.concrete_fields:
        key = field.attname if field.many_to_one else field.name
        payload[key] = _json_safe(getattr(instance, key))
    return payload


def _coerce_field_value(field: models.Field, raw_value: Any) -> Any:
    if raw_value is None:
        return None

    if isinstance(field, models.DateTimeField) and isinstance(raw_value, str):
        parsed = parse_datetime(raw_value)
        return parsed if parsed is not None else raw_value

    if isinstance(field, models.DateField) and isinstance(raw_value, str):
        parsed = parse_date(raw_value)
        return parsed if parsed is not None else raw_value

    if isinstance(field, models.TimeField) and isinstance(raw_value, str):
        parsed = parse_time(raw_value)
        return parsed if parsed is not None else raw_value

    if isinstance(field, models.BooleanField):
        if isinstance(raw_value, str):
            lowered = raw_value.strip().lower()
            if lowered in {"1", "true", "yes", "on"}:
                return True
            if lowered in {"0", "false", "no", "off"}:
                return False
        return bool(raw_value)

    if isinstance(field, (models.IntegerField, models.BigIntegerField, models.PositiveIntegerField)):
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            return raw_value

    if isinstance(field, models.FloatField):
        try:
            return float(raw_value)
        except (TypeError, ValueError):
            return raw_value

    if isinstance(field, models.DecimalField):
        try:
            return Decimal(str(raw_value))
        except Exception:
            return raw_value

    if isinstance(field, models.UUIDField):
        try:
            return UUID(str(raw_value))
        except Exception:
            return raw_value

    return raw_value


def capture_model_upsert(instance: models.Model, *, source_node: str | None = None) -> SyncChangeLog | None:
    if not getattr(instance, "pk", None):
        return None

    payload = _serialize_instance(instance)
    source = source_node or get_local_node_id()
    timestamp_raw = payload.get("updated_at")
    timestamp = parse_datetime(str(timestamp_raw)) if isinstance(timestamp_raw, str) else None
    if timestamp is None:
        timestamp = timezone.now()

    record = {
        "model_label": instance._meta.label_lower,
        "object_pk": str(instance.pk),
        "operation": SyncChangeLog.OP_UPSERT,
        "payload": payload,
        "source_node": source,
        "source_timestamp": timestamp,
    }
    record["checksum"] = _payload_checksum(
        {
            "model_label": record["model_label"],
            "object_pk": record["object_pk"],
            "operation": record["operation"],
            "payload": payload,
            "source_timestamp": timestamp.isoformat(),
            "source_node": source,
        }
    )
    return SyncChangeLog.objects.create(**record)


def capture_model_delete(model_label: str, object_pk: Any, *, source_node: str | None = None) -> SyncChangeLog:
    source = source_node or get_local_node_id()
    payload = {
        "deleted": True,
        "model_label": model_label,
        "object_pk": str(object_pk),
    }
    timestamp = timezone.now()
    checksum = _payload_checksum(
        {
            "model_label": model_label,
            "object_pk": str(object_pk),
            "operation": SyncChangeLog.OP_DELETE,
            "payload": payload,
            "source_timestamp": timestamp.isoformat(),
            "source_node": source,
        }
    )
    return SyncChangeLog.objects.create(
        source_node=source,
        model_label=model_label,
        object_pk=str(object_pk),
        operation=SyncChangeLog.OP_DELETE,
        payload=payload,
        source_timestamp=timestamp,
        checksum=checksum,
    )


def _resolve_model(model_label: str):
    if not model_label or "." not in model_label:
        return None
    app_label, model_name = model_label.split(".", 1)
    try:
        return apps.get_model(app_label, model_name)
    except LookupError:
        return None


def _resolve_incoming_ts(raw_change: dict[str, Any]) -> datetime:
    raw_value = raw_change.get("source_timestamp") or raw_change.get("sourceTimestamp")
    if isinstance(raw_value, str):
        parsed = parse_datetime(raw_value)
        if parsed is not None:
            return parsed

    payload = raw_change.get("payload") or {}
    if isinstance(payload, dict):
        payload_ts = payload.get("updated_at")
        if isinstance(payload_ts, str):
            parsed = parse_datetime(payload_ts)
            if parsed is not None:
                return parsed

    return timezone.now()


def apply_change(raw_change: dict[str, Any], *, source_node: str) -> dict[str, Any]:
    model_label = str(raw_change.get("model_label") or raw_change.get("modelLabel") or "").strip().lower()
    object_pk = str(raw_change.get("object_pk") or raw_change.get("objectPk") or "").strip()
    operation = str(raw_change.get("operation") or SyncChangeLog.OP_UPSERT).strip().lower()
    payload = raw_change.get("payload") if isinstance(raw_change.get("payload"), dict) else {}
    incoming_ts = _resolve_incoming_ts(raw_change)

    if not model_label or not object_pk:
        return {"applied": False, "reason": "invalid_change"}

    model = _resolve_model(model_label)
    if model is None:
        return {"applied": False, "reason": "unknown_model", "modelLabel": model_label}

    try:
        existing = model._default_manager.filter(pk=object_pk).first()
        existing_updated = getattr(existing, "updated_at", None) if existing is not None else None

        if existing is not None and isinstance(existing_updated, datetime) and existing_updated > incoming_ts:
            existing_snapshot = _serialize_instance(existing)
            SyncConflict.objects.create(
                model_label=model_label,
                object_pk=object_pk,
                incoming_change=_json_safe(raw_change),
                existing_snapshot=existing_snapshot,
                chosen_source="existing",
                reason="incoming_older_than_existing",
            )
            return {"applied": False, "conflict": True, "reason": "incoming_older_than_existing"}

        if operation == SyncChangeLog.OP_DELETE:
            if existing is not None:
                with sync_apply_context():
                    existing.delete()
            return {"applied": True, "operation": operation}

        if not isinstance(payload, dict):
            return {"applied": False, "reason": "invalid_payload"}

        instance = existing if existing is not None else model()
        if existing is None and object_pk:
            pk_field = model._meta.pk
            setattr(instance, pk_field.attname, _coerce_field_value(pk_field, object_pk))

        for field in model._meta.concrete_fields:
            if getattr(field, "auto_created", False):
                continue

            storage_key = field.attname if field.many_to_one else field.name
            if storage_key == field.attname and field.primary_key and existing is not None:
                continue
            if storage_key not in payload:
                continue

            coerced = _coerce_field_value(field, payload.get(storage_key))
            setattr(instance, storage_key, coerced)

        with sync_apply_context():
            instance._sync_skip_capture = True
            instance.save()
            instance._sync_skip_capture = False
            if "updated_at" in payload:
                try:
                    updated_at_field = instance._meta.get_field("updated_at")
                    forced_updated_at = _coerce_field_value(updated_at_field, payload.get("updated_at"))
                    if isinstance(forced_updated_at, datetime):
                        model._default_manager.filter(pk=instance.pk).update(updated_at=forced_updated_at)
                except Exception:
                    pass

        return {"applied": True, "operation": SyncChangeLog.OP_UPSERT}
    except Exception as exc:
        return {"applied": False, "reason": f"apply_error:{type(exc).__name__}"}


def ingest_remote_changes(*, source_node: str, changes: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = 0
    skipped = 0
    conflicts = 0
    last_seq = 0

    for change in changes:
        if not isinstance(change, dict):
            skipped += 1
            continue

        model_label = str(change.get("model_label") or change.get("modelLabel") or "").strip().lower()
        object_pk = str(change.get("object_pk") or change.get("objectPk") or "").strip()
        operation = str(change.get("operation") or SyncChangeLog.OP_UPSERT).strip().lower()
        payload = change.get("payload") if isinstance(change.get("payload"), dict) else {}
        incoming_ts = _resolve_incoming_ts(change)
        checksum = str(change.get("checksum") or "").strip()
        if not checksum:
            checksum = _payload_checksum(
                {
                    "model_label": model_label,
                    "object_pk": object_pk,
                    "operation": operation,
                    "payload": payload,
                    "source_timestamp": incoming_ts.isoformat(),
                    "source_node": source_node,
                }
            )

        existing_log = SyncChangeLog.objects.filter(source_node=source_node, checksum=checksum).first()
        if existing_log is not None:
            skipped += 1
            continue

        apply_result = apply_change(change, source_node=source_node)
        applied = bool(apply_result.get("applied"))
        if apply_result.get("conflict"):
            conflicts += 1

        new_log = SyncChangeLog.objects.create(
            source_node=source_node,
            model_label=model_label,
            object_pk=object_pk,
            operation=operation,
            payload=_json_safe(payload if isinstance(payload, dict) else {}),
            source_timestamp=incoming_ts,
            checksum=checksum,
            applied=applied,
        )
        last_seq = max(last_seq, int(new_log.seq))

        if applied:
            accepted += 1
        else:
            skipped += 1

    return {
        "accepted": accepted,
        "skipped": skipped,
        "conflicts": conflicts,
        "lastSeq": last_seq,
    }


def pull_changes(*, after_seq: int, limit: int = 200) -> list[dict[str, Any]]:
    queryset = SyncChangeLog.objects.filter(seq__gt=max(0, int(after_seq))).order_by("seq")[: max(1, int(limit))]
    result: list[dict[str, Any]] = []
    for row in queryset:
        result.append(
            {
                "seq": int(row.seq),
                "source_node": row.source_node,
                "model_label": row.model_label,
                "object_pk": row.object_pk,
                "operation": row.operation,
                "payload": row.payload,
                "source_timestamp": row.source_timestamp.isoformat(),
                "checksum": row.checksum,
                "applied": bool(row.applied),
            }
        )
    return result


def _iter_local_media_paths() -> list[str]:
    media_root = str(getattr(settings, "MEDIA_ROOT", "") or "")
    if not media_root or not os.path.isdir(media_root):
        return []

    paths: list[str] = []
    for root, _dirs, filenames in os.walk(media_root):
        for filename in filenames:
            absolute_path = os.path.join(root, filename)
            rel_path = os.path.relpath(absolute_path, media_root)
            if rel_path.startswith(".."):
                continue
            paths.append(rel_path.replace("\\", "/"))
    return paths


def _checksum_for_storage_path(path: str, *, absolute_path: str | None = None) -> str:
    digest = hashlib.sha256()
    if absolute_path and os.path.exists(absolute_path):
        with open(absolute_path, "rb") as file_handle:
            for chunk in iter(lambda: file_handle.read(64 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    with default_storage.open(path, "rb") as file_handle:
        for chunk in file_handle.chunks():
            digest.update(chunk)
    return digest.hexdigest()


def refresh_media_manifest(*, source_node: str | None = None) -> int:
    source = source_node or get_local_node_id()
    storage_backend = f"{default_storage.__class__.__module__}.{default_storage.__class__.__name__}"
    encrypted = bool(getattr(settings, "LOCAL_MEDIA_ENCRYPTION_ENABLED", False))
    updated = 0
    media_root = str(getattr(settings, "MEDIA_ROOT", "") or "")

    for path in _iter_local_media_paths():
        try:
            absolute_path = os.path.join(media_root, path) if media_root else None
            checksum = _checksum_for_storage_path(path, absolute_path=absolute_path)
            if absolute_path and os.path.exists(absolute_path):
                size = int(os.path.getsize(absolute_path))
                modified_at = datetime.fromtimestamp(
                    os.path.getmtime(absolute_path), tz=timezone.get_current_timezone()
                )
            else:
                size = int(default_storage.size(path))
                modified_at = default_storage.get_modified_time(path)
            if timezone.is_naive(modified_at):
                modified_at = timezone.make_aware(modified_at, timezone.get_current_timezone())

            entry, created = MediaManifestEntry.objects.get_or_create(
                path=path,
                defaults={
                    "checksum": checksum,
                    "size": size,
                    "modified_at": modified_at,
                    "encrypted": encrypted,
                    "storage_backend": storage_backend,
                    "source_node": source,
                },
            )
            if created:
                updated += 1
                continue

            if (
                entry.checksum == checksum
                and int(entry.size) == size
                and entry.modified_at == modified_at
                and bool(entry.encrypted) == encrypted
                and entry.storage_backend == storage_backend
                and entry.source_node == source
            ):
                continue

            entry.checksum = checksum
            entry.size = size
            entry.modified_at = modified_at
            entry.encrypted = encrypted
            entry.storage_backend = storage_backend
            entry.source_node = source
            entry.save(
                update_fields=[
                    "checksum",
                    "size",
                    "modified_at",
                    "encrypted",
                    "storage_backend",
                    "source_node",
                    "updated_at",
                ]
            )
            updated += 1
        except Exception:
            continue

    return updated


def get_media_manifest(*, after_updated_at: datetime | None = None, limit: int = 500) -> list[dict[str, Any]]:
    queryset = MediaManifestEntry.objects.all().order_by("updated_at", "path")
    if after_updated_at is not None:
        queryset = queryset.filter(updated_at__gt=after_updated_at)
    queryset = queryset[: max(1, int(limit))]

    return [
        {
            "path": row.path,
            "checksum": row.checksum,
            "size": int(row.size),
            "modified_at": row.modified_at.isoformat() if row.modified_at else None,
            "encrypted": bool(row.encrypted),
            "storage_backend": row.storage_backend,
            "source_node": row.source_node,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        for row in queryset
    ]


def fetch_media_entries(
    *, paths: list[str], include_content: bool = False, content_size_limit: int = 5_000_000
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for raw_path in paths:
        path = str(raw_path or "").strip().lstrip("/")
        if not path:
            continue

        exists = default_storage.exists(path)
        if not exists:
            items.append({"path": path, "exists": False})
            continue

        entry: dict[str, Any] = {
            "path": path,
            "exists": True,
            "size": int(default_storage.size(path)),
            "url": default_storage.url(path),
        }

        if include_content and entry["size"] <= int(content_size_limit):
            try:
                with default_storage.open(path, "rb") as file_handle:
                    entry["content_base64"] = base64.b64encode(file_handle.read()).decode("ascii")
            except Exception:
                entry["content_base64"] = ""

        items.append(entry)
    return items


def bootstrap_snapshot(*, force: bool = False, source_node: str | None = None) -> dict[str, int | str]:
    """
    Capture a full upsert snapshot for tracked models into SyncChangeLog.

    This is intended for first-time local-first bootstrap so replicas can clone
    the complete dataset even if change capture started after data already existed.
    """
    if not force and SyncChangeLog.objects.exists():
        return {"created": 0, "scanned": 0, "reason": "changelog_already_exists"}

    # Imported lazily to avoid import cycle at module import time.
    from core.sync_signals import TRACKED_MODELS

    source = source_node or get_local_node_id()
    created = 0
    scanned = 0

    for app_label, model_name in TRACKED_MODELS:
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:
            continue

        queryset = model._default_manager.all().order_by(model._meta.pk.name)
        for instance in queryset.iterator(chunk_size=500):
            scanned += 1
            if capture_model_upsert(instance, source_node=source) is not None:
                created += 1

    return {"created": created, "scanned": scanned}
