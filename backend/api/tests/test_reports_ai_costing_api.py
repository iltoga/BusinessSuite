from datetime import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models.ai_request_usage import AIRequestUsage
from core.services.ai_usage_service import AIUsageFeature


class AICostingReportApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="ai-report-user",
            email="ai-report-user@example.com",
            password="password",
        )
        self.client.force_authenticate(user=self.user)

    def _create_usage(
        self,
        *,
        feature: str,
        created_at: datetime,
        cost_usd: Decimal,
        total_tokens: int,
        success: bool = True,
    ) -> None:
        row = AIRequestUsage.objects.create(
            feature=feature,
            provider="openrouter",
            model="google/gemini-2.5-flash-lite",
            success=success,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
        )
        AIRequestUsage.objects.filter(pk=row.pk).update(created_at=created_at)

    def test_ai_costing_report_returns_year_month_day_aggregates(self):
        tz = timezone.get_current_timezone()
        self._create_usage(
            feature=AIUsageFeature.INVOICE_IMPORT_AI_PARSER,
            created_at=timezone.make_aware(datetime(2025, 12, 31, 11, 0), tz),
            cost_usd=Decimal("0.050000"),
            total_tokens=100,
        )
        self._create_usage(
            feature=AIUsageFeature.INVOICE_IMPORT_AI_PARSER,
            created_at=timezone.make_aware(datetime(2026, 1, 5, 11, 0), tz),
            cost_usd=Decimal("0.010000"),
            total_tokens=20,
        )
        self._create_usage(
            feature=AIUsageFeature.INVOICE_IMPORT_AI_PARSER,
            created_at=timezone.make_aware(datetime(2026, 2, 10, 11, 0), tz),
            cost_usd=Decimal("0.100000"),
            total_tokens=200,
        )
        self._create_usage(
            feature=AIUsageFeature.PASSPORT_OCR_AI_EXTRACTOR,
            created_at=timezone.make_aware(datetime(2026, 2, 10, 11, 30), tz),
            cost_usd=Decimal("0.030000"),
            total_tokens=80,
            success=False,
        )
        self._create_usage(
            feature=AIUsageFeature.INVOICE_IMPORT_AI_PARSER,
            created_at=timezone.make_aware(datetime(2026, 2, 11, 9, 15), tz),
            cost_usd=Decimal("0.020000"),
            total_tokens=40,
        )

        response = self.client.get("/api/reports/ai-costing/?year=2026&month=2")
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload["selectedYear"], 2026)
        self.assertEqual(payload["selectedMonth"], 2)
        self.assertEqual(payload["yearSummary"]["requestCount"], 4)
        self.assertEqual(payload["monthSummary"]["requestCount"], 3)
        self.assertAlmostEqual(payload["monthSummary"]["totalCost"], 0.15, places=6)

        month_row = next(row for row in payload["monthlyData"] if row["month"] == 2)
        self.assertEqual(month_row["requestCount"], 3)
        self.assertAlmostEqual(month_row["totalCost"], 0.15, places=6)

        day_row = next(row for row in payload["dailyData"] if row["date"] == "2026-02-10")
        self.assertEqual(day_row["requestCount"], 2)

        feature_row = next(
            row for row in payload["featureBreakdownMonth"] if row["feature"] == AIUsageFeature.INVOICE_IMPORT_AI_PARSER
        )
        self.assertEqual(feature_row["requestCount"], 2)
        self.assertAlmostEqual(feature_row["totalCost"], 0.12, places=6)
