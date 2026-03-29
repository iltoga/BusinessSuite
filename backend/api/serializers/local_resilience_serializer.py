"""
FILE_ROLE: Serializer and payload-shaping helpers for the API app.

KEY_COMPONENTS:
- LocalResilienceSerializer: Serializer class.

INTERACTIONS:
- Depends on: nearby Django models, services, serializers, and the app packages imported by this module.

AI_GUIDELINES:
- Keep the module focused on serializer validation and representation only.
- Preserve the existing API contract because client code and views depend on these field names.
"""

from core.models.local_resilience import LocalResilienceSettings
from rest_framework import serializers


class LocalResilienceSettingsSerializer(serializers.ModelSerializer):
    updatedBy = serializers.SerializerMethodField()

    class Meta:
        model = LocalResilienceSettings
        fields = [
            "enabled",
            "encryption_required",
            "desktop_mode",
            "vault_epoch",
            "updated_at",
            "updatedBy",
        ]

    def get_updatedBy(self, obj):
        if not obj.updated_by:
            return None
        return {
            "id": obj.updated_by_id,
            "username": getattr(obj.updated_by, "username", None),
            "email": getattr(obj.updated_by, "email", None),
        }
