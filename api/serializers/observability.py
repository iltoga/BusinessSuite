from rest_framework import serializers


class ObservabilityLogSerializer(serializers.Serializer):
    timestamp = serializers.DateTimeField(required=False)
    level = serializers.CharField(required=True)
    message = serializers.CharField(required=True)
    stack = serializers.CharField(required=False, allow_blank=True)
    metadata = serializers.JSONField(required=False)
