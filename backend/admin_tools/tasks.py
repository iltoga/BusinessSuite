from __future__ import annotations

from admin_tools import services
from core.services.logger_service import Logger
from core.services.redis_streams import publish_stream_event, stream_user_key
from core.tasks.runtime import QUEUE_LOW, db_task

logger = Logger.get_logger(__name__)


def _publish_user_event(
    user_id: int,
    *,
    event: str,
    status: str,
    payload: dict,
) -> None:
    publish_stream_event(
        stream_user_key(user_id),
        event=event,
        status=status,
        payload=payload,
        user_id=str(user_id),
    )


@db_task(queue=QUEUE_LOW)
def run_backup_stream(*, user_id: int, include_users: bool = False) -> None:
    _publish_user_event(user_id, event="backup_started", status="info", payload={"message": "Backup started"})

    finished = False
    try:
        for msg in services.backup_all(include_users=include_users):
            if msg.startswith("RESULT_PATH:"):
                path = msg.split(":", 1)[1]
                _publish_user_event(
                    user_id,
                    event="backup_finished",
                    status="success",
                    payload={"message": f"Backup finished: {path}", "resultPath": path, "_terminal": True},
                )
                finished = True
                continue

            _publish_user_event(user_id, event="backup_message", status="info", payload={"message": msg})

        if not finished:
            _publish_user_event(
                user_id,
                event="backup_finished",
                status="success",
                payload={"message": "Backup finished", "_terminal": True},
            )
    except Exception as exc:
        logger.exception("Backup stream failed for user=%s", user_id)
        _publish_user_event(
            user_id,
            event="backup_failed",
            status="error",
            payload={"message": f"Error: {exc}", "error": str(exc), "_terminal": True},
        )


@db_task(queue=QUEUE_LOW)
def run_restore_stream(*, user_id: int, archive_path: str, include_users: bool = False) -> None:
    _publish_user_event(user_id, event="restore_started", status="info", payload={"message": "Restore started"})

    try:
        for msg in services.restore_from_file(archive_path, include_users=include_users):
            if msg.startswith("PROGRESS:"):
                progress = msg.split(":", 1)[1]
                _publish_user_event(
                    user_id,
                    event="restore_progress",
                    status="info",
                    payload={"progress": progress},
                )
                continue

            _publish_user_event(user_id, event="restore_message", status="info", payload={"message": msg})

        _publish_user_event(
            user_id,
            event="restore_finished",
            status="success",
            payload={"message": "Restore finished", "_terminal": True},
        )
    except Exception as exc:
        logger.exception("Restore stream failed for user=%s", user_id)
        _publish_user_event(
            user_id,
            event="restore_failed",
            status="error",
            payload={"message": f"Error: {exc}", "error": str(exc), "_terminal": True},
        )


@db_task(queue=QUEUE_LOW)
def run_media_cleanup_stream(*, user_id: int, dry_run: bool = True) -> None:
    def emit(payload: dict) -> None:
        event_name = str(payload.get("event") or "media_cleanup_progress")
        status = "error" if event_name == "media_cleanup_failed" else "info"
        is_terminal = event_name in {"media_cleanup_finished", "media_cleanup_failed"}
        _publish_user_event(
            user_id,
            event=event_name,
            status=status,
            payload={
                **payload,
                **({"_terminal": True} if is_terminal else {}),
            },
        )

    try:
        services.cleanup_unlinked_media_files(dry_run=dry_run, progress_callback=emit)
    except Exception as exc:
        logger.exception("Media cleanup stream failed for user=%s", user_id)
        emit(
            {
                "event": "media_cleanup_failed",
                "message": f"Error: {exc}",
                "error": str(exc),
            }
        )
