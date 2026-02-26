from api.serializers.document_type_serializer import DocumentTypeSerializer
from customer_applications.hooks.registry import hook_registry
from customer_applications.models import Document
from drf_spectacular.utils import extend_schema_field
from products.models.document_type import DocumentType
from rest_framework import serializers


class DocumentActionSerializer(serializers.Serializer):
    """Serializer for document hook actions."""

    name = serializers.CharField()
    label = serializers.CharField()
    icon = serializers.CharField(allow_blank=True)
    css_class = serializers.CharField()


class DocumentMergeSerializer(serializers.Serializer):
    """Serializer for merging documents."""

    document_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        help_text="Ordered list of document IDs to merge.",
    )


class DocumentSerializer(serializers.ModelSerializer):
    doc_type = DocumentTypeSerializer(read_only=True)
    file = serializers.SerializerMethodField()
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
            "ai_validation",
            "required",
            "ai_validation_status",
            "ai_validation_result",
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
            "ai_validation",
            "ai_validation_status",
            "ai_validation_result",
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

    def get_file(self, obj) -> str | None:
        """
        Return file URL while allowing detail responses to skip expensive storage URL generation.

        When `prefer_cached_file_url` is enabled in serializer context, use the persisted
        `file_link` first and only fall back to storage-generated URLs if needed.
        """
        if not obj.file:
            return None

        if self.context.get("prefer_cached_file_url") and obj.file_link:
            return obj.file_link

        try:
            return obj.file.url
        except Exception:
            # Keep response backward-compatible even if storage URL generation fails.
            return obj.file_link or obj.file.name

    @extend_schema_field(DocumentActionSerializer(many=True))
    def get_extra_actions(self, obj):
        """Return hook actions available for this document type."""
        if not obj.doc_type:
            return []
        cache = self.context.setdefault("_extra_actions_by_doc_type", {})
        cache_key = obj.doc_type_id
        if cache_key in cache:
            return cache[cache_key]

        hook = hook_registry.get_hook(obj.doc_type.name)
        if not hook:
            cache[cache_key] = []
            return []
        actions = hook.get_extra_actions()
        serialized = DocumentActionSerializer(actions, many=True).data
        cache[cache_key] = serialized
        return serialized

    def validate_metadata(self, value):
        if isinstance(value, str):
            import json

            try:
                return json.loads(value)
            except json.JSONDecodeError:
                raise serializers.ValidationError("Metadata must be valid JSON")
        return value
