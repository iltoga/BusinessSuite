from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.serializers.google_calendar_serializer import GoogleCalendarEventSerializer, GoogleTaskSerializer
from core.utils.google_client import DEFAULT_CALENDAR_ID, GoogleClient


class GoogleCalendarViewSet(viewsets.ViewSet):
    """A simple ViewSet for listing, creating, retrieving, updating and deleting Google Calendar Events."""

    permission_classes = [IsAuthenticated]
    serializer_class = GoogleCalendarEventSerializer

    @extend_schema(responses={200: GoogleCalendarEventSerializer(many=True)})
    def list(self, request):
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
