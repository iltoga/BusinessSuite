"""
FILE_ROLE: Serializer and payload-shaping helpers for the API app.

KEY_COMPONENTS:
- AsyncJobSerializer: Serializer class.

INTERACTIONS:
- Depends on: nearby Django models, services, serializers, and the app packages imported by this module.

AI_GUIDELINES:
- Keep the module focused on serializer validation and representation only.
- Preserve the existing API contract because client code and views depend on these field names.
"""

from api.utils.stream_payloads import camelize_payload
from core.models.async_job import AsyncJob
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers


class AsyncJobSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    jobId = serializers.UUIDField(source="id", read_only=True)
    taskName = serializers.CharField(source="task_name", read_only=True)
    errorMessage = serializers.CharField(source="error_message", read_only=True, allow_null=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)
    createdBy = serializers.IntegerField(source="created_by_id", read_only=True, allow_null=True)
    result = serializers.SerializerMethodField()

    class Meta:
        model = AsyncJob
        fields = [
            "id",
            "jobId",
            "taskName",
            "status",
            "progress",
            "message",
            "result",
            "errorMessage",
            "createdAt",
            "updatedAt",
            "createdBy",
        ]
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_result(self, instance):
        if not isinstance(instance.result, dict):
            return instance.result
        return camelize_payload(instance.result)
