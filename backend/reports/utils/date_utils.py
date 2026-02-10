from datetime import datetime, timedelta

from django.utils import timezone


def get_date_range_filter(from_date=None, to_date=None):
    """
    Returns a tuple of (from_date, to_date) for filtering.
    If not provided, defaults to current year.
    """
    if not from_date:
        from_date = timezone.now().replace(month=1, day=1)
    if not to_date:
        to_date = timezone.now()

    return from_date, to_date


def get_month_list(from_date, to_date):
    """
    Returns a list of months between two dates.
    Format: [{'year': 2025, 'month': 1, 'label': 'Jan 2025'}, ...]
    """
    months = []
    current = from_date.replace(day=1)
    end = to_date.replace(day=1)

    while current <= end:
        months.append(
            {"year": current.year, "month": current.month, "label": current.strftime("%b %Y"), "date": current}
        )
        # Move to next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    return months
