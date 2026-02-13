import pytest

# Skip these tests gracefully if Django is not installed in this environment
pytest.importorskip("django")

import datetime
from contextlib import ExitStack
from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APIClient

from core.services.google_calendar_event_colors import GoogleCalendarEventColors


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
            resp = self.client.get("/api/calendar/?source=google")
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
            resp = self.client.get("/api/calendar/?source=google")
            assert resp.status_code == status.HTTP_200_OK
            assert resp.data == []

    @pytest.mark.django_db
    def test_calendar_list_uses_local_application_source_by_default(self):
        from django.contrib.auth import get_user_model
        from django.utils import timezone

        from customer_applications.models import DocApplication
        from customers.models import Customer
        from products.models import Product

        User = get_user_model()
        user = User.objects.create_superuser(username="testadmin-local", email="local@test", password="test")
        self.client.force_authenticate(user=user)

        customer = Customer.objects.create(first_name="Local", last_name="Event")
        product = Product.objects.create(
            name="Local Calendar Product",
            code="LCP-1",
            product_type="visa",
            required_documents="Passport",
        )
        product.tasks.create(
            step=1,
            name="Biometrics",
            duration=1,
            duration_is_business_days=True,
            add_task_to_calendar=True,
            last_step=False,
        )

        application = DocApplication.objects.create(
            customer=customer,
            product=product,
            doc_date=timezone.localdate(),
            due_date=timezone.localdate(),
            add_deadlines_to_calendar=True,
            created_by=user,
        )

        resp = self.client.get("/api/calendar/")
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data) == 1
        assert str(application.id) in resp.data[0]["summary"]

    @pytest.mark.django_db
    def test_calendar_list_local_includes_completed_workflow_events_as_done(self):
        from django.contrib.auth import get_user_model
        from django.utils import timezone

        from customer_applications.models import DocApplication
        from customer_applications.models.doc_workflow import DocWorkflow
        from customers.models import Customer
        from products.models import Product

        User = get_user_model()
        user = User.objects.create_superuser(username="testadmin-local-done", email="localdone@test", password="test")
        self.client.force_authenticate(user=user)

        customer = Customer.objects.create(first_name="Done", last_name="Workflow")
        product = Product.objects.create(
            name="Local Calendar Done Product",
            code="LCD-1",
            product_type="visa",
            required_documents="Passport",
        )
        task1 = product.tasks.create(
            step=1,
            name="Step 1",
            duration=1,
            duration_is_business_days=True,
            add_task_to_calendar=True,
            last_step=False,
        )
        task2 = product.tasks.create(
            step=2,
            name="Step 2",
            duration=1,
            duration_is_business_days=True,
            add_task_to_calendar=True,
            last_step=False,
        )

        today = timezone.localdate()
        tomorrow = today + datetime.timedelta(days=1)
        application = DocApplication.objects.create(
            customer=customer,
            product=product,
            doc_date=today,
            due_date=tomorrow,
            add_deadlines_to_calendar=True,
            created_by=user,
        )

        completed = DocWorkflow.objects.create(
            start_date=today,
            due_date=today,
            task=task1,
            doc_application=application,
            created_by=user,
            status=DocWorkflow.STATUS_COMPLETED,
        )
        pending = DocWorkflow.objects.create(
            start_date=today,
            due_date=tomorrow,
            task=task2,
            doc_application=application,
            created_by=user,
            status=DocWorkflow.STATUS_PENDING,
        )

        resp = self.client.get("/api/calendar/")
        assert resp.status_code == status.HTTP_200_OK

        done_event = next((event for event in resp.data if event["id"].endswith(f"workflow-{completed.id}")), None)
        assert done_event is not None
        assert done_event["colorId"] == GoogleCalendarEventColors.done_color_id()
        assert "Step 1" in done_event["summary"]

        todo_event = next((event for event in resp.data if event["id"] == f"local-app-{application.id}"), None)
        assert todo_event is not None
        assert todo_event["colorId"] == GoogleCalendarEventColors.todo_color_id()
        assert "Step 2" in todo_event["summary"]
        assert pending.due_date.isoformat() == todo_event["start"]["date"]

    @pytest.mark.django_db
    def test_partial_update_done_field_maps_to_color_id(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_superuser(username="testadmin2", email="test2@local", password="test")
        self.client.force_authenticate(user=user)

        with ExitStack() as stack:
            stack.enter_context(patch("core.utils.google_client.GoogleClient.__init__", return_value=None))
            mock_update = stack.enter_context(patch("core.utils.google_client.GoogleClient.update_event"))

            updated = make_event("Done Task")
            updated["colorId"] = GoogleCalendarEventColors.done_color_id()
            mock_update.return_value = updated

            resp = self.client.patch("/api/calendar/evt-1/", {"done": True}, format="json")
            assert resp.status_code == status.HTTP_200_OK
            assert resp.data["colorId"] == GoogleCalendarEventColors.done_color_id()

            mock_update.assert_called_once()
            kwargs = mock_update.call_args.kwargs
            assert kwargs["event_id"] == "evt-1"
            assert kwargs["data"]["color_id"] == GoogleCalendarEventColors.done_color_id()

    @pytest.mark.django_db
    def test_partial_update_rejects_invalid_color_id(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_superuser(username="testadmin3", email="test3@local", password="test")
        self.client.force_authenticate(user=user)

        with patch("core.utils.google_client.GoogleClient.__init__", return_value=None):
            resp = self.client.patch("/api/calendar/evt-1/", {"colorId": "99"}, format="json")
            assert resp.status_code == status.HTTP_400_BAD_REQUEST
            assert "errors" in resp.data
            assert "colorId" in resp.data["errors"]

    @pytest.mark.django_db
    def test_partial_update_rejects_done_false(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_superuser(username="testadmin4", email="test4@local", password="test")
        self.client.force_authenticate(user=user)

        with patch("core.utils.google_client.GoogleClient.update_event") as update_mock:
            resp = self.client.patch("/api/calendar/evt-1/", {"done": False}, format="json")

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        errors = resp.data.get("errors", resp.data)
        assert "done" in errors
        update_mock.assert_not_called()

    @pytest.mark.django_db
    def test_partial_update_done_completes_application_current_task_and_queues_calendar_sync(self):
        from django.contrib.auth import get_user_model
        from django.utils import timezone

        from customer_applications.models import DocApplication, Document
        from customer_applications.models.doc_workflow import DocWorkflow
        from customers.models import Customer
        from products.models import Product
        from products.models.document_type import DocumentType

        User = get_user_model()
        user = User.objects.create_superuser(username="testadmin5", email="test5@local", password="test")
        self.client.force_authenticate(user=user)

        customer = Customer.objects.create(first_name="Calendar", last_name="Workflow")
        product = Product.objects.create(
            name="Calendar Workflow Product",
            code="CWP-1",
            product_type="visa",
            required_documents="Passport",
        )
        task1 = product.tasks.create(
            step=1,
            name="Step 1",
            duration=1,
            duration_is_business_days=True,
            add_task_to_calendar=True,
            last_step=False,
        )
        product.tasks.create(
            step=2,
            name="Step 2",
            duration=1,
            duration_is_business_days=True,
            add_task_to_calendar=True,
            last_step=False,
        )

        application = DocApplication.objects.create(
            customer=customer,
            product=product,
            doc_date=timezone.localdate(),
            due_date=timezone.localdate(),
            calendar_event_id="evt-app-1",
            add_deadlines_to_calendar=True,
            created_by=user,
        )
        doc_type = DocumentType.objects.create(name="Passport", has_doc_number=True)
        Document.objects.create(
            doc_application=application,
            doc_type=doc_type,
            required=True,
            created_by=user,
        )

        workflow = DocWorkflow(
            start_date=timezone.localdate(),
            task=task1,
            doc_application=application,
            created_by=user,
            status=DocWorkflow.STATUS_PENDING,
        )
        workflow.due_date = workflow.calculate_workflow_due_date()
        workflow.save()

        with patch("customer_applications.tasks.sync_application_calendar_task") as sync_mock, patch(
            "django.db.transaction.on_commit", side_effect=lambda callback: callback()
        ), patch("core.utils.google_client.GoogleClient.update_event") as update_mock:
            resp = self.client.patch("/api/calendar/evt-app-1/", {"done": True}, format="json")

        assert resp.status_code == status.HTTP_200_OK
        workflow.refresh_from_db()
        application.refresh_from_db()
        assert workflow.status == DocWorkflow.STATUS_COMPLETED

        next_workflow = application.workflows.filter(task__step=2).first()
        assert next_workflow is not None
        assert next_workflow.status == DocWorkflow.STATUS_PENDING

        sync_mock.assert_called_once()
        update_mock.assert_called_once()
        kwargs = update_mock.call_args.kwargs
        assert kwargs["event_id"] == "evt-app-1"
        assert kwargs["data"]["color_id"] == GoogleCalendarEventColors.done_color_id()
