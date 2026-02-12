from core.models.async_job import AsyncJob
from rest_framework import serializers


class AsyncJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = AsyncJob
        fields = [
            "id",
            "task_name",
            "status",
            "progress",
            "message",
            "result",
            "error_message",
            "created_at",
            "updated_at",
            "created_by",
        ]
        read_only_fields = fields
