from datetime import datetime

from django.utils import timezone

from core.models.holiday import Holiday


def parse_date_field(value):
    """
    Parse a date field value from form data.
    Handles empty strings, None values, and various date formats.
    Returns None for empty/invalid values, or a date object for valid dates.

    Args:
        value: The date value to parse (string, date, or None)

    Returns:
        date object or None
    """
    if not value or value == "":
        return None
    if isinstance(value, str):
        # Try YYYY-MM-DD format first (HTML date input default)
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            pass
        # Try DD/MM/YYYY format
        try:
            return datetime.strptime(value, "%d/%m/%Y").date()
        except ValueError:
            pass
        # Try YYMMDD format (passport MRZ format)
        try:
            return datetime.strptime(value, "%y%m%d").date()
        except ValueError:
            pass
        return None
    # If it's already a date object, return it
    if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
        return value
    return None


def calculate_due_date(start_date, days_to_complete, business_days_only=False, country="ID"):
    if not start_date or days_to_complete == 0:
        return start_date

    due_date = start_date
    added_days = 0

    while added_days < days_to_complete:
        due_date = due_date + timezone.timedelta(days=1)
        is_holiday = Holiday.objects.is_holiday(due_date, country)
        if not business_days_only or not is_holiday:
            added_days += 1

    return due_date
