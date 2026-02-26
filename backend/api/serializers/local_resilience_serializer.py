from rest_framework import serializers

from core.models.local_resilience import LocalResilienceSettings


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
