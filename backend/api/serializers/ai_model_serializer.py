from core.models import AiModel
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers


class AiModelCapabilitiesSerializer(serializers.Serializer):
    vision = serializers.BooleanField()
    fileUpload = serializers.BooleanField()
    reasoning = serializers.BooleanField()


class AiModelSerializer(serializers.ModelSerializer):
    capabilities = serializers.SerializerMethodField(read_only=True)

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
            "prompt_price_per_token",
            "completion_price_per_token",
            "image_price",
            "request_price",
            "source",
            "raw_metadata",
            "capabilities",
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
