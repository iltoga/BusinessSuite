from customer_applications.models import DocumentCategorizationItem, DocumentCategorizationJob
from api.utils.stream_payloads import camelize_payload
from rest_framework import serializers
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field


class DocumentCategorizationItemSerializer(serializers.ModelSerializer):
    documentTypeName = serializers.CharField(source="document_type.name", read_only=True, default=None)
    documentId = serializers.IntegerField(source="document.id", read_only=True, default=None)
    sortIndex = serializers.IntegerField(source="sort_index", read_only=True)
    result = serializers.SerializerMethodField()
    validationStatus = serializers.CharField(source="validation_status", read_only=True, allow_null=True)
    validationResult = serializers.SerializerMethodField()
    errorMessage = serializers.CharField(source="error_message", read_only=True, allow_null=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)

    class Meta:
        model = DocumentCategorizationItem
        fields = [
            "id",
            "sortIndex",
            "filename",
            "status",
            "documentTypeName",
            "documentId",
            "confidence",
            "result",
            "validationStatus",
            "validationResult",
            "errorMessage",
            "createdAt",
            "updatedAt",
        ]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_result(self, instance):
        if not isinstance(instance.result, dict):
            return instance.result
        return camelize_payload(instance.result)

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_validationResult(self, instance):
        if not isinstance(instance.validation_result, dict):
            return instance.validation_result
        return camelize_payload(instance.validation_result)


class DocumentCategorizationJobSerializer(serializers.ModelSerializer):
    items = DocumentCategorizationItemSerializer(many=True, read_only=True)
    docApplicationId = serializers.IntegerField(source="doc_application_id", read_only=True)
    totalFiles = serializers.IntegerField(source="total_files", read_only=True)
    processedFiles = serializers.IntegerField(source="processed_files", read_only=True)
    successCount = serializers.IntegerField(source="success_count", read_only=True)
    errorCount = serializers.IntegerField(source="error_count", read_only=True)
    requestParams = serializers.JSONField(source="request_params", read_only=True)
    result = serializers.SerializerMethodField()
    errorMessage = serializers.CharField(source="error_message", read_only=True, allow_null=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)

    class Meta:
        model = DocumentCategorizationJob
        fields = [
            "id",
            "docApplicationId",
            "status",
            "progress",
            "totalFiles",
            "processedFiles",
            "successCount",
            "errorCount",
            "requestParams",
            "result",
            "errorMessage",
            "createdAt",
            "updatedAt",
            "items",
        ]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_result(self, instance):
        if not isinstance(instance.result, dict):
            return instance.result
        return camelize_payload(instance.result)


class CategorizationApplyItemSerializer(serializers.Serializer):
    item_id = serializers.UUIDField()
    document_id = serializers.IntegerField()


class CategorizationApplySerializer(serializers.Serializer):
    mappings = CategorizationApplyItemSerializer(many=True)
