from core.services.google_calendar_event_colors import GoogleCalendarEventColors
from rest_framework import serializers

COLOR_ID_CHOICES = [(str(i), str(i)) for i in range(1, 12)]


class GoogleCalendarEventSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    summary = serializers.CharField(required=True)
    description = serializers.CharField(required=False, allow_blank=True)
    start_time = serializers.DateTimeField(write_only=True)
    end_time = serializers.DateTimeField(write_only=True)
    attendees = serializers.JSONField(required=False)
    notifications = serializers.JSONField(required=False)
    colorId = serializers.ChoiceField(required=False, choices=COLOR_ID_CHOICES)
    done = serializers.BooleanField(required=False, write_only=True)
    start = serializers.JSONField(read_only=True)
    end = serializers.JSONField(read_only=True)
    htmlLink = serializers.URLField(read_only=True)

    def validate(self, attrs):
        done = attrs.pop("done", None)
        if done is not None and "colorId" in attrs:
            raise serializers.ValidationError("Use either done or colorId, not both.")
        if done is not None:
            attrs["colorId"] = GoogleCalendarEventColors.color_for_done_state(done)
        return attrs


class GoogleTaskSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    title = serializers.CharField(required=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    due = serializers.DateTimeField(required=False, allow_null=True)
    status = serializers.CharField(read_only=True)
    selfLink = serializers.URLField(read_only=True)
