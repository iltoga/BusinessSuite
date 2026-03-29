"""Regression tests for Google Calendar request-mocking behavior."""

from unittest.mock import patch

import pytest
from core.models.calendar_event import CalendarEvent
from core.tasks.calendar_sync import create_google_event_task, delete_google_event_task, update_google_event_task


def _run_huey_task(task, **kwargs):
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
        google_client = google_client_cls.return_value
        google_client.list_events.return_value = []
        google_client.create_event.return_value = {"id": "google-evt-1"}

        result = _run_huey_task(create_google_event_task, event_id=event.id)

    status = result["status"] if isinstance(result, dict) else getattr(result, "status", None)
    assert status == "ok"
    event.refresh_from_db()
    assert event.google_event_id == "google-evt-1"
    assert event.sync_status == CalendarEvent.SYNC_STATUS_SYNCED
    assert event.last_synced_at is not None
    assert google_client.create_event.call_args.kwargs["event_id"] is not None


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

        result = _run_huey_task(update_google_event_task, event_id=event.id)

    status = result["status"] if isinstance(result, dict) else getattr(result, "status", None)
    assert status == "ok"
    google_client_cls.return_value.update_event.assert_called_once()
    event.refresh_from_db()
    assert event.google_event_id == "google-evt-existing"
    assert event.sync_status == CalendarEvent.SYNC_STATUS_SYNCED


@pytest.mark.django_db
def test_create_google_event_task_reuses_existing_remote_event_by_local_event_id():
    event = CalendarEvent.objects.create(
        id="evt-task-create-reuse",
        title="Mirror Event",
        description="sync me",
        start_date="2026-02-10",
        end_date="2026-02-11",
    )

    with patch("core.tasks.calendar_sync.GoogleClient") as google_client_cls:
        google_client = google_client_cls.return_value
        google_client.list_events.return_value = [{"id": "google-evt-existing", "summary": "Mirror Event"}]
        google_client.update_event.return_value = {"id": "google-evt-existing"}

        result = _run_huey_task(create_google_event_task, event_id=event.id)

    status = result["status"] if isinstance(result, dict) else getattr(result, "status", None)
    assert status == "ok"
    google_client.list_events.assert_called_once_with(
        calendar_id=None,
        max_results=10,
        include_past=True,
        fetch_all=False,
        private_extended_property="revisbali_calendar_event_id=evt-task-create-reuse",
    )
    google_client.update_event.assert_called_once()
    google_client.create_event.assert_not_called()
    event.refresh_from_db()
    assert event.google_event_id == "google-evt-existing"
    assert event.sync_status == CalendarEvent.SYNC_STATUS_SYNCED


@pytest.mark.django_db
def test_delete_google_event_task_resolves_remote_event_by_application_metadata():
    with patch("core.tasks.calendar_sync.GoogleClient") as google_client_cls:
        google_client = google_client_cls.return_value
        google_client.list_events.side_effect = [
            [],
            [
                {
                    "id": "google-delete-id",
                    "summary": "Mirror Event",
                    "start": {"date": "2026-02-10"},
                    "extendedProperties": {
                        "private": {
                            "revisbali_customer_application_id": "99",
                            "revisbali_task_id": "7",
                            "revisbali_event_kind": "task_deadline",
                        }
                    },
                }
            ],
        ]

        result = _run_huey_task(
            delete_google_event_task,
            event_id="evt-task-delete-recover",
            title="Mirror Event",
            start_date="2026-02-10",
            extended_properties={
                "private": {
                    "revisbali_customer_application_id": "99",
                    "revisbali_task_id": "7",
                    "revisbali_event_kind": "task_deadline",
                }
            },
        )

    status = result["status"] if isinstance(result, dict) else getattr(result, "status", None)
    assert status == "ok"
    assert google_client.list_events.call_args_list[0].kwargs == {
        "calendar_id": None,
        "max_results": 10,
        "include_past": True,
        "fetch_all": False,
        "private_extended_property": "revisbali_calendar_event_id=evt-task-delete-recover",
    }
    assert google_client.list_events.call_args_list[1].kwargs == {
        "calendar_id": None,
        "max_results": 250,
        "include_past": True,
        "fetch_all": True,
        "private_extended_property": "revisbali_customer_application_id=99",
    }
    google_client.delete_event.assert_called_once_with(event_id="google-delete-id")


@pytest.mark.django_db
def test_delete_google_event_task_logs_critical_on_error():
    with patch("core.tasks.calendar_sync.GoogleClient") as google_client_cls:
        google_client_cls.return_value.delete_event.side_effect = RuntimeError("delete failed")
        result = _run_huey_task(delete_google_event_task, google_event_id="google-delete-id")

    status = result["status"] if isinstance(result, dict) else getattr(result, "status", None)
    assert status == "failed"
    google_client_cls.return_value.delete_event.assert_called_once_with(event_id="google-delete-id")


@pytest.mark.django_db
def test_create_google_event_task_reuses_preferred_google_id_on_conflict():
    event = CalendarEvent.objects.create(
        id="evt-task-create-conflict",
        title="Mirror Event",
        description="sync me",
        start_date="2026-02-10",
        end_date="2026-02-11",
    )

    with patch("core.tasks.calendar_sync.GoogleClient") as google_client_cls:
        google_client = google_client_cls.return_value
        google_client.list_events.return_value = []
        google_client.create_event.side_effect = RuntimeError("409 already exists")
        google_client.get_event.return_value = {"id": "rb-existing-id"}

        result = _run_huey_task(create_google_event_task, event_id=event.id)

    status = result["status"] if isinstance(result, dict) else getattr(result, "status", None)
    assert status == "ok"
    google_client.get_event.assert_called_once()
    event.refresh_from_db()
    assert event.google_event_id == "rb-existing-id"
