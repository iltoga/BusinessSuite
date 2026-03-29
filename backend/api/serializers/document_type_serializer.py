"""
FILE_ROLE: Serializer and payload-shaping helpers for the API app.

KEY_COMPONENTS:
- DocumentTypeSerializer: Serializer class.

INTERACTIONS:
- Depends on: nearby Django models, services, serializers, and the app packages imported by this module.

AI_GUIDELINES:
- Keep the module focused on serializer validation and representation only.
- Preserve the existing API contract because client code and views depend on these field names.
"""

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
            "auto_generation",
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
            "ai_structured_output",
            "is_in_required_documents",
        ]
