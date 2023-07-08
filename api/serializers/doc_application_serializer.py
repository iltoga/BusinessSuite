from rest_framework import serializers

from customer_applications.models import DocApplication


class DocApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocApplication
        fields = "__all__"

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["str_field"] = str(instance)
        return representation
