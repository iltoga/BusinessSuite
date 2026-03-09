from core.models import AiModel
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers


class AiModelCapabilitiesSerializer(serializers.Serializer):
    vision = serializers.BooleanField()
    fileUpload = serializers.BooleanField()
    reasoning = serializers.BooleanField()


class AiModelPricingSerializer(serializers.Serializer):
    prompt_price_per_token = serializers.DecimalField(max_digits=20, decimal_places=12, allow_null=True)
    completion_price_per_token = serializers.DecimalField(max_digits=20, decimal_places=12, allow_null=True)
    image_price = serializers.DecimalField(max_digits=20, decimal_places=12, allow_null=True)
    request_price = serializers.DecimalField(max_digits=20, decimal_places=12, allow_null=True)


class AiModelArchitectureSerializer(serializers.Serializer):
    modality = serializers.CharField()
    tokenizer = serializers.CharField()
    instruct_type = serializers.CharField()


class AiModelSerializer(serializers.ModelSerializer):
    capabilities = serializers.SerializerMethodField(read_only=True)
    pricing = serializers.SerializerMethodField(read_only=True)
    architecture = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = AiModel
        fields = [
            "id",
            "provider",
            "model_id",
            "name",
            "description",
            "vision",
            "file_upload",
            "reasoning",
            "context_length",
            "max_completion_tokens",
            "modality",
            "architecture_modality",
            "architecture_tokenizer",
            "instruct_type",
            "prompt_price_per_token",
            "completion_price_per_token",
            "image_price",
            "request_price",
            "top_provider_id",
            "provider_name",
            "supported_parameters",
            "per_request_limits",
            "source",
            "raw_metadata",
            "capabilities",
            "pricing",
            "architecture",
            "created_at",
            "updated_at",
        ]

    @extend_schema_field(AiModelCapabilitiesSerializer)
    def get_capabilities(self, obj: AiModel) -> dict[str, bool]:
        return {
            "vision": bool(obj.vision),
            "fileUpload": bool(obj.file_upload),
            "reasoning": bool(obj.reasoning),
        }

    @extend_schema_field(AiModelPricingSerializer)
    def get_pricing(self, obj: AiModel) -> dict:
        return {
            "prompt_price_per_token": str(obj.prompt_price_per_token) if obj.prompt_price_per_token else None,
            "completion_price_per_token": str(obj.completion_price_per_token) if obj.completion_price_per_token else None,
            "image_price": str(obj.image_price) if obj.image_price else None,
            "request_price": str(obj.request_price) if obj.request_price else None,
        }

    @extend_schema_field(AiModelArchitectureSerializer)
    def get_architecture(self, obj: AiModel) -> dict:
        return {
            "modality": obj.architecture_modality or "",
            "tokenizer": obj.architecture_tokenizer or "",
            "instruct_type": obj.instruct_type or "",
        }
