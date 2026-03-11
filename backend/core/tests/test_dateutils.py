from datetime import date

from core.models.holiday import Holiday
from core.utils.dateutils import calculate_due_date
from django.test import TestCase


class CalculateDueDateTests(TestCase):
    def test_business_days_skip_weekends_without_seeded_weekend_rows(self):
        start_date = date(2026, 3, 13)  # Friday

        due_date = calculate_due_date(start_date, 1, business_days_only=True)

        self.assertEqual(due_date, date(2026, 3, 16))

    def test_business_days_skip_explicit_country_holidays(self):
        Holiday.objects.create(name="Nyepi Observed", date=date(2026, 3, 16), country="ID")
        start_date = date(2026, 3, 13)  # Friday

        due_date = calculate_due_date(start_date, 1, business_days_only=True)

        self.assertEqual(due_date, date(2026, 3, 17))

    def test_calendar_days_still_count_weekends(self):
        start_date = date(2026, 3, 13)  # Friday

        due_date = calculate_due_date(start_date, 1, business_days_only=False)

        self.assertEqual(due_date, date(2026, 3, 14))
