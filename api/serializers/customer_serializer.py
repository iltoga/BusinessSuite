from rest_framework import serializers

from customers.models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    """Serializer for Customer model.

    Note: This serializer exposes all model fields.
    Keep `fields = '__all__'` to avoid missing fields from the model.
    """

    class Meta:
        model = Customer
        fields = "__all__"
