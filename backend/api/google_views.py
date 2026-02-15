from datetime import timedelta
from typing import Any, cast

from api.serializers.google_calendar_serializer import GoogleCalendarEventSerializer, GoogleTaskSerializer
from core.models.calendar_event import CalendarEvent
from core.services.google_calendar_event_colors import GoogleCalendarEventColors
from core.utils.dateutils import calculate_due_date
from core.utils.google_client import GoogleClient
from customer_applications.models import DocApplication
from customer_applications.models.doc_workflow import DocWorkflow
from customer_applications.services.workflow_status_transition_service import (
    WorkflowStatusTransitionError,
    WorkflowStatusTransitionService,
)
from django.db import transaction
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.exceptions import APIException, NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


@extend_schema_view(
    retrieve=extend_schema(
        parameters=[OpenApiParameter("id", OpenApiTypes.STR, OpenApiParameter.PATH, required=True)]
    ),
    update=extend_schema(
        parameters=[OpenApiParameter("id", OpenApiTypes.STR, OpenApiParameter.PATH, required=True)]
    ),
    partial_update=extend_schema(
        parameters=[OpenApiParameter("id", OpenApiTypes.STR, OpenApiParameter.PATH, required=True)]
    ),
    destroy=extend_schema(
        parameters=[OpenApiParameter("id", OpenApiTypes.STR, OpenApiParameter.PATH, required=True)]
    ),
)
class GoogleCalendarViewSet(viewsets.ViewSet):
    """Local-mirror calendar API.

    CRUD operations update `CalendarEvent` records and signals queue asynchronous
    synchronization to Google Calendar through Huey tasks.
    """

    LOCAL_EVENT_ID_PREFIX = "local-app-"

    permission_classes = [IsAuthenticated]
    serializer_class = GoogleCalendarEventSerializer

    def _coerce_bool(self, value):
        if isinstance(value, bool):
            return value
        if value is None:
            return None
        return str(value).strip().lower() in {"true", "1", "yes", "y", "on"}

    def _normalize_calendar_request_data(self, data):
        payload = dict(data)
        if "color_id" in payload and "colorId" not in payload:
            payload["colorId"] = payload["color_id"]
        if "reminders" in payload and "notifications" not in payload:
            payload["notifications"] = payload["reminders"]
        return payload

    def _parse_local_application_id(self, event_id: str):
        if not event_id.startswith(self.LOCAL_EVENT_ID_PREFIX):
            return None
        raw_value = event_id[len(self.LOCAL_EVENT_ID_PREFIX) :]
        if "-" in raw_value:
            raw_value = raw_value.split("-", 1)[0]
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

        direct = queryset.filter(calendar_event_id=event_id).first()
        if direct:
            return direct

        return queryset.filter(calendar_events__google_event_id=event_id).distinct().first()

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

    def _serialize_calendar_event(self, event: CalendarEvent) -> dict:
        data = {
            "id": event.id,
            "summary": event.title,
            "description": event.description or "",
        }
        if event.color_id:
            data["colorId"] = event.color_id
        if event.attendees:
            data["attendees"] = event.attendees
        if event.notifications:
            data["notifications"] = event.notifications

        if event.start_date and event.end_date:
            data["start"] = {"date": event.start_date.isoformat()}
            data["end"] = {"date": event.end_date.isoformat()}
        else:
            data["start"] = {"dateTime": event.start_time.isoformat()} if event.start_time else None
            data["end"] = {"dateTime": event.end_time.isoformat()} if event.end_time else None
            if event.start_time:
                data["startTime"] = event.start_time.isoformat()
            if event.end_time:
                data["endTime"] = event.end_time.isoformat()
        return data

    def _lookup_calendar_event(self, event_identifier: str) -> CalendarEvent | None:
        event = CalendarEvent.objects.filter(pk=event_identifier).first()
        if event:
            return event
        return CalendarEvent.objects.filter(google_event_id=event_identifier).first()

    def _get_calendar_event_or_404(self, event_identifier: str) -> CalendarEvent:
        event = self._lookup_calendar_event(event_identifier)
        if not event:
            raise NotFound("Calendar event not found.")
        return event

    def _apply_calendar_update(self, event: CalendarEvent, validated_data: dict) -> list[str]:
        update_fields: list[str] = []
        if "summary" in validated_data:
            event.title = validated_data["summary"]
            update_fields.append("title")
        if "description" in validated_data:
            event.description = validated_data["description"] or ""
            update_fields.append("description")
        if "start_time" in validated_data:
            event.start_time = validated_data["start_time"]
            event.start_date = None
            update_fields.extend(["start_time", "start_date"])
        if "end_time" in validated_data:
            event.end_time = validated_data["end_time"]
            event.end_date = None
            update_fields.extend(["end_time", "end_date"])
        if "colorId" in validated_data:
            event.color_id = validated_data["colorId"]
            update_fields.append("color_id")
        if "attendees" in validated_data:
            event.attendees = validated_data["attendees"] or []
            update_fields.append("attendees")
        if "notifications" in validated_data:
            event.notifications = validated_data["notifications"] or {}
            update_fields.append("notifications")

        if update_fields:
            event.sync_status = CalendarEvent.SYNC_STATUS_PENDING
            update_fields.append("sync_status")
        return update_fields

    def _serialize_local_event_for_application(
        self,
        application,
        *,
        task=None,
        due_date=None,
        event_id: str | None = None,
        is_done: bool = False,
    ):
        task = task or application.get_next_calendar_task()
        if not task:
            return None

        due_date = (
            due_date
            or application.due_date
            or application.calculate_next_calendar_due_date(start_date=application.doc_date)
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

    def _serialize_local_done_event_for_workflow(self, application, workflow):
        if not workflow.task.add_task_to_calendar or not workflow.due_date:
            return None

        return self._serialize_local_event_for_application(
            application,
            task=workflow.task,
            due_date=workflow.due_date,
            event_id=f"{self.LOCAL_EVENT_ID_PREFIX}{application.id}-workflow-{workflow.id}",
            is_done=True,
        )

    def _list_local_application_events(self):
        applications = (
            DocApplication.objects.select_related("customer", "product")
            .prefetch_related("product__tasks", "workflows__task")
            .filter(
                add_deadlines_to_calendar=True,
            )
            .order_by("id")
        )

        events = []
        for application in applications:
            # Use prefetched data to avoid N+1 DB queries from model helper properties.
            tasks = list(application.product.tasks.all())
            workflows = list(application.workflows.all())
            current_workflow = max(
                workflows,
                key=lambda wf: ((wf.task.step if wf.task else -1), wf.created_at, wf.id),
                default=None,
            )

            next_task = None
            if current_workflow and current_workflow.status == DocApplication.STATUS_COMPLETED:
                next_task = next(
                    (t for t in tasks if t.add_task_to_calendar and t.step > current_workflow.task.step),
                    None,
                )
            elif current_workflow and current_workflow.status == DocApplication.STATUS_REJECTED:
                next_task = None
            elif current_workflow:
                if current_workflow.task and current_workflow.task.add_task_to_calendar:
                    next_task = current_workflow.task
                else:
                    next_task = next(
                        (t for t in tasks if t.add_task_to_calendar and t.step >= current_workflow.task.step),
                        None,
                    )
            else:
                next_task = next((t for t in tasks if t.add_task_to_calendar), None)

            due_date = application.due_date
            if not due_date and next_task:
                due_date = calculate_due_date(
                    application.doc_date or timezone.localdate(),
                    next_task.duration,
                    next_task.duration_is_business_days,
                )

            event = self._serialize_local_event_for_application(application, task=next_task, due_date=due_date)
            if event:
                events.append(event)

            done_workflows = sorted(
                (
                    wf
                    for wf in workflows
                    if wf.status in [DocWorkflow.STATUS_COMPLETED, DocWorkflow.STATUS_REJECTED]
                    and wf.task
                    and wf.task.add_task_to_calendar
                    and wf.due_date
                ),
                key=lambda wf: (wf.due_date, wf.id),
                reverse=True,
            )
            for workflow in done_workflows:
                done_event = self._serialize_local_done_event_for_workflow(application, workflow)
                if done_event:
                    events.append(done_event)

        events.sort(key=lambda item: (item.get("start", {}).get("date"), item.get("summary", "")))
        return events

    @extend_schema(responses={200: GoogleCalendarEventSerializer(many=True)})
    def list(self, request):
        source = (request.query_params.get("source") or "local").strip().lower()
        if source == "local":
            return Response(self._list_local_application_events())
        if source not in {"google", "mirror"}:
            raise ValidationError({"source": "Invalid source. Use 'local', 'mirror', or 'google'."})

        queryset = CalendarEvent.objects.all().order_by("start_date", "start_time", "id")
        return Response([self._serialize_calendar_event(event) for event in queryset])

    @extend_schema(request=GoogleCalendarEventSerializer, responses={201: GoogleCalendarEventSerializer})
    def create(self, request):
        serializer = GoogleCalendarEventSerializer(data=self._normalize_calendar_request_data(request.data))
        serializer.is_valid(raise_exception=True)
        validated_data = cast(dict[str, Any], serializer.validated_data)

        event = CalendarEvent.objects.create(
            source=CalendarEvent.SOURCE_MANUAL,
            title=validated_data["summary"],
            description=validated_data.get("description", ""),
            start_time=validated_data.get("start_time"),
            end_time=validated_data.get("end_time"),
            color_id=validated_data.get("colorId"),
            attendees=validated_data.get("attendees") or [],
            notifications=validated_data.get("notifications") or {},
            sync_status=CalendarEvent.SYNC_STATUS_PENDING,
        )
        return Response(self._serialize_calendar_event(event), status=status.HTTP_201_CREATED)

    @extend_schema(responses={200: GoogleCalendarEventSerializer})
    def retrieve(self, request, pk=None):
        event = self._get_calendar_event_or_404(pk)
        return Response(self._serialize_calendar_event(event))

    @extend_schema(request=GoogleCalendarEventSerializer, responses={200: GoogleCalendarEventSerializer})
    def update(self, request, pk=None):
        serializer = GoogleCalendarEventSerializer(
            data=self._normalize_calendar_request_data(request.data),
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        validated_data = cast(dict[str, Any], serializer.validated_data)

        event = self._get_calendar_event_or_404(pk)
        update_fields = self._apply_calendar_update(event, validated_data)
        if update_fields:
            event.save(update_fields=[*set(update_fields), "updated_at"])
        return Response(self._serialize_calendar_event(event))

    @extend_schema(request=GoogleCalendarEventSerializer, responses={200: GoogleCalendarEventSerializer})
    def partial_update(self, request, pk=None):
        normalized_request_data = self._normalize_calendar_request_data(request.data)
        serializer = GoogleCalendarEventSerializer(data=normalized_request_data, partial=True)
        serializer.is_valid(raise_exception=True)
        validated_data = cast(dict[str, Any], serializer.validated_data)
        done_key_present = "done" in request.data
        done_value = self._coerce_bool(request.data.get("done")) if done_key_present else None

        if done_key_present and done_value is False:
            raise ValidationError({"done": "Calendar events moved to DONE cannot be moved back to TODO."})

        if done_key_present and done_value is True:
            application = self._resolve_application_for_event(event_id=pk)
            if application:
                current_workflow = application.current_workflow
                completed_workflow = (
                    current_workflow if current_workflow and not current_workflow.is_terminal_status else None
                )
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
                    self._queue_application_calendar_sync(
                        application_id=application.id,
                        user_id=request.user.id,
                    )

                mirror_event = self._lookup_calendar_event(pk)
                if mirror_event:
                    mirror_event.color_id = GoogleCalendarEventColors.done_color_id()
                    mirror_event.sync_status = CalendarEvent.SYNC_STATUS_PENDING
                    mirror_event.save(update_fields=["color_id", "sync_status", "updated_at"])
                    return Response(self._serialize_calendar_event(mirror_event))

                local_event = self._serialize_local_event_for_application(
                    application,
                    task=(completed_workflow.task if completed_workflow else None),
                    due_date=(completed_workflow.due_date if completed_workflow else None),
                    event_id=pk,
                    is_done=True,
                )
                if local_event:
                    return Response(local_event)
                return Response({"id": pk, "colorId": GoogleCalendarEventColors.done_color_id()})

            mirror_event = self._get_calendar_event_or_404(pk)
            mirror_event.color_id = GoogleCalendarEventColors.done_color_id()
            mirror_event.sync_status = CalendarEvent.SYNC_STATUS_PENDING
            mirror_event.save(update_fields=["color_id", "sync_status", "updated_at"])
            return Response(self._serialize_calendar_event(mirror_event))

        event = self._get_calendar_event_or_404(pk)
        update_fields = self._apply_calendar_update(event, validated_data)
        if update_fields:
            event.save(update_fields=[*set(update_fields), "updated_at"])
        return Response(self._serialize_calendar_event(event))

    def destroy(self, request, pk=None):
        event = self._get_calendar_event_or_404(pk)
        event.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    retrieve=extend_schema(
        parameters=[OpenApiParameter("id", OpenApiTypes.STR, OpenApiParameter.PATH, required=True)]
    ),
    update=extend_schema(
        parameters=[OpenApiParameter("id", OpenApiTypes.STR, OpenApiParameter.PATH, required=True)]
    ),
    partial_update=extend_schema(
        parameters=[OpenApiParameter("id", OpenApiTypes.STR, OpenApiParameter.PATH, required=True)]
    ),
    destroy=extend_schema(
        parameters=[OpenApiParameter("id", OpenApiTypes.STR, OpenApiParameter.PATH, required=True)]
    ),
)
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
        event_data = cast(dict[str, Any], serializer.validated_data)
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
        validated_data = cast(dict[str, Any], serializer.validated_data)
        tasklist = request.query_params.get("tasklist")
        client = GoogleClient()
        updated = client.update_task(task_id=pk, data=validated_data, tasklist=tasklist)
        return Response(updated)

    @extend_schema(request=GoogleTaskSerializer, responses={200: GoogleTaskSerializer})
    def partial_update(self, request, pk=None):
        serializer = GoogleTaskSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        validated_data = cast(dict[str, Any], serializer.validated_data)
        tasklist = request.query_params.get("tasklist")
        client = GoogleClient()
        updated = client.update_task(task_id=pk, data=validated_data, tasklist=tasklist)
        return Response(updated)

    def destroy(self, request, pk=None):
        tasklist = request.query_params.get("tasklist")
        client = GoogleClient()
        client.delete_task(task_id=pk, tasklist=tasklist)
        return Response(status=status.HTTP_204_NO_CONTENT)
