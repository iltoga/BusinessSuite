from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from customers.models import Customer


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

    def get_passport_expired(self, obj):
        if not obj.passport_expiration_date:
            return False
        return obj.passport_expiration_date < timezone.now().date()

    def get_passport_expiring_soon(self, obj):
        if not obj.passport_expiration_date:
            return False
        now = timezone.now().date()
        threshold = now + timedelta(days=183)
        return now <= obj.passport_expiration_date <= threshold

    def get_gender_display(self, obj):
        return obj.get_gender_display()

    def get_nationality_name(self, obj):
        if not obj.nationality:
            return ""
        return obj.nationality.country_idn or obj.nationality.country

    def get_nationality_code(self, obj):
        return obj.nationality.alpha3_code if obj.nationality else ""

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
