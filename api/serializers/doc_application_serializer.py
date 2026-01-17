from rest_framework import serializers

from api.serializers.customer_serializer import CustomerSerializer
from api.serializers.product_serializer import ProductSerializer
from customer_applications.models import DocApplication


class DocApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocApplication
        fields = [
            "id",
            "customer",
            "product",
            "doc_date",
            "due_date",
            "status",
            "notes",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["str_field"] = str(instance)
        return representation


class DocApplicationSerializerWithRelations(serializers.ModelSerializer):
    class Meta:
        model = DocApplication
        fields = [
            "id",
            "customer",
            "product",
            "doc_date",
            "due_date",
            "status",
            "notes",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["product"] = ProductSerializer(instance.product).data
        representation["customer"] = CustomerSerializer(instance.customer).data
        representation["str_field"] = str(instance)
        return representation
