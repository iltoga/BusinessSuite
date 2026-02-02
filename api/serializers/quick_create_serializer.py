from decimal import Decimal

from rest_framework import serializers

from core.models import CountryCode
from core.utils.dateutils import parse_date_field
from core.utils.form_validators import normalize_phone_number
from customers.models import CUSTOMER_TYPE_CHOICES, Customer
from products.models import Product


class CustomerQuickCreateSerializer(serializers.Serializer):
    title = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    customer_type = serializers.ChoiceField(choices=CUSTOMER_TYPE_CHOICES, default="person")
    first_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    last_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    company_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    npwp = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    birth_place = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    email = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    telephone = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    whatsapp = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    address_bali = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    address_abroad = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    passport_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    gender = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    nationality = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    birthdate = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    passport_issue_date = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    passport_expiration_date = serializers.CharField(required=False, allow_blank=True, allow_null=True)

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

        self._apply_parsed_date(attrs, "birthdate")
        self._apply_parsed_date(attrs, "passport_issue_date")
        self._apply_parsed_date(attrs, "passport_expiration_date")

        nationality_code = attrs.get("nationality")
        if nationality_code:
            nationality = CountryCode.objects.filter(alpha3_code=nationality_code).first()
            if nationality:
                attrs["nationality"] = nationality
            else:
                attrs.pop("nationality", None)
        else:
            attrs.pop("nationality", None)

        return attrs

    @staticmethod
    def _normalize_phone(value):
        if not value:
            return None
        normalized = normalize_phone_number(value)
        return normalized or None

    @staticmethod
    def _apply_parsed_date(attrs, field_name):
        raw_value = attrs.get(field_name)
        parsed_value = parse_date_field(raw_value)
        if parsed_value:
            attrs[field_name] = parsed_value
        else:
            attrs.pop(field_name, None)

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
    product_type = serializers.ChoiceField(choices=Product.PRODUCT_TYPE_CHOICES, default="other")
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    base_price = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    validity = serializers.IntegerField(required=False, allow_null=True)
    documents_min_validity = serializers.IntegerField(required=False, allow_null=True)
    required_documents = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    optional_documents = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def to_internal_value(self, data):
        data = data.copy()
        for field in ["validity", "documents_min_validity", "base_price"]:
            if data.get(field) in ["", None]:
                data[field] = None
        return super().to_internal_value(data)

    def validate_code(self, value):
        if Product.objects.filter(code=value).exists():
            raise serializers.ValidationError("A product with this code already exists.")
        return value

    def validate(self, attrs):
        if attrs.get("base_price") is None:
            attrs["base_price"] = Decimal("0.00")
        return attrs
