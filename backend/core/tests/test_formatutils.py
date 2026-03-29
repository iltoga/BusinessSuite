"""Tests for core formatting utility helpers."""

from datetime import date

from core.utils.formatutils import as_currency, as_currency_no_symbol, as_date_dash_str, as_date_str, as_long_date_str
from django.test import SimpleTestCase, override_settings


@override_settings(CURRENCY_SYMBOL="IDR", CURRENCY_DECIMAL_PLACES=2)
class FormatUtilsTests(SimpleTestCase):
    def test_currency_helpers_format_values_consistently(self):
        self.assertEqual(as_currency_no_symbol(1234.5), "1,234.50")
        self.assertEqual(as_currency(1234.5), "IDR 1,234.50")
        self.assertEqual(as_currency(""), "IDR 0.00")

    def test_date_helpers_use_expected_formats(self):
        sample = date(2026, 3, 20)

        self.assertEqual(as_date_str(sample), "20/03/2026")
        self.assertEqual(as_long_date_str(sample), "20 March 2026")
        self.assertEqual(as_date_dash_str(sample), "20-03-2026")
