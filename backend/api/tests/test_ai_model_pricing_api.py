"""Regression tests for AI model pricing API endpoints."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from core.models import AiModel
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient


class AiModelPricingApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="ai-model-pricing-admin",
            email="ai-model-pricing-admin@example.com",
            password="password",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_ai_model_detail_exposes_display_pricing_in_per_million_tokens(self):
        model = AiModel.objects.create(
            provider=AiModel.PROVIDER_OPENROUTER,
            model_id="openrouter/qwen3.5-flash",
            name="Qwen: Qwen3.5-Flash",
            description="Test model",
            prompt_price_per_token=Decimal("0.00000016"),
            completion_price_per_token=Decimal("0.00000130"),
            image_price=Decimal("0"),
            request_price=Decimal("0.00000005"),
            source="manual",
        )

        response = self.client.get(f"/api/ai-models/{model.id}/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(Decimal(payload["promptPricePerToken"]), Decimal("0.00000016"))
        self.assertEqual(Decimal(payload["completionPricePerToken"]), Decimal("0.00000130"))
        self.assertEqual(payload["pricingDisplay"]["promptPricePerMillionTokens"], "0.16")
        self.assertEqual(payload["pricingDisplay"]["completionPricePerMillionTokens"], "1.3")
        self.assertEqual(payload["pricingDisplay"]["imagePricePerMillionTokens"], "0")
        self.assertEqual(payload["pricingDisplay"]["requestPricePerMillionTokens"], "0.05")

    @override_settings(OPENROUTER_API_KEY="test-key")
    @patch("api.view_auth_catalog.requests.get")
    def test_openrouter_search_includes_display_pricing_for_form_autofill(self, requests_get_mock):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "data": [
                {
                    "id": "openrouter/qwen3.5-flash",
                    "name": "Qwen: Qwen3.5-Flash",
                    "description": "Test model",
                    "architecture": {
                        "modality": "text->text",
                        "tokenizer": "qwen",
                        "instruct_type": "chat",
                    },
                    "pricing": {
                        "prompt": "0.00000016",
                        "completion": "0.00000130",
                        "image": "0",
                        "request": "0.00000005",
                    },
                    "top_provider": {"max_completion_tokens": 8192},
                    "context_length": 32768,
                    "supported_parameters": ["temperature"],
                    "per_request_limits": {"max_input_tokens": 4096},
                }
            ]
        }
        requests_get_mock.return_value = mock_response

        response = self.client.get("/api/ai-models/openrouter-search/?q=qwen&limit=1")

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(len(payload["results"]), 1)
        row = payload["results"][0]
        self.assertEqual(row["promptPricePerToken"], "0.00000016")
        self.assertEqual(row["pricingDisplay"]["promptPricePerMillionTokens"], "0.16")
        self.assertEqual(row["pricingDisplay"]["completionPricePerMillionTokens"], "1.3")
        self.assertEqual(row["pricingDisplay"]["imagePricePerMillionTokens"], "0")
        self.assertEqual(row["pricingDisplay"]["requestPricePerMillionTokens"], "0.05")
