from __future__ import annotations

from typing import Any


def persist_progress(
    instance,
    *,
    progress: int | None = None,
    status: str | None = None,
    min_delta: int = 5,
    force: bool = False,
    extra_fields: dict[str, Any] | None = None,
) -> bool:
    update_fields: list[str] = []
    current_progress = int(getattr(instance, "progress", 0) or 0)
    current_status = getattr(instance, "status", None)
    status_changed = status is not None and status != current_status

    if status_changed:
        instance.status = status
        update_fields.append("status")

    if progress is not None:
        target_progress = int(progress)
        progress_changed = target_progress != current_progress
        should_persist = (
            force
            or status_changed
            or (progress_changed and abs(target_progress - current_progress) >= max(1, int(min_delta or 1)))
        )
        if should_persist and progress_changed:
            instance.progress = target_progress
            update_fields.append("progress")

    for field_name, field_value in (extra_fields or {}).items():
        if getattr(instance, field_name, None) != field_value:
            setattr(instance, field_name, field_value)
            update_fields.append(field_name)

    if not update_fields:
        return False

    if "updated_at" not in update_fields:
        update_fields.append("updated_at")
    instance.save(update_fields=list(dict.fromkeys(update_fields)))
    return True
