from customer_applications.models import DocumentCategorizationItem, DocumentCategorizationJob
from rest_framework import serializers


class DocumentCategorizationItemSerializer(serializers.ModelSerializer):
    documentTypeName = serializers.CharField(source="document_type.name", read_only=True, default=None)
    documentId = serializers.IntegerField(source="document.id", read_only=True, default=None)

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
            "errorMessage",
            "createdAt",
            "updatedAt",
        ]
        extra_kwargs = {
            "sortIndex": {"source": "sort_index"},
            "errorMessage": {"source": "error_message"},
            "createdAt": {"source": "created_at"},
            "updatedAt": {"source": "updated_at"},
        }


class DocumentCategorizationJobSerializer(serializers.ModelSerializer):
    items = DocumentCategorizationItemSerializer(many=True, read_only=True)
    docApplicationId = serializers.IntegerField(source="doc_application_id", read_only=True)

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
        extra_kwargs = {
            "totalFiles": {"source": "total_files"},
            "processedFiles": {"source": "processed_files"},
            "successCount": {"source": "success_count"},
            "errorCount": {"source": "error_count"},
            "requestParams": {"source": "request_params"},
            "errorMessage": {"source": "error_message"},
            "createdAt": {"source": "created_at"},
            "updatedAt": {"source": "updated_at"},
        }


class CategorizationApplyItemSerializer(serializers.Serializer):
    itemId = serializers.UUIDField()
    documentId = serializers.IntegerField()


class CategorizationApplySerializer(serializers.Serializer):
    mappings = CategorizationApplyItemSerializer(many=True)
