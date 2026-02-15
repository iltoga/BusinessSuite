import logging

from core.models.calendar_event import CalendarEvent
from core.utils.google_client import GoogleClient
from django.utils import timezone
from huey.contrib.djhuey import db_task

logger = logging.getLogger(__name__)

CALENDAR_SYNC_MAX_RETRIES = 3
CALENDAR_SYNC_RETRY_DELAY_SECONDS = 15


def _is_google_not_found_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "404" in message and "not found" in message


def _is_retryable_google_error(exc: Exception) -> bool:
    if _is_google_not_found_error(exc):
        return False
    message = str(exc).lower()
    return "google calendar" in message or "httperror" in message or "failed to initialize google client" in message


def _create_missing_remote_event(*, client: GoogleClient, event: CalendarEvent, payload: dict, reason: str):
    logger.error(
        "calendar_remote_event_missing_local_present event_id=%s google_event_id=%s calendar_id=%s reason=%s",
        event.pk,
        event.google_event_id,
        _calendar_id_for_event(event),
        reason,
    )
    remote_event = client.create_event(
        payload,
        calendar_id=_calendar_id_for_event(event),
    )
    logger.debug(
        "calendar_remote_event_recreated event_id=%s old_google_event_id=%s new_google_event_id=%s",
        event.pk,
        event.google_event_id,
        remote_event.get("id"),
    )
    return remote_event


def _google_payload_from_event(event: CalendarEvent) -> dict:
    payload = {
        "summary": event.title,
        "description": event.description or "",
        "reminders": event.notifications or {},
        "extended_properties": event.extended_properties or {},
        "attendees": event.attendees or [],
    }
    if event.color_id:
        payload["color_id"] = event.color_id

    if event.start_date and event.end_date:
        payload["start_date"] = event.start_date.isoformat()
        payload["end_date"] = event.end_date.isoformat()
    else:
        payload["start_time"] = event.start_time
        payload["end_time"] = event.end_time

    return payload


def _calendar_id_for_event(event: CalendarEvent) -> str | None:
    return event.google_calendar_id or None


def _resolve_google_event_id_for_update(client: GoogleClient, event: CalendarEvent) -> str | None:
    if event.google_event_id:
        return event.google_event_id

    try:
        private_props = (event.extended_properties or {}).get("private") or {}
        application_id = private_props.get("revisbali_customer_application_id")
        if not application_id:
            return None

        candidates = client.list_events(
            calendar_id=_calendar_id_for_event(event),
            max_results=250,
            include_past=True,
            fetch_all=True,
            private_extended_property=f"revisbali_customer_application_id={application_id}",
        )

        if not candidates:
            return None

        expected_summary = (event.title or "").strip()
        expected_start_date = event.start_date.isoformat() if event.start_date else None

        for candidate in candidates:
            candidate_id = candidate.get("id")
            if not candidate_id:
                continue

            if expected_summary and (candidate.get("summary") or "").strip() != expected_summary:
                continue

            if expected_start_date:
                candidate_start = (candidate.get("start") or {}).get("date")
                if candidate_start != expected_start_date:
                    continue

            return candidate_id

        return candidates[0].get("id")
    except Exception as exc:
        logger.error(
            "calendar_update_sync_resolve_existing_failed event_id=%s error_type=%s error=%s",
            event.pk,
            type(exc).__name__,
            str(exc),
        )
        return None


@db_task(retries=CALENDAR_SYNC_MAX_RETRIES, retry_delay=CALENDAR_SYNC_RETRY_DELAY_SECONDS, context=True)
def create_google_event_task(event_id: str, task=None):
    event = CalendarEvent.objects.filter(pk=event_id).first()
    if not event:
        logger.error("calendar_create_sync_missing_event event_id=%s", event_id)
        return {"status": "skipped", "reason": "event_missing"}

    try:
        client = GoogleClient()
        payload = _google_payload_from_event(event)
        logger.debug(
            "calendar_create_sync_start event_id=%s google_event_id=%s calendar_id=%s",
            event_id,
            event.google_event_id,
            _calendar_id_for_event(event),
        )
        if event.google_event_id:
            try:
                remote_event = client.update_event(
                    event_id=event.google_event_id,
                    data=payload,
                    calendar_id=_calendar_id_for_event(event),
                )
            except Exception as exc:
                if not _is_google_not_found_error(exc):
                    raise
                remote_event = _create_missing_remote_event(
                    client=client,
                    event=event,
                    payload=payload,
                    reason="create_task_update_target_missing",
                )
        else:
            remote_event = client.create_event(
                payload,
                calendar_id=_calendar_id_for_event(event),
            )
        CalendarEvent.objects.filter(pk=event_id).update(
            google_event_id=remote_event.get("id") or event.google_event_id,
            sync_status=CalendarEvent.SYNC_STATUS_SYNCED,
            sync_error="",
            last_synced_at=timezone.now(),
            updated_at=timezone.now(),
        )
        logger.debug(
            "calendar_create_sync_success event_id=%s google_event_id=%s",
            event_id,
            remote_event.get("id") or event.google_event_id,
        )
        return {"status": "ok", "google_event_id": remote_event.get("id")}
    except Exception as exc:
        if task and task.retries > 0 and _is_retryable_google_error(exc):
            logger.error(
                "calendar_create_sync_retrying event_id=%s retries_left=%s error_type=%s error=%s",
                event_id,
                task.retries,
                type(exc).__name__,
                str(exc),
            )
            raise
        logger.error(
            "calendar_create_sync_failed_after_retries event_id=%s error_type=%s error=%s",
            event_id,
            type(exc).__name__,
            str(exc),
        )
        CalendarEvent.objects.filter(pk=event_id).update(
            sync_status=CalendarEvent.SYNC_STATUS_FAILED,
            sync_error=str(exc),
            updated_at=timezone.now(),
        )
        return {"status": "failed", "error": str(exc)}


@db_task(retries=CALENDAR_SYNC_MAX_RETRIES, retry_delay=CALENDAR_SYNC_RETRY_DELAY_SECONDS, context=True)
def update_google_event_task(event_id: str, task=None):
    event = CalendarEvent.objects.filter(pk=event_id).first()
    if not event:
        logger.error("calendar_update_sync_missing_event event_id=%s", event_id)
        return {"status": "skipped", "reason": "event_missing"}

    try:
        client = GoogleClient()
        payload = _google_payload_from_event(event)
        logger.debug(
            "calendar_update_sync_start event_id=%s google_event_id=%s calendar_id=%s",
            event_id,
            event.google_event_id,
            _calendar_id_for_event(event),
        )
        target_google_event_id = _resolve_google_event_id_for_update(client, event)
        if not target_google_event_id:
            logger.error(
                "calendar_update_sync_missing_google_event_id event_id=%s",
                event_id,
            )
            remote_event = _create_missing_remote_event(
                client=client,
                event=event,
                payload=payload,
                reason="update_task_google_event_id_unresolved",
            )
            target_google_event_id = remote_event.get("id") or event.google_event_id
        else:
            try:
                remote_event = client.update_event(
                    event_id=target_google_event_id,
                    data=payload,
                    calendar_id=_calendar_id_for_event(event),
                )
            except Exception as exc:
                if not _is_google_not_found_error(exc):
                    raise
                remote_event = _create_missing_remote_event(
                    client=client,
                    event=event,
                    payload=payload,
                    reason="update_task_update_target_missing",
                )
                target_google_event_id = remote_event.get("id") or target_google_event_id

        CalendarEvent.objects.filter(pk=event_id).update(
            google_event_id=remote_event.get("id") or target_google_event_id,
            sync_status=CalendarEvent.SYNC_STATUS_SYNCED,
            sync_error="",
            last_synced_at=timezone.now(),
            updated_at=timezone.now(),
        )
        logger.debug(
            "calendar_update_sync_success event_id=%s google_event_id=%s",
            event_id,
            remote_event.get("id") or target_google_event_id,
        )
        return {"status": "ok", "google_event_id": remote_event.get("id")}
    except Exception as exc:
        if task and task.retries > 0 and _is_retryable_google_error(exc):
            logger.error(
                "calendar_update_sync_retrying event_id=%s retries_left=%s error_type=%s error=%s",
                event_id,
                task.retries,
                type(exc).__name__,
                str(exc),
            )
            raise
        logger.error(
            "calendar_update_sync_failed_after_retries event_id=%s google_event_id=%s error_type=%s error=%s",
            event_id,
            event.google_event_id,
            type(exc).__name__,
            str(exc),
        )
        CalendarEvent.objects.filter(pk=event_id).update(
            sync_status=CalendarEvent.SYNC_STATUS_FAILED,
            sync_error=str(exc),
            updated_at=timezone.now(),
        )
        return {"status": "failed", "error": str(exc)}


@db_task(retries=CALENDAR_SYNC_MAX_RETRIES, retry_delay=CALENDAR_SYNC_RETRY_DELAY_SECONDS, context=True)
def delete_google_event_task(google_event_id: str, google_calendar_id: str | None = None, task=None):
    if not google_event_id:
        logger.error("calendar_delete_sync_missing_google_event_id google_event_id=%s", google_event_id)
        return {"status": "skipped", "reason": "google_event_id_missing"}

    try:
        logger.debug(
            "calendar_delete_sync_start google_event_id=%s calendar_id=%s",
            google_event_id,
            google_calendar_id,
        )
        if google_calendar_id:
            GoogleClient().delete_event(event_id=google_event_id, calendar_id=google_calendar_id)
        else:
            GoogleClient().delete_event(event_id=google_event_id)
        logger.debug(
            "calendar_delete_sync_success google_event_id=%s calendar_id=%s",
            google_event_id,
            google_calendar_id,
        )
        return {
            "status": "ok",
            "google_event_id": google_event_id,
            "google_calendar_id": google_calendar_id,
        }
    except Exception as exc:
        if _is_google_not_found_error(exc):
            logger.error(
                "calendar_delete_sync_missing_remote_event google_event_id=%s calendar_id=%s error=%s",
                google_event_id,
                google_calendar_id,
                str(exc),
            )
            return {
                "status": "ok",
                "google_event_id": google_event_id,
                "google_calendar_id": google_calendar_id,
                "reason": "remote_event_already_missing",
            }
        if task and task.retries > 0 and _is_retryable_google_error(exc):
            logger.error(
                "calendar_delete_sync_retrying google_event_id=%s calendar_id=%s retries_left=%s error_type=%s error=%s",
                google_event_id,
                google_calendar_id,
                task.retries,
                type(exc).__name__,
                str(exc),
            )
            raise
        logger.error(
            "calendar_delete_sync_failed_after_retries google_event_id=%s error_type=%s error=%s",
            google_event_id,
            type(exc).__name__,
            str(exc),
        )
        return {"status": "failed", "error": str(exc)}
