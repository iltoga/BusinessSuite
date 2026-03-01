from unittest.mock import patch

import pytest

from core.models.calendar_event import CalendarEvent
from core.tasks.calendar_sync import create_google_event_task, delete_google_event_task, update_google_event_task


def _run_task(task, **kwargs):
    if hasattr(task, "call_local"):
        return task.call_local(**kwargs)
    if hasattr(task, "func"):
        return task.func(**kwargs)
    return task(**kwargs)


@pytest.mark.django_db
def test_create_google_event_task_updates_sync_metadata():
    event = CalendarEvent.objects.create(
        id="evt-task-create",
        title="Mirror Event",
        description="sync me",
        start_date="2026-02-10",
        end_date="2026-02-11",
    )

    with patch("core.tasks.calendar_sync.GoogleClient") as google_client_cls:
        google_client_cls.return_value.create_event.return_value = {"id": "google-evt-1"}

        result = _run_task(create_google_event_task, event_id=event.id)

    assert result["status"] == "ok"
    event.refresh_from_db()
    assert event.google_event_id == "google-evt-1"
    assert event.sync_status == CalendarEvent.SYNC_STATUS_SYNCED
    assert event.last_synced_at is not None


@pytest.mark.django_db
def test_update_google_event_task_updates_existing_google_event():
    event = CalendarEvent.objects.create(
        id="evt-task-update",
        title="Mirror Event",
        description="sync update",
        start_date="2026-02-10",
        end_date="2026-02-11",
        google_event_id="google-evt-existing",
    )

    with patch("core.tasks.calendar_sync.GoogleClient") as google_client_cls:
        google_client_cls.return_value.update_event.return_value = {"id": "google-evt-existing"}

        result = _run_task(update_google_event_task, event_id=event.id)

    assert result["status"] == "ok"
    google_client_cls.return_value.update_event.assert_called_once()
    event.refresh_from_db()
    assert event.google_event_id == "google-evt-existing"
    assert event.sync_status == CalendarEvent.SYNC_STATUS_SYNCED


@pytest.mark.django_db
def test_delete_google_event_task_logs_critical_on_error():
    with patch("core.tasks.calendar_sync.GoogleClient") as google_client_cls:
        google_client_cls.return_value.delete_event.side_effect = RuntimeError("delete failed")
        result = _run_task(delete_google_event_task, google_event_id="google-delete-id")

    assert result["status"] == "failed"
    google_client_cls.return_value.delete_event.assert_called_once_with(event_id="google-delete-id")
