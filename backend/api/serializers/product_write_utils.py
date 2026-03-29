"""Helpers for normalizing product write payloads before persistence."""

from decimal import Decimal

from products.models import ProductCategory
from rest_framework import serializers


def apply_product_category(attrs: dict, *, instance=None) -> None:
    if "product_category" in attrs:
        if attrs["product_category"] is None:
            raise serializers.ValidationError({"product_category": "Product category is required."})
        attrs.pop("product_type", None)
        return

    product_type = attrs.pop("product_type", None)
    if product_type:
        attrs["product_category"] = ProductCategory.get_default_for_type(product_type)
        return

    if instance is None:
        attrs["product_category"] = ProductCategory.get_default_for_type("other")


def normalize_currency_code(value):
    if value is None:
        return value
    return str(value).strip().upper()


def apply_pricing_defaults(attrs: dict, *, instance=None, set_base_price_default_on_create: bool = False) -> None:
    base_price = attrs.get("base_price")
    if base_price is None and instance is not None:
        base_price = instance.base_price
    elif base_price is None and instance is None and set_base_price_default_on_create:
        base_price = Decimal("0.00")
        attrs["base_price"] = base_price

    retail_price = attrs.get("retail_price")
    if retail_price is None:
        if "base_price" in attrs:
            retail_price = base_price
        elif instance is not None:
            retail_price = instance.retail_price
        else:
            retail_price = base_price

    if base_price is not None and retail_price is not None and retail_price < base_price:
        raise serializers.ValidationError({"retail_price": "Retail price must be greater than or equal to base price."})

    if retail_price is not None:
        attrs["retail_price"] = retail_price
