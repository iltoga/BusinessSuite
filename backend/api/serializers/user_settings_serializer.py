from rest_framework import serializers

from core.models import UserSettings


class UserSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSettings
        fields = ["theme", "dark_mode", "preferences"]
        read_only_fields = []
