from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from api.serializers.document_type_serializer import DocumentTypeSerializer
from customer_applications.hooks.registry import hook_registry
from customer_applications.models import Document
from products.models.document_type import DocumentType


class DocumentActionSerializer(serializers.Serializer):
    """Serializer for document hook actions."""

    name = serializers.CharField()
    label = serializers.CharField()
    icon = serializers.CharField(allow_blank=True)
    css_class = serializers.CharField()


class DocumentSerializer(serializers.ModelSerializer):
    doc_type = DocumentTypeSerializer(read_only=True)
    doc_type_id = serializers.PrimaryKeyRelatedField(
        source="doc_type",
        queryset=DocumentType.objects.all(),
        write_only=True,
        required=False,
    )
    updated_by_username = serializers.SerializerMethodField()
    created_by_username = serializers.SerializerMethodField()
    extra_actions = serializers.SerializerMethodField()

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
            "updated_by_username",
            "created_by_username",
            "extra_actions",
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
            "updated_by_username",
            "created_by_username",
            "extra_actions",
        ]

    def get_updated_by_username(self, obj) -> str | None:
        """Return the username of the user who last updated the document."""
        if obj.updated_by:
            return obj.updated_by.username
        return None

    def get_created_by_username(self, obj) -> str | None:
        """Return the username of the user who created the document."""
        if obj.created_by:
            return obj.created_by.username
        return None

    @extend_schema_field(DocumentActionSerializer(many=True))
    def get_extra_actions(self, obj):
        """Return hook actions available for this document type."""
        if not obj.doc_type:
            return []
        hook = hook_registry.get_hook(obj.doc_type.name)
        if not hook:
            return []
        actions = hook.get_extra_actions()
        return DocumentActionSerializer(actions, many=True).data

    def validate_metadata(self, value):
        if isinstance(value, str):
            import json

            try:
                return json.loads(value)
            except json.JSONDecodeError:
                raise serializers.ValidationError("Metadata must be valid JSON")
        return value
