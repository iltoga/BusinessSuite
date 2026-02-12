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
            "notify_customer",
            "last_step",
        ]


class DocWorkflowSerializer(serializers.ModelSerializer):
    task = TaskSerializer(read_only=True)
    is_current_step = serializers.BooleanField(read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    is_notification_date_reached = serializers.BooleanField(read_only=True)
    has_notes = serializers.BooleanField(read_only=True)

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
            "is_current_step",
            "is_overdue",
            "is_notification_date_reached",
            "has_notes",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]
        read_only_fields = fields
