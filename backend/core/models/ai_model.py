from django.db import models


class AiModel(models.Model):
    PROVIDER_OPENROUTER = "openrouter"
    PROVIDER_OPENAI = "openai"
    PROVIDER_GROQ = "groq"

    PROVIDER_CHOICES = [
        (PROVIDER_OPENROUTER, "OpenRouter"),
        (PROVIDER_OPENAI, "OpenAI"),
        (PROVIDER_GROQ, "Groq"),
    ]

    provider = models.CharField(max_length=32, choices=PROVIDER_CHOICES, db_index=True)
    model_id = models.CharField(max_length=255, blank=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    # Capabilities
    vision = models.BooleanField(default=False)
    file_upload = models.BooleanField(default=False)
    reasoning = models.BooleanField(default=False)

    # Architecture & Modality
    context_length = models.IntegerField(null=True, blank=True)
    max_completion_tokens = models.IntegerField(null=True, blank=True)
    modality = models.CharField(max_length=120, blank=True)
    architecture_modality = models.CharField(max_length=120, blank=True)
    architecture_tokenizer = models.CharField(max_length=255, blank=True)
    instruct_type = models.CharField(max_length=120, blank=True)

    # Pricing is stored in per-token units; APIs expose display-friendly per-1M-token values.
    prompt_price_per_token = models.DecimalField(max_digits=20, decimal_places=12, null=True, blank=True)
    completion_price_per_token = models.DecimalField(max_digits=20, decimal_places=12, null=True, blank=True)
    image_price = models.DecimalField(max_digits=20, decimal_places=12, null=True, blank=True)
    request_price = models.DecimalField(max_digits=20, decimal_places=12, null=True, blank=True)

    # Provider info
    top_provider_id = models.CharField(max_length=255, blank=True)
    provider_name = models.CharField(max_length=255, blank=True)
    
    # Endpoints and parameters
    supported_parameters = models.JSONField(default=list, blank=True)
    per_request_limits = models.JSONField(default=dict, blank=True)
    
    # Source and metadata
    source = models.CharField(max_length=32, blank=True, default="manual")
    raw_metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["provider", "name", "model_id"]
        constraints = [
            models.UniqueConstraint(fields=["provider", "model_id"], name="core_aimodel_provider_model_id_uniq")
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.model_id}"


from django.db.models.signals import post_delete
from django.dispatch import receiver


@receiver(post_delete, sender=AiModel)
def _repair_ai_settings_after_model_delete(sender, instance: AiModel, **kwargs):
    from core.services.ai_runtime_settings_service import AIRuntimeSettingsService

    AIRuntimeSettingsService.replace_deleted_model_references(instance.model_id)
