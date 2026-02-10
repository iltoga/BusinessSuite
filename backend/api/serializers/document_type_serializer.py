from rest_framework import serializers

from products.models.document_type import DocumentType


class DocumentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentType
        fields = [
            "id",
            "name",
            "description",
            "has_ocr_check",
            "has_expiration_date",
            "has_doc_number",
            "has_file",
            "has_details",
            "is_in_required_documents",
        ]
