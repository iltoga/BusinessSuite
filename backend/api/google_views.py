from datetime import timedelta

from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.serializers.google_calendar_serializer import GoogleCalendarEventSerializer, GoogleTaskSerializer
from core.services.google_calendar_event_colors import GoogleCalendarEventColors
from core.utils.google_client import DEFAULT_CALENDAR_ID, GoogleClient
from customer_applications.models import DocApplication
from customer_applications.services.workflow_status_transition_service import (
    WorkflowStatusTransitionError,
    WorkflowStatusTransitionService,
)
from django.db import transaction


class GoogleCalendarViewSet(viewsets.ViewSet):
    """A simple ViewSet for listing, creating, retrieving, updating and deleting Google Calendar Events."""

    LOCAL_EVENT_ID_PREFIX = "local-app-"

    permission_classes = [IsAuthenticated]
    serializer_class = GoogleCalendarEventSerializer

    def _coerce_bool(self, value):
        if isinstance(value, bool):
            return value
        if value is None:
            return None
        return str(value).strip().lower() in {"true", "1", "yes", "y", "on"}

    def _parse_local_application_id(self, event_id: str):
        if not event_id.startswith(self.LOCAL_EVENT_ID_PREFIX):
            return None
        raw_value = event_id[len(self.LOCAL_EVENT_ID_PREFIX) :]
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            return None

    def _resolve_application_for_event(self, event_id: str):
        local_app_id = self._parse_local_application_id(event_id)
        queryset = DocApplication.objects.select_related("customer", "product").prefetch_related(
            "product__tasks",
            "workflows__task",
        )

        if local_app_id is not None:
            return queryset.filter(id=local_app_id).first()

        return queryset.filter(calendar_event_id=event_id).first()

    def _queue_application_calendar_sync(
        self,
        *,
        application_id: int,
        user_id: int,
        previous_due_date=None,
        start_date=None,
    ):
        from customer_applications.tasks import SYNC_ACTION_UPSERT, sync_application_calendar_task

        previous_due_date_value = previous_due_date.isoformat() if previous_due_date else None
        start_date_value = start_date.isoformat() if start_date else None

        transaction.on_commit(
            lambda: sync_application_calendar_task(
                application_id=application_id,
                user_id=user_id,
                action=SYNC_ACTION_UPSERT,
                previous_due_date=previous_due_date_value,
                start_date=start_date_value,
            )
        )

    def _serialize_local_event_for_application(
        self,
        application,
        *,
        task=None,
        event_id: str | None = None,
        is_done: bool = False,
    ):
        task = task or application.get_next_calendar_task()
        if not task:
            return None

        due_date = application.due_date or application.calculate_next_calendar_due_date(
            start_date=application.doc_date
        )
        event_id = event_id or application.calendar_event_id or f"{self.LOCAL_EVENT_ID_PREFIX}{application.id}"
        color_id = GoogleCalendarEventColors.done_color_id() if is_done else GoogleCalendarEventColors.todo_color_id()
        notes = application.notes or "-"

        return {
            "id": event_id,
            "summary": f"[Application #{application.id}] {application.customer.full_name} - {task.name}",
            "description": (
                f"Application #{application.id}\n"
                f"Customer: {application.customer.full_name}\n"
                f"Product: {application.product.name}\n"
                f"Task: {task.name}\n"
                f"Application Notes: {notes}"
            ),
            "start": {"date": due_date.isoformat()},
            "end": {"date": (due_date + timedelta(days=1)).isoformat()},
            "colorId": color_id,
            "extendedProperties": {
                "private": {
                    "revisbali_entity": "customer_application",
                    "revisbali_customer_application_id": str(application.id),
                }
            },
        }

    def _list_local_application_events(self):
        applications = (
            DocApplication.objects.select_related("customer", "product")
            .prefetch_related("product__tasks", "workflows__task")
            .filter(
                add_deadlines_to_calendar=True,
                due_date__isnull=False,
                status__in=[DocApplication.STATUS_PENDING, DocApplication.STATUS_PROCESSING],
            )
            .order_by("due_date", "id")
        )

        events = []
        for application in applications:
            task = application.get_next_calendar_task()
            if not task:
                continue
            event = self._serialize_local_event_for_application(application, task=task)
            if event:
                events.append(event)
        return events

    @extend_schema(responses={200: GoogleCalendarEventSerializer(many=True)})
    def list(self, request):
        source = (request.query_params.get("source") or "local").strip().lower()
        if source == "local":
            return Response(self._list_local_application_events())
        if source != "google":
            raise ValidationError({"source": "Invalid source. Use 'local' or 'google'."})

        calendar_id = request.query_params.get("calendar_id")
        client = GoogleClient()
        try:
            events = client.list_events(calendar_id=calendar_id)
            return Response(events)
        except Exception as e:
            # Use DEFAULT_CALENDAR_ID if no calendar_id was provided
            used_id = calendar_id or DEFAULT_CALENDAR_ID
            if "notFound" in str(e) or "404" in str(e):
                raise APIException(
                    f"Calendar '{used_id}' not found. Make sure you shared your Google Calendar with the service account email."
                )
            raise APIException(f"Failed to list events: {str(e)}")

    @extend_schema(request=GoogleCalendarEventSerializer, responses={201: GoogleCalendarEventSerializer})
    def create(self, request):
        serializer = GoogleCalendarEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        calendar_id = request.query_params.get("calendar_id")
        client = GoogleClient()
        try:
            event = client.create_event(serializer.validated_data, calendar_id=calendar_id)
            return Response(event, status=status.HTTP_201_CREATED)
        except Exception as e:
            used_id = calendar_id or DEFAULT_CALENDAR_ID
            if "notFound" in str(e) or "404" in str(e):
                raise APIException(
                    f"Calendar '{used_id}' not found. Make sure you shared your Google Calendar with the service account email."
                )
            raise APIException(f"Failed to create event: {str(e)}")

    @extend_schema(responses={200: GoogleCalendarEventSerializer})
    def retrieve(self, request, pk=None):
        calendar_id = request.query_params.get("calendar_id")
        client = GoogleClient()
        event = client.get_event(event_id=pk, calendar_id=calendar_id)
        return Response(event)

    @extend_schema(request=GoogleCalendarEventSerializer, responses={200: GoogleCalendarEventSerializer})
    def update(self, request, pk=None):
        """Full update (PUT) - delegates to patch behavior in Google API."""
        serializer = GoogleCalendarEventSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        calendar_id = request.query_params.get("calendar_id")
        client = GoogleClient()
        updated = client.update_event(event_id=pk, data=serializer.validated_data, calendar_id=calendar_id)
        return Response(updated)

    @extend_schema(request=GoogleCalendarEventSerializer, responses={200: GoogleCalendarEventSerializer})
    def partial_update(self, request, pk=None):
        serializer = GoogleCalendarEventSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        done_key_present = "done" in request.data
        done_value = self._coerce_bool(request.data.get("done")) if done_key_present else None

        if done_key_present and done_value is False:
            raise ValidationError({"done": "Calendar events moved to DONE cannot be moved back to TODO."})

        if done_key_present and done_value is True:
            application = self._resolve_application_for_event(event_id=pk)
            if application:
                current_workflow = application.current_workflow
                if current_workflow and not current_workflow.is_terminal_status:
                    try:
                        transition_result = WorkflowStatusTransitionService().transition(
                            workflow=current_workflow,
                            status_value=current_workflow.STATUS_COMPLETED,
                            user=request.user,
                        )
                    except WorkflowStatusTransitionError as exc:
                        raise ValidationError({"done": str(exc)})

                    if transition_result.changed:
                        self._queue_application_calendar_sync(
                            application_id=transition_result.application.id,
                            user_id=request.user.id,
                            previous_due_date=transition_result.previous_due_date,
                            start_date=transition_result.next_start_date,
                        )
                else:
                    # Keep Google Calendar eventually consistent with local application state.
                    self._queue_application_calendar_sync(
                        application_id=application.id,
                        user_id=request.user.id,
                    )

                local_event = self._serialize_local_event_for_application(application, event_id=pk, is_done=True)
                if local_event:
                    return Response(local_event)
                return Response({"id": pk, "colorId": GoogleCalendarEventColors.done_color_id()})

        calendar_id = request.query_params.get("calendar_id")
        client = GoogleClient()
        updated = client.update_event(event_id=pk, data=serializer.validated_data, calendar_id=calendar_id)
        return Response(updated)

    def destroy(self, request, pk=None):
        calendar_id = request.query_params.get("calendar_id")
        client = GoogleClient()
        client.delete_event(event_id=pk, calendar_id=calendar_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class GoogleTasksViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = GoogleTaskSerializer

    @extend_schema(responses={200: GoogleTaskSerializer(many=True)})
    def list(self, request):
        tasklist = request.query_params.get("tasklist")
        client = GoogleClient()
        try:
            tasks = client.list_tasks(tasklist=tasklist)
            return Response(tasks)
        except Exception as e:
            raise APIException(f"Failed to list tasks: {str(e)}")

    @extend_schema(request=GoogleTaskSerializer, responses={201: GoogleTaskSerializer})
    def create(self, request):
        serializer = GoogleTaskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tasklist = request.query_params.get("tasklist")
        client = GoogleClient()
        event_data = serializer.validated_data
        try:
            task = client.create_task(
                title=event_data.get("title"),
                notes=event_data.get("notes", ""),
                due=event_data.get("due"),
                tasklist=tasklist,
            )
            return Response(task, status=status.HTTP_201_CREATED)
        except Exception as e:
            raise APIException(f"Failed to create task: {str(e)}")

    @extend_schema(responses={200: GoogleTaskSerializer})
    def retrieve(self, request, pk=None):
        tasklist = request.query_params.get("tasklist")
        client = GoogleClient()
        task = client.get_task(task_id=pk, tasklist=tasklist)
        return Response(task)

    @extend_schema(request=GoogleTaskSerializer, responses={200: GoogleTaskSerializer})
    def update(self, request, pk=None):
        serializer = GoogleTaskSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        tasklist = request.query_params.get("tasklist")
        client = GoogleClient()
        updated = client.update_task(task_id=pk, data=serializer.validated_data, tasklist=tasklist)
        return Response(updated)

    @extend_schema(request=GoogleTaskSerializer, responses={200: GoogleTaskSerializer})
    def partial_update(self, request, pk=None):
        serializer = GoogleTaskSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        tasklist = request.query_params.get("tasklist")
        client = GoogleClient()
        updated = client.update_task(task_id=pk, data=serializer.validated_data, tasklist=tasklist)
        return Response(updated)

    def destroy(self, request, pk=None):
        tasklist = request.query_params.get("tasklist")
        client = GoogleClient()
        client.delete_task(task_id=pk, tasklist=tasklist)
        return Response(status=status.HTTP_204_NO_CONTENT)
