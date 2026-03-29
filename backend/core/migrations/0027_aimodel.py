"""Create the AI model registry table used by runtime model selection.

This migration stores the configurable model catalog that powers AI-related
services.
"""

from django.db import migrations, models

INITIAL_MODELS = [
    ("openrouter", "openai/gpt-5", "GPT-5", "OpenAI GPT-5 via OpenRouter", True, True, True),
    ("openrouter", "openai/gpt-5-mini", "GPT-5 Mini", "OpenAI GPT-5 Mini via OpenRouter", True, True, True),
    ("openrouter", "openai/gpt-5-nano", "GPT-5 Nano", "OpenAI GPT-5 Nano via OpenRouter", True, True, True),
    (
        "openrouter",
        "google/gemini-2.0-flash-lite-001",
        "Gemini 2.0 Flash Lite",
        "Google Gemini 2.0 Flash Lite",
        True,
        True,
        True,
    ),
    ("openrouter", "google/gemini-2.0-flash-001", "Gemini 2.0 Flash", "Google Gemini 2.0 Flash", True, True, True),
    ("openrouter", "google/gemini-2.0-pro-001", "Gemini 2.0 Pro", "Google Gemini 2.0 Pro", True, True, True),
    (
        "openrouter",
        "mistralai/mistral-small-3.2-24b-instruct",
        "Mistral Small 3.2",
        "Mistral AI Small 3.2 24B",
        False,
        False,
        True,
    ),
    (
        "openrouter",
        "google/gemini-2.5-flash-lite",
        "Gemini 2.5 Flash Lite",
        "Google Gemini 2.5 Flash Lite",
        True,
        True,
        True,
    ),
    ("openrouter", "google/gemini-2.5-flash", "Gemini 2.5 Flash", "Google Gemini 2.5 Flash", True, True, True),
    (
        "openrouter",
        "google/gemini-3-flash-preview",
        "Gemini 3 Flash Preview",
        "Google Gemini 3 Flash Preview",
        True,
        True,
        True,
    ),
    ("openrouter", "google/gemini-2.5-pro", "Gemini 2.5 Pro", "Google Gemini 2.5 Pro", True, True, True),
    ("openrouter", "x-ai/grok-4.1-fast", "Grok 4.1 Fast", "X-AI Grok 4.1 Fast", True, True, True),
    ("openai", "gpt-5", "GPT-5", "OpenAI GPT-5 Direct API", True, True, True),
    ("openai", "gpt-5-mini", "GPT-5 Mini", "OpenAI GPT-5 Mini Direct API", True, True, True),
    ("openai", "gpt-5-nano", "GPT-5 Nano", "OpenAI GPT-5 Nano Direct API", True, True, True),
    (
        "groq",
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "Llama 4 Scout 17B",
        "Meta Llama 4 Scout via Groq",
        True,
        False,
        True,
    ),
    (
        "groq",
        "meta-llama/llama-4-maverick-17b-128e-instruct",
        "Llama 4 Maverick 17B",
        "Meta Llama 4 Maverick via Groq",
        True,
        False,
        True,
    ),
    ("groq", "qwen/qwen3-32b", "Qwen 3 32B", "Qwen 3 32B via Groq", False, False, True),
]


def seed_ai_models(apps, schema_editor):
    AiModel = apps.get_model("core", "AiModel")
    for provider, model_id, name, description, vision, file_upload, reasoning in INITIAL_MODELS:
        AiModel.objects.update_or_create(
            provider=provider,
            model_id=model_id,
            defaults={
                "name": name,
                "description": description,
                "vision": vision,
                "file_upload": file_upload,
                "reasoning": reasoning,
                "source": "seed",
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0026_app_setting"),
    ]

    operations = [
        migrations.CreateModel(
            name="AiModel",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "provider",
                    models.CharField(
                        choices=[("openrouter", "OpenRouter"), ("openai", "OpenAI"), ("groq", "Groq")],
                        db_index=True,
                        max_length=32,
                    ),
                ),
                ("model_id", models.CharField(max_length=255)),
                ("name", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                ("vision", models.BooleanField(default=False)),
                ("file_upload", models.BooleanField(default=False)),
                ("reasoning", models.BooleanField(default=False)),
                ("context_length", models.IntegerField(blank=True, null=True)),
                ("max_completion_tokens", models.IntegerField(blank=True, null=True)),
                ("modality", models.CharField(blank=True, max_length=120)),
                (
                    "prompt_price_per_token",
                    models.DecimalField(blank=True, decimal_places=12, max_digits=20, null=True),
                ),
                (
                    "completion_price_per_token",
                    models.DecimalField(blank=True, decimal_places=12, max_digits=20, null=True),
                ),
                ("image_price", models.DecimalField(blank=True, decimal_places=12, max_digits=20, null=True)),
                ("request_price", models.DecimalField(blank=True, decimal_places=12, max_digits=20, null=True)),
                ("source", models.CharField(blank=True, default="manual", max_length=32)),
                ("raw_metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["provider", "name", "model_id"]},
        ),
        migrations.AddConstraint(
            model_name="aimodel",
            constraint=models.UniqueConstraint(
                fields=("provider", "model_id"), name="core_aimodel_provider_model_id_uniq"
            ),
        ),
        migrations.RunPython(seed_ai_models, migrations.RunPython.noop),
    ]
