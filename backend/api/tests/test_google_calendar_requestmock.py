import datetime
import json
from unittest.mock import patch

import pytest
from googleapiclient.http import RequestMockBuilder
from rest_framework.test import APIClient

from core.services.google_calendar_event_colors import GoogleCalendarEventColors


@pytest.mark.django_db
def test_calendar_crud_flow_with_requestmockbuilder(settings):
    # Use a fixed time to avoid jitter and timezone shifts in the test comparison
    start_iso = "2026-02-10T10:00:00+08:00"
    end_iso = "2026-02-10T11:00:00+08:00"

    # Use camelCase to test the parser mapping
    payload = {
        "summary": "Meeting",
        "description": "Discuss",
        "startTime": start_iso,
        "endTime": end_iso,
    }

    # Expected event representation returned by the Google API
    created_event = {
        "id": "evt-req-1",
        "summary": "Meeting",
        "description": "Discuss",
        "start": {"dateTime": start_iso, "timeZone": "Asia/Makassar"},
        "end": {"dateTime": end_iso, "timeZone": "Asia/Makassar"},
    }

    # The body the Google client will send for insert
    expected_insert_body = {
        "summary": payload["summary"],
        "description": payload.get("description", ""),
        "start": {"dateTime": start_iso, "timeZone": "Asia/Makassar"},
        "end": {"dateTime": end_iso, "timeZone": "Asia/Makassar"},
        "reminders": {
            "useDefault": False,
            "overrides": [{"method": "email", "minutes": 60}, {"method": "popup", "minutes": 10}],
        },
    }

    # Prepare a RequestMockBuilder mapping methodIds -> responses
    rmb = RequestMockBuilder(
        {
            "calendar.events.insert": (None, json.dumps(created_event), json.dumps(expected_insert_body)),
            "calendar.events.list": (None, json.dumps({"items": [created_event]})),
            "calendar.events.get": (None, json.dumps(created_event)),
            "calendar.events.patch": (None, json.dumps({**created_event, "summary": "Updated Meeting"})),
            "calendar.events.delete": (None, json.dumps({})),
        }
    )

    # Patch file existence and credentials, and make the 'build' used in our module attach the requestBuilder
    with (
        patch("core.utils.google_client.os.path.exists", return_value=True),
        patch("core.utils.google_client.service_account.Credentials.from_service_account_file") as mock_creds,
        patch("core.utils.google_client.build") as real_build,
    ):

        # Provide a lightweight credentials object with an `authorize` method that discovery.build may call
        class DummyCreds:
            def authorize(self, http):
                return http

        mock_creds.return_value = DummyCreds()

        # discovery.build remains the original; import it to call as the underlying implementation
        import googleapiclient.discovery as discovery

        orig_build = discovery.build

        # Make our patched build inject the RequestMockBuilder
        def build_with_rmb(service, version, credentials=None, **kwargs):
            return orig_build(service, version, credentials=credentials, requestBuilder=rmb, **kwargs)

        real_build.side_effect = build_with_rmb

        # Create authenticated client
        client = APIClient()
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_superuser(username="reqtest", email="req@test", password="test")
        client.force_authenticate(user=user)

        # Create event (this will call calendar.events().insert and use our RequestMockBuilder)
        resp = client.post("/api/calendar/", payload, format="json")
        if resp.status_code != 201:
            # Debug output to surface server error details
            print("POST /api/calendar/ returned:", resp.status_code, resp.content)
        assert resp.status_code == 201
        assert resp.data["id"] == created_event["id"]

        # List events
        resp = client.get("/api/calendar/?source=google")
        assert resp.status_code == 200
        assert any(e["id"] == created_event["id"] for e in resp.data)

        # Update event
        resp = client.put(f"/api/calendar/{created_event['id']}/", {"summary": "Updated Meeting"}, format="json")
        assert resp.status_code == 200
        assert resp.data["summary"] == "Updated Meeting"

        # Get single event
        resp = client.get(f"/api/calendar/{created_event['id']}/")
        assert resp.status_code == 200
        assert resp.data["id"] == created_event["id"]

        # Delete
        resp = client.delete(f"/api/calendar/{created_event['id']}/")
        assert resp.status_code == 204

        # RMB is static, so this list call still returns the same mocked payload.
        resp = client.get("/api/calendar/?source=google")
        assert resp.status_code == 200


@pytest.mark.django_db
def test_calendar_done_patch_updates_color_with_requestmockbuilder(settings):
    done_color_id = GoogleCalendarEventColors.done_color_id()
    updated_event = {
        "id": "evt-color-1",
        "summary": "Task",
        "colorId": done_color_id,
        "start": {"date": "2026-02-13"},
        "end": {"date": "2026-02-14"},
    }

    rmb = RequestMockBuilder(
        {
            "calendar.events.patch": (None, json.dumps(updated_event), json.dumps({"colorId": done_color_id})),
        }
    )

    with (
        patch("core.utils.google_client.os.path.exists", return_value=True),
        patch("core.utils.google_client.service_account.Credentials.from_service_account_file") as mock_creds,
        patch("core.utils.google_client.build") as real_build,
    ):

        class DummyCreds:
            def authorize(self, http):
                return http

        mock_creds.return_value = DummyCreds()

        import googleapiclient.discovery as discovery

        orig_build = discovery.build

        def build_with_rmb(service, version, credentials=None, **kwargs):
            return orig_build(service, version, credentials=credentials, requestBuilder=rmb, **kwargs)

        real_build.side_effect = build_with_rmb

        client = APIClient()
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_superuser(username="reqtest2", email="req2@test", password="test")
        client.force_authenticate(user=user)

        resp = client.patch(f"/api/calendar/{updated_event['id']}/", {"done": True}, format="json")
        assert resp.status_code == 200
        assert resp.data["colorId"] == done_color_id
