import datetime
from unittest.mock import patch

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from core.models.calendar_event import CalendarEvent
from core.services.google_calendar_event_colors import GoogleCalendarEventColors


class TestGoogleCalendarAPI:
    def setup_method(self):
        self.client = APIClient()

    @pytest.mark.django_db
    def test_calendar_crud_flow(self):
        now = datetime.datetime.now(datetime.UTC)
        payload = {
            "summary": "Meeting",
            "description": "Discuss",
            "start_time": now.isoformat().replace("+00:00", "Z"),
            "end_time": (now + datetime.timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        }

        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_superuser(username="testadmin", email="test@local", password="test")
        self.client.force_authenticate(user=user)

        with (
            patch("core.signals_calendar.create_google_event_task") as create_sync_mock,
            patch("core.signals_calendar.update_google_event_task") as update_sync_mock,
            patch("core.signals_calendar.delete_google_event_task") as delete_sync_mock,
            patch("django.db.transaction.on_commit", side_effect=lambda callback: callback()),
        ):
            resp = self.client.post("/api/calendar/", payload, format="json")
            assert resp.status_code == status.HTTP_201_CREATED
            event_id = resp.data["id"]
            assert CalendarEvent.objects.filter(pk=event_id).exists()
            create_sync_mock.assert_called_once_with(event_id=event_id)

            resp = self.client.get("/api/calendar/?source=google")
            assert resp.status_code == status.HTTP_200_OK
            assert any(e["id"] == event_id for e in resp.data)

            resp = self.client.put(f"/api/calendar/{event_id}/", {"summary": "Updated Meeting"}, format="json")
            assert resp.status_code == status.HTTP_200_OK
            assert resp.data["summary"] == "Updated Meeting"
            update_sync_mock.assert_called_once_with(event_id=event_id)

            resp = self.client.get(f"/api/calendar/{event_id}/")
            assert resp.status_code == status.HTTP_200_OK
            assert resp.data["summary"] == "Updated Meeting"

            CalendarEvent.objects.filter(pk=event_id).update(google_event_id="g-evt-1")

            resp = self.client.delete(f"/api/calendar/{event_id}/")
            assert resp.status_code == status.HTTP_204_NO_CONTENT
            assert not CalendarEvent.objects.filter(pk=event_id).exists()
            delete_sync_mock.assert_called_once_with(google_event_id="g-evt-1")

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

        now = datetime.datetime.now(datetime.UTC)
        event = CalendarEvent.objects.create(
            id="evt-1",
            title="Done Task",
            description="desc",
            start_time=now,
            end_time=now + datetime.timedelta(hours=1),
            source=CalendarEvent.SOURCE_MANUAL,
        )

        with (
            patch("core.signals_calendar.update_google_event_task") as update_sync_mock,
            patch("django.db.transaction.on_commit", side_effect=lambda callback: callback()),
        ):
            resp = self.client.patch("/api/calendar/evt-1/", {"done": True}, format="json")
            assert resp.status_code == status.HTTP_200_OK
            assert resp.data["colorId"] == GoogleCalendarEventColors.done_color_id()
            update_sync_mock.assert_called_once_with(event_id="evt-1")

        event.refresh_from_db()
        assert event.color_id == GoogleCalendarEventColors.done_color_id()

    @pytest.mark.django_db
    def test_partial_update_rejects_invalid_color_id(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_superuser(username="testadmin3", email="test3@local", password="test")
        self.client.force_authenticate(user=user)

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

        resp = self.client.patch("/api/calendar/evt-1/", {"done": False}, format="json")

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        errors = resp.data.get("errors", resp.data)
        assert "done" in errors

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
        CalendarEvent.objects.create(
            id="evt-app-1",
            source=CalendarEvent.SOURCE_APPLICATION,
            application=application,
            title="App task",
            description="desc",
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + datetime.timedelta(days=1),
            color_id=GoogleCalendarEventColors.todo_color_id(),
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

        with (
            patch("customer_applications.tasks.sync_application_calendar_task") as sync_mock,
            patch("django.db.transaction.on_commit", side_effect=lambda callback: callback()),
            patch("core.signals_calendar.update_google_event_task") as update_sync_mock,
        ):
            resp = self.client.patch("/api/calendar/evt-app-1/", {"done": True}, format="json")

        assert resp.status_code == status.HTTP_200_OK
        workflow.refresh_from_db()
        application.refresh_from_db()
        assert workflow.status == DocWorkflow.STATUS_COMPLETED

        next_workflow = application.workflows.filter(task__step=2).first()
        assert next_workflow is not None
        assert next_workflow.status == DocWorkflow.STATUS_PENDING

        sync_mock.assert_called_once()
        update_sync_mock.assert_called_once_with(event_id="evt-app-1")

        event = CalendarEvent.objects.get(pk="evt-app-1")
        assert event.color_id == GoogleCalendarEventColors.done_color_id()

    @pytest.mark.django_db
    def test_partial_update_done_on_overdue_application_force_completes_application(self):
        from django.contrib.auth import get_user_model
        from django.utils import timezone

        from customer_applications.models import DocApplication
        from customers.models import Customer
        from products.models import Product

        User = get_user_model()
        user = User.objects.create_superuser(username="testadmin6", email="test6@local", password="test")
        self.client.force_authenticate(user=user)

        customer = Customer.objects.create(first_name="Overdue", last_name="App")
        product = Product.objects.create(
            name="Overdue Product",
            code="OD-1",
            product_type="visa",
            required_documents="Passport",
        )
        task = product.tasks.create(
            step=1,
            name="Step 1",
            duration=1,
            duration_is_business_days=True,
            add_task_to_calendar=True,
            last_step=False,
        )
        application = DocApplication.objects.create(
            customer=customer,
            product=product,
            doc_date=timezone.localdate() - datetime.timedelta(days=20),
            due_date=timezone.localdate() - datetime.timedelta(days=2),
            calendar_event_id="evt-overdue-1",
            add_deadlines_to_calendar=True,
            created_by=user,
            status=DocApplication.STATUS_PENDING,
        )
        application.workflows.create(
            start_date=timezone.localdate() - datetime.timedelta(days=20),
            due_date=timezone.localdate() - datetime.timedelta(days=2),
            task=task,
            created_by=user,
            status="pending",
        )
        CalendarEvent.objects.create(
            id="evt-overdue-1",
            source=CalendarEvent.SOURCE_APPLICATION,
            application=application,
            title="Overdue task",
            description="desc",
            start_date=timezone.localdate() - datetime.timedelta(days=2),
            end_date=timezone.localdate() - datetime.timedelta(days=1),
            color_id=GoogleCalendarEventColors.todo_color_id(),
        )

        with (
            patch("customer_applications.tasks.sync_application_calendar_task") as sync_mock,
            patch("django.db.transaction.on_commit", side_effect=lambda callback: callback()),
            patch("core.signals_calendar.update_google_event_task") as update_sync_mock,
        ):
            resp = self.client.patch("/api/calendar/evt-overdue-1/", {"done": True}, format="json")

        assert resp.status_code == status.HTTP_200_OK
        application.refresh_from_db()
        assert application.status == DocApplication.STATUS_COMPLETED
        assert resp.data["colorId"] == GoogleCalendarEventColors.done_color_id()
        sync_mock.assert_called_once()
        update_sync_mock.assert_called_once_with(event_id="evt-overdue-1")

        event = CalendarEvent.objects.get(pk="evt-overdue-1")
        assert event.color_id == GoogleCalendarEventColors.done_color_id()
