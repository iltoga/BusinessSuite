from core.models.async_job import AsyncJob
from api.utils.stream_payloads import camelize_payload
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes


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
