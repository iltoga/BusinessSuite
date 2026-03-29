"""Tests for AI usage accounting and aggregation helpers."""

from decimal import Decimal
from unittest.mock import patch

from core.services.ai_usage_service import AIUsageFeature, AIUsageService
from django.test import SimpleTestCase


class AIUsageServiceTests(SimpleTestCase):
    @patch("core.tasks.ai_usage.capture_ai_usage_task")
    def test_enqueue_request_capture_serializes_decimal_usage_for_dramatiq_payload(self, capture_task_mock):
        response = {
            "id": "req-123",
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "cost": Decimal("0.1234"),
            },
        }

        AIUsageService.enqueue_request_capture(
            feature=AIUsageFeature.DOCUMENT_AI_CATEGORIZER,
            provider="openrouter",
            model="mistralai/mistral-small-3.2-24b-instruct",
            response=response,
        )

        # Task is dispatched via send_with_options(kwargs=..., delay=5000)
        capture_task_mock.send_with_options.assert_called_once()
        kwargs = capture_task_mock.send_with_options.call_args.kwargs["kwargs"]
        self.assertEqual(kwargs["request_id"], "req-123")
        self.assertEqual(kwargs["usage_data"]["cost_usd"], "0.1234")
