import pytest

# Skip these tests gracefully if Django is not installed in this environment
pytest.importorskip("django")

import datetime
from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


def make_event(summary="Test event"):
    now = datetime.datetime.now(datetime.UTC)
    start = now.replace(microsecond=0)
    end = start + datetime.timedelta(hours=1)
    return {
        "id": "evt-1",
        "summary": summary,
        "description": "desc",
        "start": {"dateTime": start.isoformat().replace("+00:00", "Z"), "timeZone": "UTC"},
        "end": {"dateTime": end.isoformat().replace("+00:00", "Z"), "timeZone": "UTC"},
    }


class TestGoogleCalendarAPI:
    def setup_method(self):
        self.client = APIClient()

    @pytest.mark.django_db
    def test_calendar_crud_flow(self):
        # Create
        now = datetime.datetime.now(datetime.UTC)
        payload = {
            "summary": "Meeting",
            "description": "Discuss",
            "start_time": now.isoformat().replace("+00:00", "Z"),
            "end_time": (now + datetime.timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        }

        from contextlib import ExitStack

        from django.contrib.auth import get_user_model

        # Create a superuser and authenticate the test client so DRF permissions allow access
        User = get_user_model()
        user = User.objects.create_superuser(username="testadmin", email="test@local", password="test")
        self.client.force_authenticate(user=user)

        with ExitStack() as stack:
            # Mock __init__ so it doesn't try to load real credentials
            stack.enter_context(patch("core.utils.google_client.GoogleClient.__init__", return_value=None))

            mock_create = stack.enter_context(patch("core.utils.google_client.GoogleClient.create_event"))
            mock_list = stack.enter_context(patch("core.utils.google_client.GoogleClient.list_events"))
            mock_get = stack.enter_context(patch("core.utils.google_client.GoogleClient.get_event"))
            mock_update = stack.enter_context(patch("core.utils.google_client.GoogleClient.update_event"))
            mock_delete = stack.enter_context(patch("core.utils.google_client.GoogleClient.delete_event"))

            created = make_event("Meeting")
            mock_create.return_value = created

            resp = self.client.post("/api/calendar/", payload, format="json")
            assert resp.status_code == status.HTTP_201_CREATED
            assert resp.data["id"] == "evt-1"

            # List should include created event
            mock_list.return_value = [created]
            resp = self.client.get("/api/calendar/")
            assert resp.status_code == status.HTTP_200_OK
            assert any(e["id"] == "evt-1" for e in resp.data)

            # Update
            updated = dict(created)
            updated["summary"] = "Updated Meeting"
            mock_update.return_value = updated

            resp = self.client.put(f"/api/calendar/{created['id']}/", {"summary": "Updated Meeting"}, format="json")
            assert resp.status_code == status.HTTP_200_OK
            assert resp.data["summary"] == "Updated Meeting"

            # Retrieve single
            mock_get.return_value = updated
            resp = self.client.get(f"/api/calendar/{created['id']}/")
            assert resp.status_code == status.HTTP_200_OK
            assert resp.data["summary"] == "Updated Meeting"

            # Delete
            mock_delete.return_value = True
            resp = self.client.delete(f"/api/calendar/{created['id']}/")
            assert resp.status_code == status.HTTP_204_NO_CONTENT

            # After delete, list empty
            mock_list.return_value = []
            resp = self.client.get("/api/calendar/")
            assert resp.status_code == status.HTTP_200_OK
            assert resp.data == []
