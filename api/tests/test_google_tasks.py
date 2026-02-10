import pytest

# Skip these tests gracefully if Django is not installed in this environment
pytest.importorskip("django")

import datetime
from contextlib import ExitStack
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient


def make_task(title="Test Task"):
    now = datetime.datetime.now(datetime.UTC)
    due = (now + datetime.timedelta(days=1)).replace(microsecond=0)
    return {
        "id": "task-1",
        "title": title,
        "notes": "desc",
        "due": due.isoformat().replace("+00:00", "Z"),
    }


class TestGoogleTasksAPI:
    def setup_method(self):
        self.client = APIClient()

    @pytest.mark.django_db
    def test_tasks_crud_flow(self):
        User = get_user_model()
        user = User.objects.create_superuser(username="testadmin2", email="test2@local", password="test")
        self.client.force_authenticate(user=user)

        with ExitStack() as stack:
            # Mock __init__ so it doesn't try to load real credentials
            stack.enter_context(patch("core.utils.google_client.GoogleClient.__init__", return_value=None))

            mock_create = stack.enter_context(patch("core.utils.google_client.GoogleClient.create_task"))
            mock_list = stack.enter_context(patch("core.utils.google_client.GoogleClient.list_tasks"))
            mock_get = stack.enter_context(patch("core.utils.google_client.GoogleClient.get_task"))
            mock_update = stack.enter_context(patch("core.utils.google_client.GoogleClient.update_task"))
            mock_delete = stack.enter_context(patch("core.utils.google_client.GoogleClient.delete_task"))

            created = make_task("My Task")
            mock_create.return_value = created

            # Create
            payload = {"title": "My Task", "notes": "desc", "due": created["due"]}
            resp = self.client.post("/api/tasks/", payload, format="json")
            assert resp.status_code == status.HTTP_201_CREATED, resp.data
            assert resp.data["id"] == "task-1"

            # List should include created task
            mock_list.return_value = [created]
            resp = self.client.get("/api/tasks/")
            assert resp.status_code == status.HTTP_200_OK
            assert any(t["id"] == "task-1" for t in resp.data)

            # Update
            updated = dict(created)
            updated["title"] = "Updated Task"
            mock_update.return_value = updated

            resp = self.client.put(f"/api/tasks/{created['id']}/", {"title": "Updated Task"}, format="json")
            assert resp.status_code == status.HTTP_200_OK
            assert resp.data["title"] == "Updated Task"

            # Retrieve single
            mock_get.return_value = updated
            resp = self.client.get(f"/api/tasks/{created['id']}/")
            assert resp.status_code == status.HTTP_200_OK
            assert resp.data["title"] == "Updated Task"

            # Delete
            mock_delete.return_value = True
            resp = self.client.delete(f"/api/tasks/{created['id']}/")
            assert resp.status_code == status.HTTP_204_NO_CONTENT

            # After delete, list empty
            mock_list.return_value = []
            resp = self.client.get("/api/tasks/")
            assert resp.status_code == status.HTTP_200_OK
            assert resp.data == []

    @pytest.mark.django_db
    def test_create_validation_error_missing_title(self):
        """Ensure serializer validation rejects missing required title field"""
        User = get_user_model()
        user = User.objects.create_superuser(username="testadmin3", email="test3@local", password="test")
        self.client.force_authenticate(user=user)

        with ExitStack() as stack:
            stack.enter_context(patch("core.utils.google_client.GoogleClient.__init__", return_value=None))
            mock_create = stack.enter_context(patch("core.utils.google_client.GoogleClient.create_task"))

            # Missing title
            payload = {"notes": "desc"}
            resp = self.client.post("/api/tasks/", payload, format="json")
            assert resp.status_code == status.HTTP_400_BAD_REQUEST
            # Ensure client create_task was not called
            mock_create.assert_not_called()
