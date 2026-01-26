from rest_framework import serializers

from api.serializers.customer_serializer import CustomerSerializer
from api.serializers.doc_workflow_serializer import DocWorkflowSerializer
from api.serializers.document_serializer import DocumentSerializer
from api.serializers.product_serializer import ProductSerializer
from customer_applications.models import DocApplication


class DocApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocApplication
        fields = [
            "id",
            "customer",
            "product",
            "doc_date",
            "due_date",
            "status",
            "notes",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["str_field"] = str(instance)
        return representation


class DocApplicationSerializerWithRelations(serializers.ModelSerializer):
    class Meta:
        model = DocApplication
        fields = [
            "id",
            "customer",
            "product",
            "doc_date",
            "due_date",
            "status",
            "notes",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["product"] = ProductSerializer(instance.product).data
        representation["customer"] = CustomerSerializer(instance.customer).data
        representation["str_field"] = str(instance)
        return representation


class DocApplicationDetailSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    customer = CustomerSerializer(read_only=True)
    documents = serializers.SerializerMethodField()
    workflows = DocWorkflowSerializer(many=True, read_only=True)
    str_field = serializers.SerializerMethodField()

    class Meta:
        model = DocApplication
        fields = [
            "id",
            "customer",
            "product",
            "doc_date",
            "due_date",
            "status",
            "notes",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "documents",
            "workflows",
            "str_field",
        ]
        read_only_fields = fields

    def get_documents(self, instance):
        documents = instance.documents.select_related("doc_type").all()
        return DocumentSerializer(documents, many=True).data

    def get_str_field(self, instance):
        return str(instance)
