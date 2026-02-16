from rest_framework import serializers

from core.models import Holiday


class HolidaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Holiday
        fields = ["id", "name", "date", "is_weekend", "description", "country"]
        read_only_fields = ["id", "is_weekend"]
