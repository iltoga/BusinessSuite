from rest_framework import serializers

from products.models import Product


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "code",
            "description",
            "immigration_id",
            "base_price",
            "product_type",
            "validity",
            "required_documents",
            "optional_documents",
            "documents_min_validity",
        ]
