"""
FILE_ROLE: Serializer and payload-shaping helpers for the API app.

KEY_COMPONENTS:
- AiModelCapabilitiesSerializer: Serializer class.
- AiModelPricingSerializer: Serializer class.
- AiModelPricingDisplaySerializer: Serializer class.
- AiModelArchitectureSerializer: Serializer class.
- AiModelSerializer: Serializer class.

INTERACTIONS:
- Depends on: nearby Django models, services, serializers, and the app packages imported by this module.

AI_GUIDELINES:
- Keep the module focused on serializer validation and representation only.
- Preserve the existing API contract because client code and views depend on these field names.
"""

from api.utils.ai_model_pricing import price_to_display
from core.models import AiModel
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers


class AiModelCapabilitiesSerializer(serializers.Serializer):
    vision = serializers.BooleanField()
    fileUpload = serializers.BooleanField()
    reasoning = serializers.BooleanField()


class AiModelPricingSerializer(serializers.Serializer):
    prompt_price_per_token = serializers.DecimalField(
        max_digits=20,
        decimal_places=12,
        allow_null=True,
        help_text="Stored per-token value.",
    )
    completion_price_per_token = serializers.DecimalField(
        max_digits=20,
        decimal_places=12,
        allow_null=True,
        help_text="Stored per-token value.",
    )
    image_price = serializers.DecimalField(
        max_digits=20,
        decimal_places=12,
        allow_null=True,
        help_text="Stored per-unit value.",
    )
    request_price = serializers.DecimalField(
        max_digits=20,
        decimal_places=12,
        allow_null=True,
        help_text="Stored per-unit value.",
    )


class AiModelPricingDisplaySerializer(serializers.Serializer):
    prompt_price_per_million_tokens = serializers.DecimalField(
        max_digits=20,
        decimal_places=12,
        allow_null=True,
        help_text="Displayed in USD per 1M tokens.",
    )
    completion_price_per_million_tokens = serializers.DecimalField(
        max_digits=20,
        decimal_places=12,
        allow_null=True,
        help_text="Displayed in USD per 1M tokens.",
    )
    image_price_per_million_tokens = serializers.DecimalField(
        max_digits=20,
        decimal_places=12,
        allow_null=True,
        help_text="Displayed in USD per 1M tokens.",
    )
    request_price_per_million_tokens = serializers.DecimalField(
        max_digits=20,
        decimal_places=12,
        allow_null=True,
        help_text="Displayed in USD per 1M tokens.",
    )


class AiModelArchitectureSerializer(serializers.Serializer):
    modality = serializers.CharField()
    tokenizer = serializers.CharField()
    instruct_type = serializers.CharField()


class AiModelSerializer(serializers.ModelSerializer):
    capabilities = serializers.SerializerMethodField(read_only=True)
    pricing = serializers.SerializerMethodField(read_only=True)
    pricing_display = serializers.SerializerMethodField(read_only=True)
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
            "pricing_display",
            "architecture",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "prompt_price_per_token": {"help_text": "Stored per-token value."},
            "completion_price_per_token": {"help_text": "Stored per-token value."},
            "image_price": {"help_text": "Stored per-unit value."},
            "request_price": {"help_text": "Stored per-unit value."},
        }

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
            "prompt_price_per_token": (
                str(obj.prompt_price_per_token) if obj.prompt_price_per_token is not None else None
            ),
            "completion_price_per_token": (
                str(obj.completion_price_per_token) if obj.completion_price_per_token is not None else None
            ),
            "image_price": str(obj.image_price) if obj.image_price is not None else None,
            "request_price": str(obj.request_price) if obj.request_price is not None else None,
        }

    @extend_schema_field(AiModelPricingDisplaySerializer)
    def get_pricing_display(self, obj: AiModel) -> dict:
        return {
            "prompt_price_per_million_tokens": price_to_display(obj.prompt_price_per_token),
            "completion_price_per_million_tokens": price_to_display(obj.completion_price_per_token),
            "image_price_per_million_tokens": price_to_display(obj.image_price),
            "request_price_per_million_tokens": price_to_display(obj.request_price),
        }

    @extend_schema_field(AiModelArchitectureSerializer)
    def get_architecture(self, obj: AiModel) -> dict:
        return {
            "modality": obj.architecture_modality or "",
            "tokenizer": obj.architecture_tokenizer or "",
            "instruct_type": obj.instruct_type or "",
        }
