"""Serializers for holiday lookup and calendar display payloads."""

from core.models import Holiday
from rest_framework import serializers


class HolidaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Holiday
        fields = ["id", "name", "date", "is_weekend", "description", "country"]
        read_only_fields = ["id", "is_weekend"]
