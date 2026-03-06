import logging

from core.models.calendar_event import CalendarEvent
from core.utils.google_client import GoogleClient
from django.utils import timezone
from core.tasks.runtime import QUEUE_DEFAULT, db_task

logger = logging.getLogger(__name__)

CALENDAR_SYNC_MAX_RETRIES = 3
CALENDAR_SYNC_RETRY_DELAY_SECONDS = 15
LOCAL_EVENT_ID_PRIVATE_PROP = "revisbali_calendar_event_id"
APPLICATION_ID_PRIVATE_PROP = "revisbali_customer_application_id"
TASK_ID_PRIVATE_PROP = "revisbali_task_id"
EVENT_KIND_PRIVATE_PROP = "revisbali_event_kind"


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


def _private_properties_for_sync(*, local_event_id: str | None = None, extended_properties: dict | None = None) -> dict[str, str]:
    private_props = dict(((extended_properties or {}).get("private") or {}))
    if local_event_id:
        private_props.setdefault(LOCAL_EVENT_ID_PRIVATE_PROP, str(local_event_id))
    return {str(key): str(value) for key, value in private_props.items() if value not in (None, "")}


def _extended_properties_for_sync(*, local_event_id: str, extended_properties: dict | None) -> dict:
    merged = dict(extended_properties or {})
    merged["private"] = _private_properties_for_sync(
        local_event_id=local_event_id,
        extended_properties=extended_properties,
    )
    return merged


def _google_payload_from_event(event: CalendarEvent) -> dict:
    payload = {
        "summary": event.title,
        "description": event.description or "",
        "reminders": event.notifications or {},
        "extended_properties": _extended_properties_for_sync(
            local_event_id=event.pk,
            extended_properties=event.extended_properties,
        ),
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


def _remote_event_start_date(candidate: dict) -> str | None:
    start = candidate.get("start") or {}
    return start.get("date") or ((start.get("dateTime") or "")[:10] or None)


def _select_remote_event_candidate(
    candidates: list[dict],
    *,
    private_props: dict[str, str],
    title: str,
    start_date: str | None,
    strict_match: bool,
):
    normalized_title = (title or "").strip()
    expected_task_id = private_props.get(TASK_ID_PRIVATE_PROP)
    expected_event_kind = private_props.get(EVENT_KIND_PRIVATE_PROP)

    for candidate in candidates:
        candidate_private = ((candidate.get("extendedProperties") or {}).get("private") or {})
        if normalized_title and (candidate.get("summary") or "").strip() != normalized_title:
            continue
        if start_date and _remote_event_start_date(candidate) != start_date:
            continue

        if expected_task_id and candidate_private.get(TASK_ID_PRIVATE_PROP) != expected_task_id:
            continue

        if expected_event_kind and candidate_private.get(EVENT_KIND_PRIVATE_PROP) != expected_event_kind:
            continue

        return candidate

    if not strict_match or (not normalized_title and not start_date and not expected_task_id and not expected_event_kind):
        return candidates[0] if candidates else None

    return None


def _resolve_google_event_id(
    client: GoogleClient,
    *,
    local_event_id: str | None,
    google_event_id: str | None,
    google_calendar_id: str | None,
    extended_properties: dict | None,
    title: str,
    start_date: str | None,
) -> str | None:
    if google_event_id:
        return google_event_id

    try:
        private_props = _private_properties_for_sync(
            local_event_id=local_event_id,
            extended_properties=extended_properties,
        )
        lookup_keys = (
            (LOCAL_EVENT_ID_PRIVATE_PROP, 10, False, False),
            (APPLICATION_ID_PRIVATE_PROP, 250, True, True),
        )

        for lookup_key, max_results, fetch_all, strict_match in lookup_keys:
            lookup_value = private_props.get(lookup_key)
            if not lookup_value:
                continue

            candidates = client.list_events(
                calendar_id=google_calendar_id,
                max_results=max_results,
                include_past=True,
                fetch_all=fetch_all,
                private_extended_property=f"{lookup_key}={lookup_value}",
            )

            if not candidates:
                continue

            selected = _select_remote_event_candidate(
                candidates,
                private_props=private_props,
                title=title,
                start_date=start_date,
                strict_match=strict_match,
            )
            if selected and selected.get("id"):
                return selected["id"]

        return None
    except Exception as exc:
        logger.error(
            "calendar_sync_resolve_existing_failed event_id=%s google_event_id=%s error_type=%s error=%s",
            local_event_id,
            google_event_id,
            type(exc).__name__,
            str(exc),
        )
        return None


@db_task(
    name="core.tasks.calendar_sync.create_google_event_task",
    retries=CALENDAR_SYNC_MAX_RETRIES,
    retry_delay=CALENDAR_SYNC_RETRY_DELAY_SECONDS,
    context=True,
    queue=QUEUE_DEFAULT,
)
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
        target_google_event_id = _resolve_google_event_id(
            client,
            local_event_id=event.pk,
            google_event_id=event.google_event_id,
            google_calendar_id=_calendar_id_for_event(event),
            extended_properties=event.extended_properties,
            title=event.title,
            start_date=event.start_date.isoformat() if event.start_date else None,
        )
        if target_google_event_id:
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
                    reason="create_task_update_target_missing",
                )
        else:
            remote_event = client.create_event(
                payload,
                calendar_id=_calendar_id_for_event(event),
            )
        CalendarEvent.objects.filter(pk=event_id).update(
            google_event_id=remote_event.get("id") or target_google_event_id or event.google_event_id,
            sync_status=CalendarEvent.SYNC_STATUS_SYNCED,
            sync_error="",
            last_synced_at=timezone.now(),
            updated_at=timezone.now(),
        )
        logger.debug(
            "calendar_create_sync_success event_id=%s google_event_id=%s",
            event_id,
            remote_event.get("id") or target_google_event_id or event.google_event_id,
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


@db_task(
    name="core.tasks.calendar_sync.update_google_event_task",
    retries=CALENDAR_SYNC_MAX_RETRIES,
    retry_delay=CALENDAR_SYNC_RETRY_DELAY_SECONDS,
    context=True,
    queue=QUEUE_DEFAULT,
)
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
        target_google_event_id = _resolve_google_event_id(
            client,
            local_event_id=event.pk,
            google_event_id=event.google_event_id,
            google_calendar_id=_calendar_id_for_event(event),
            extended_properties=event.extended_properties,
            title=event.title,
            start_date=event.start_date.isoformat() if event.start_date else None,
        )
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


@db_task(
    name="core.tasks.calendar_sync.delete_google_event_task",
    retries=CALENDAR_SYNC_MAX_RETRIES,
    retry_delay=CALENDAR_SYNC_RETRY_DELAY_SECONDS,
    context=True,
    queue=QUEUE_DEFAULT,
)
def delete_google_event_task(
    google_event_id: str | None = None,
    google_calendar_id: str | None = None,
    event_id: str | None = None,
    title: str = "",
    start_date: str | None = None,
    extended_properties: dict | None = None,
    task=None,
):
    target_google_event_id = google_event_id
    try:
        client = GoogleClient()
        target_google_event_id = _resolve_google_event_id(
            client,
            local_event_id=event_id,
            google_event_id=google_event_id,
            google_calendar_id=google_calendar_id,
            extended_properties=extended_properties,
            title=title,
            start_date=start_date,
        )
        if not target_google_event_id:
            logger.error(
                "calendar_delete_sync_missing_google_event_id event_id=%s google_event_id=%s",
                event_id,
                google_event_id,
            )
            return {"status": "skipped", "reason": "google_event_id_missing"}

        logger.debug(
            "calendar_delete_sync_start event_id=%s google_event_id=%s calendar_id=%s",
            event_id,
            target_google_event_id,
            google_calendar_id,
        )
        if google_calendar_id:
            client.delete_event(event_id=target_google_event_id, calendar_id=google_calendar_id)
        else:
            client.delete_event(event_id=target_google_event_id)
        logger.debug(
            "calendar_delete_sync_success event_id=%s google_event_id=%s calendar_id=%s",
            event_id,
            target_google_event_id,
            google_calendar_id,
        )
        return {
            "status": "ok",
            "google_event_id": target_google_event_id,
            "google_calendar_id": google_calendar_id,
        }
    except Exception as exc:
        if _is_google_not_found_error(exc):
            logger.error(
                "calendar_delete_sync_missing_remote_event event_id=%s google_event_id=%s calendar_id=%s error=%s",
                event_id,
                target_google_event_id,
                google_calendar_id,
                str(exc),
            )
            return {
                "status": "ok",
                "google_event_id": target_google_event_id,
                "google_calendar_id": google_calendar_id,
                "reason": "remote_event_already_missing",
            }
        if task and task.retries > 0 and _is_retryable_google_error(exc):
            logger.error(
                "calendar_delete_sync_retrying event_id=%s google_event_id=%s calendar_id=%s retries_left=%s error_type=%s error=%s",
                event_id,
                target_google_event_id,
                google_calendar_id,
                task.retries,
                type(exc).__name__,
                str(exc),
            )
            raise
        logger.error(
            "calendar_delete_sync_failed_after_retries event_id=%s google_event_id=%s error_type=%s error=%s",
            event_id,
            target_google_event_id,
            type(exc).__name__,
            str(exc),
        )
        return {"status": "failed", "error": str(exc)}
