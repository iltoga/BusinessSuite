"""Tests for reports utility helpers and date calculations."""

from datetime import date, datetime
from decimal import Decimal

from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from reports.utils import format_currency, get_date_range_filter, get_month_list, get_trend_indicator


class ReportUtilsTests(SimpleTestCase):
    def test_get_date_range_filter_defaults_to_start_of_current_year(self):
        fixed_now = timezone.make_aware(datetime(2026, 3, 20, 14, 30, 0))

        with override_settings(TIME_ZONE="Asia/Makassar"):
            with self.subTest("defaults"):
                from unittest.mock import patch

                with patch("reports.utils.date_utils.timezone.now", return_value=fixed_now):
                    from_date, to_date = get_date_range_filter()

        self.assertEqual(from_date.year, 2026)
        self.assertEqual(from_date.month, 1)
        self.assertEqual(from_date.day, 1)
        self.assertEqual(to_date, fixed_now)

    def test_get_date_range_filter_preserves_explicit_bounds(self):
        from_date = date(2025, 11, 1)
        to_date = date(2026, 2, 28)

        resolved_from, resolved_to = get_date_range_filter(from_date=from_date, to_date=to_date)

        self.assertEqual(resolved_from, from_date)
        self.assertEqual(resolved_to, to_date)

    def test_get_month_list_spans_year_boundary(self):
        months = get_month_list(date(2025, 11, 15), date(2026, 2, 2))

        self.assertEqual(
            [(row["year"], row["month"], row["label"]) for row in months],
            [
                (2025, 11, "Nov 2025"),
                (2025, 12, "Dec 2025"),
                (2026, 1, "Jan 2026"),
                (2026, 2, "Feb 2026"),
            ],
        )
        self.assertEqual(months[0]["date"], date(2025, 11, 1))
        self.assertEqual(months[-1]["date"], date(2026, 2, 1))

    @override_settings(CURRENCY_SYMBOL="Rp", CURRENCY_DECIMAL_PLACES=2)
    def test_currency_and_trend_helpers_format_expected_values(self):
        self.assertEqual(format_currency(Decimal("1234.5")), "Rp 1,234.50")
        self.assertEqual(get_trend_indicator(120, 100), ("up", 20.0))
        self.assertEqual(get_trend_indicator(80, 100), ("down", 20.0))
        self.assertEqual(get_trend_indicator(100, 100), ("neutral", 0.0))
        self.assertEqual(get_trend_indicator(10, 0), ("up", 100.0))
        self.assertEqual(get_trend_indicator(0, 0), ("neutral", 0.0))
