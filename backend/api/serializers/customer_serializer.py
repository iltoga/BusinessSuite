"""
FILE_ROLE: Serializer and payload-shaping helpers for the API app.

KEY_COMPONENTS:
- CustomerSerializer: Serializer class.

INTERACTIONS:
- Depends on: nearby Django models, services, serializers, and the app packages imported by this module.

AI_GUIDELINES:
- Keep the module focused on serializer validation and representation only.
- Preserve the existing API contract because client code and views depend on these field names.
"""

from datetime import timedelta
from typing import Optional

from customers.models import Customer
from customers.services.passport_file_processing import PassportFileProcessingError, normalize_passport_file
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers


class CustomerSerializer(serializers.ModelSerializer):
    """Serializer for Customer model.

    Note: This serializer exposes all model fields.
    Keep `fields = '__all__'` to avoid missing fields from the model.
    """

    passport_expired = serializers.SerializerMethodField()
    passport_expiring_soon = serializers.SerializerMethodField()
    gender_display = serializers.SerializerMethodField()
    nationality_name = serializers.SerializerMethodField()
    nationality_code = serializers.SerializerMethodField()
    # Explicit method fields for derived read-only values so we can provide type hints
    full_name = serializers.SerializerMethodField()
    full_name_with_company = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = [
            "id",
            "created_at",
            "updated_at",
            "title",
            "customer_type",
            "first_name",
            "last_name",
            "company_name",
            "email",
            "telephone",
            "whatsapp",
            "telegram",
            "facebook",
            "instagram",
            "twitter",
            "npwp",
            "nationality",
            "birthdate",
            "birth_place",
            "passport_number",
            "passport_issue_date",
            "passport_expiration_date",
            "passport_file",
            "passport_metadata",
            "passport_expired",
            "passport_expiring_soon",
            "gender",
            "gender_display",
            "nationality_name",
            "nationality_code",
            "address_bali",
            "address_abroad",
            "notify_documents_expiration",
            "notify_by",
            "active",
            "full_name",
            "full_name_with_company",
        ]
        read_only_fields = ["created_at", "updated_at"]

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_passport_expired(self, obj) -> bool:
        if not obj.passport_expiration_date:
            return False
        return obj.passport_expiration_date < timezone.now().date()

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_passport_expiring_soon(self, obj) -> bool:
        if not obj.passport_expiration_date:
            return False
        now = timezone.now().date()
        threshold = now + timedelta(days=183)
        return now <= obj.passport_expiration_date <= threshold

    @extend_schema_field(OpenApiTypes.STR)
    def get_gender_display(self, obj) -> str:
        return obj.get_gender_display()

    @extend_schema_field(OpenApiTypes.STR)
    def get_nationality_name(self, obj) -> str:
        if not obj.nationality:
            return ""
        return obj.nationality.country_idn or obj.nationality.country

    @extend_schema_field(OpenApiTypes.STR)
    def get_nationality_code(self, obj) -> str:
        return obj.nationality.alpha3_code if obj.nationality else ""

    @extend_schema_field(OpenApiTypes.STR)
    def get_full_name(self, obj) -> str:
        return obj.full_name

    @extend_schema_field(OpenApiTypes.STR)
    def get_full_name_with_company(self, obj) -> str:
        return obj.full_name_with_company

    def validate_passport_number(self, value):
        """Ensure passport number is unique when present."""
        if not value:
            return value
        qs = Customer.objects.filter(passport_number=value)
        # exclude self if updating
        if getattr(self, "instance", None):
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("This passport number is already used by another customer.")
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        passport_file = attrs.get("passport_file")
        if passport_file:
            try:
                attrs["passport_file"] = normalize_passport_file(passport_file)
            except PassportFileProcessingError as exc:
                raise serializers.ValidationError({"passport_file": [str(exc)]}) from exc

        # Run model-level clean() so business invariants (e.g. notify_by required
        # when notify_documents_expiration is set) are enforced at the API boundary.
        instance = self.instance or Customer(**attrs)
        if self.instance:
            for field, value in attrs.items():
                setattr(instance, field, value)
        try:
            instance.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)

        return attrs
