from rest_framework import serializers

from customer_applications.models import DocWorkflow
from products.models.task import Task


class TaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = [
            "id",
            "name",
            "step",
            "duration",
            "duration_is_business_days",
            "notify_days_before",
            "last_step",
        ]


class DocWorkflowSerializer(serializers.ModelSerializer):
    task = TaskSerializer(read_only=True)

    class Meta:
        model = DocWorkflow
        fields = [
            "id",
            "task",
            "start_date",
            "completion_date",
            "due_date",
            "status",
            "notes",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]
        read_only_fields = fields
