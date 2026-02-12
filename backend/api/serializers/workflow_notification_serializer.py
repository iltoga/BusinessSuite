from rest_framework import serializers

from customer_applications.models import WorkflowNotification


class WorkflowNotificationSerializer(serializers.ModelSerializer):
    application_id = serializers.IntegerField(source="doc_application_id", read_only=True)

    class Meta:
        model = WorkflowNotification
        fields = "__all__"
        read_only_fields = ["created_at", "updated_at", "sent_at", "provider_message", "external_reference"]
