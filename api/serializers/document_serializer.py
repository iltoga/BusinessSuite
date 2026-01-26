from rest_framework import serializers

from api.serializers.document_type_serializer import DocumentTypeSerializer
from customer_applications.models import Document
from products.models.document_type import DocumentType


class DocumentSerializer(serializers.ModelSerializer):
    doc_type = DocumentTypeSerializer(read_only=True)
    doc_type_id = serializers.PrimaryKeyRelatedField(
        source="doc_type",
        queryset=DocumentType.objects.all(),
        write_only=True,
        required=False,
    )

    class Meta:
        model = Document
        fields = [
            "id",
            "doc_application",
            "doc_type",
            "doc_type_id",
            "doc_number",
            "expiration_date",
            "file",
            "file_link",
            "details",
            "completed",
            "metadata",
            "ocr_check",
            "required",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]
        read_only_fields = [
            "doc_application",
            "doc_type",
            "file_link",
            "completed",
            "ocr_check",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]

    def validate_metadata(self, value):
        if isinstance(value, str):
            import json

            try:
                return json.loads(value)
            except json.JSONDecodeError:
                raise serializers.ValidationError("Metadata must be valid JSON")
        return value
