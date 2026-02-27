from core.models.ui_settings import UiSettings
from rest_framework import serializers


class UiSettingsSerializer(serializers.ModelSerializer):
    updatedBy = serializers.SerializerMethodField()

    class Meta:
        model = UiSettings
        fields = [
            "use_overlay_menu",
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
