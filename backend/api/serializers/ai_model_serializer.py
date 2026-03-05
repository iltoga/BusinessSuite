from rest_framework import serializers

from core.models import AiModel


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

    def get_capabilities(self, obj: AiModel):
        return {
            "vision": bool(obj.vision),
            "fileUpload": bool(obj.file_upload),
            "reasoning": bool(obj.reasoning),
        }
