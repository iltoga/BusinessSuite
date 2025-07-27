from rest_framework import serializers

from api.serializers.customer_serializer import CustomerSerializer
from api.serializers.product_serializer import ProductSerializer
from customer_applications.models import DocApplication


class DocApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocApplication
        fields = "__all__"

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["str_field"] = str(instance)
        return representation


class DocApplicationSerializerWithRelations(serializers.ModelSerializer):
    class Meta:
        model = DocApplication
        fields = "__all__"

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["product"] = ProductSerializer(instance.product).data
        representation["customer"] = CustomerSerializer(instance.customer).data
        representation["str_field"] = str(instance)
        return representation
