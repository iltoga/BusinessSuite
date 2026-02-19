from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from core.models.ai_request_usage import AIRequestUsage
from core.tasks.ai_usage import capture_ai_usage_task


def _run_huey_task(task, **kwargs):
    if hasattr(task, "call_local"):
        return task.call_local(**kwargs)
    if hasattr(task, "func"):
        return task.func(**kwargs)
    return task(**kwargs)


class AIUsageTaskTests(TestCase):
    @override_settings(
        OPENROUTER_API_KEY="test-key",
        OPENROUTER_API_BASE_URL="https://openrouter.ai/api/v1",
    )
    @patch("core.tasks.ai_usage.requests.get")
    def test_capture_ai_usage_task_fetches_openrouter_generation_data(self, mock_get):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "data": {
                "id": "gen-123",
                "model": "google/gemini-2.5-flash-lite",
                "totalCost": 0.012345,
                "tokensPrompt": 50,
                "tokensCompletion": 20,
            }
        }
        mock_get.return_value = response

        result = _run_huey_task(
            capture_ai_usage_task,
            feature="Invoice Import AI Parser",
            provider="openrouter",
            model="google/gemini-2.5-flash-lite",
            request_type="chat.completions",
            request_id="gen-123",
            success=True,
            latency_ms=300,
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(AIRequestUsage.objects.count(), 1)
        usage = AIRequestUsage.objects.get()
        self.assertEqual(usage.request_id, "gen-123")
        self.assertEqual(usage.prompt_tokens, 50)
        self.assertEqual(usage.completion_tokens, 20)
        self.assertEqual(usage.total_tokens, 70)
        self.assertEqual(float(usage.cost_usd), 0.012345)

    @override_settings(
        OPENROUTER_API_KEY="test-key",
        OPENROUTER_API_BASE_URL="https://openrouter.ai/api/v1",
    )
    @patch("core.tasks.ai_usage.requests.get")
    def test_capture_ai_usage_task_logs_and_skips_on_provider_error(self, mock_get):
        mock_get.side_effect = Exception("provider unavailable")

        result = _run_huey_task(
            capture_ai_usage_task,
            feature="Invoice Import AI Parser",
            provider="openrouter",
            model="google/gemini-2.5-flash-lite",
            request_type="chat.completions",
            request_id="gen-123",
            success=True,
            latency_ms=300,
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(AIRequestUsage.objects.count(), 0)
