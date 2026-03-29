"""
FILE_ROLE: Serializer and payload-shaping helpers for the API app.

KEY_COMPONENTS:
- WorkflowNotificationSerializer: Serializer class.

INTERACTIONS:
- Depends on: nearby Django models, services, serializers, and the app packages imported by this module.

AI_GUIDELINES:
- Keep the module focused on serializer validation and representation only.
- Preserve the existing API contract because client code and views depend on these field names.
"""

from customer_applications.models import WorkflowNotification
from rest_framework import serializers


class WorkflowNotificationSerializer(serializers.ModelSerializer):
    application_id = serializers.IntegerField(source="doc_application_id", read_only=True)

    class Meta:
        model = WorkflowNotification
        fields = "__all__"
        read_only_fields = ["created_at", "updated_at", "sent_at", "provider_message", "external_reference"]
