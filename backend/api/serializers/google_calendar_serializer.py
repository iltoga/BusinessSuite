from rest_framework import serializers


class GoogleCalendarEventSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    summary = serializers.CharField(required=True)
    description = serializers.CharField(required=False, allow_blank=True)
    start_time = serializers.DateTimeField(write_only=True)
    end_time = serializers.DateTimeField(write_only=True)
    start = serializers.JSONField(read_only=True)
    end = serializers.JSONField(read_only=True)
    htmlLink = serializers.URLField(read_only=True)


class GoogleTaskSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    title = serializers.CharField(required=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    due = serializers.DateTimeField(required=False, allow_null=True)
    status = serializers.CharField(read_only=True)
    selfLink = serializers.URLField(read_only=True)
