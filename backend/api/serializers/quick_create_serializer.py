"""
FILE_ROLE: Serializer and payload-shaping helpers for the API app.

KEY_COMPONENTS:
- CustomerQuickCreateSerializer: Serializer class.
- CustomerApplicationQuickCreateSerializer: Serializer class.
- ProductQuickCreateSerializer: Serializer class.

INTERACTIONS:
- Depends on: nearby Django models, services, serializers, and the app packages imported by this module.

AI_GUIDELINES:
- Keep the module focused on serializer validation and representation only.
- Preserve the existing API contract because client code and views depend on these field names.
"""

from api.serializers.product_write_utils import apply_pricing_defaults, apply_product_category, normalize_currency_code
from core.models import CountryCode
from core.utils.form_validators import normalize_phone_number
from customers.models import CUSTOMER_TYPE_CHOICES, NOTIFY_BY_CHOICES, Customer
from django.core.exceptions import ValidationError as DjangoValidationError
from products.models import Product, ProductCategory
from rest_framework import serializers


class CustomerQuickCreateSerializer(serializers.Serializer):
    title = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    customer_type = serializers.ChoiceField(choices=CUSTOMER_TYPE_CHOICES, default="person")
    first_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    last_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    company_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    npwp = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    birth_place = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    telephone = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    whatsapp = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    address_bali = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    address_abroad = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    notify_documents_expiration = serializers.BooleanField(required=False, default=False)
    notify_by = serializers.ChoiceField(choices=NOTIFY_BY_CHOICES, required=False, allow_blank=True, allow_null=True)
    passport_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    gender = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    nationality = serializers.SlugRelatedField(
        slug_field="alpha3_code",
        queryset=CountryCode.objects.all(),
        required=False,
        allow_null=True,
    )
    birthdate = serializers.DateField(input_formats=["%Y-%m-%d", "%d/%m/%Y"], required=False, allow_null=True)
    passport_issue_date = serializers.DateField(
        input_formats=["%Y-%m-%d", "%d/%m/%Y"],
        required=False,
        allow_null=True,
    )
    passport_expiration_date = serializers.DateField(
        input_formats=["%Y-%m-%d", "%d/%m/%Y"],
        required=False,
        allow_null=True,
    )

    def to_internal_value(self, data):
        data = data.copy()
        for field_name in [
            "title",
            "first_name",
            "last_name",
            "company_name",
            "npwp",
            "birth_place",
            "email",
            "telephone",
            "whatsapp",
            "address_bali",
            "address_abroad",
            "notify_by",
            "passport_number",
            "gender",
            "nationality",
            "birthdate",
            "passport_issue_date",
            "passport_expiration_date",
        ]:
            if data.get(field_name) == "":
                data[field_name] = None
        return super().to_internal_value(data)

    def validate(self, attrs):
        customer_type = attrs.get("customer_type", "person")
        first_name = (attrs.get("first_name") or "").strip()
        last_name = (attrs.get("last_name") or "").strip()
        company_name = (attrs.get("company_name") or "").strip()

        if customer_type == "person":
            if not first_name or not last_name:
                raise serializers.ValidationError(
                    {"__all__": ["First name and last name are required for person customers."]}
                )
        elif customer_type == "company":
            if not company_name:
                raise serializers.ValidationError({"__all__": ["Company name is required for company customers."]})

        attrs["first_name"] = first_name or None
        attrs["last_name"] = last_name or None
        attrs["company_name"] = company_name or None
        attrs["telephone"] = self._normalize_phone(attrs.get("telephone"))
        attrs["whatsapp"] = self._normalize_phone(attrs.get("whatsapp"))
        attrs["notify_by"] = (attrs.get("notify_by") or "").strip() or None

        instance = Customer(**attrs)
        try:
            instance.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)

        return attrs

    @staticmethod
    def _normalize_phone(value):
        if not value:
            return None
        normalized = normalize_phone_number(value)
        return normalized or None

    def validate_passport_number(self, value):
        """Ensure passport number is unique when present for quick-create."""
        if not value:
            return value
        if Customer.objects.filter(passport_number=value).exists():
            raise serializers.ValidationError("This passport number is already used by another customer.")
        return value


class CustomerApplicationQuickCreateSerializer(serializers.Serializer):
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all())
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    doc_date = serializers.DateField(input_formats=["%Y-%m-%d", "%d/%m/%Y"])
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class ProductQuickCreateSerializer(serializers.Serializer):
    name = serializers.CharField()
    code = serializers.CharField()
    product_category = serializers.PrimaryKeyRelatedField(
        queryset=ProductCategory.objects.all(),
        required=False,
        allow_null=True,
    )
    product_type = serializers.ChoiceField(choices=ProductCategory.PRODUCT_TYPE_CHOICES, default="other")
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    base_price = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    retail_price = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    currency = serializers.RegexField(
        regex=r"^[A-Za-z]{2,3}$",
        required=False,
        allow_null=True,
    )
    validity = serializers.IntegerField(required=False, allow_null=True)
    documents_min_validity = serializers.IntegerField(required=False, allow_null=True)
    required_documents = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    optional_documents = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def to_internal_value(self, data):
        data = data.copy()
        for field in ["validity", "documents_min_validity", "base_price", "retail_price"]:
            if data.get(field) in ["", None]:
                data[field] = None
        return super().to_internal_value(data)

    def validate_code(self, value):
        if Product.objects.filter(code=value).exists():
            raise serializers.ValidationError("A product with this code already exists.")
        return value

    def validate_currency(self, value):
        return normalize_currency_code(value)

    def validate(self, attrs):
        apply_product_category(attrs, instance=None)
        apply_pricing_defaults(attrs, instance=None, set_base_price_default_on_create=True)
        return attrs
