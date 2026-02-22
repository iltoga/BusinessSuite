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
    is_current_step = serializers.SerializerMethodField()
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

    def get_is_current_step(self, obj) -> bool:
        """Resolve current step from already-loaded siblings to avoid N+1 queries."""
        parent = getattr(self, "parent", None)
        siblings = getattr(parent, "instance", None)

        if siblings is not None:
            sibling_items = getattr(parent, "_sibling_workflows_cache", None)
            if sibling_items is None:
                sibling_items = list(siblings)
                setattr(parent, "_sibling_workflows_cache", sibling_items)

            current_workflow_id = getattr(parent, "_current_workflow_id_cache", None)
            if current_workflow_id is None:
                current = max(
                    sibling_items,
                    key=lambda wf: ((wf.task.step if wf.task else -1), wf.created_at, wf.id),
                    default=None,
                )
                current_workflow_id = current.id if current else None
                setattr(parent, "_current_workflow_id_cache", current_workflow_id)

            return obj.id == current_workflow_id

        return obj.is_current_step
