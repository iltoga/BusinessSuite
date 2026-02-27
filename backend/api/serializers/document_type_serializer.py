from products.models.document_type import DocumentType
from rest_framework import serializers


class DocumentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentType
        fields = [
            "id",
            "name",
            "description",
            "deprecated",
            "ai_validation",
            "has_expiration_date",
            "expiring_threshold_days",
            "is_stay_permit",
            "has_doc_number",
            "has_file",
            "has_details",
            "validation_rule_regex",
            "validation_rule_ai_positive",
            "validation_rule_ai_negative",
            "is_in_required_documents",
        ]
