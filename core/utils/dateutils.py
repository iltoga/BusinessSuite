from django.utils import timezone
from core.models import Holiday

def calculate_due_date(start_date, days_to_complete, business_days_only=False, country='ID'):
    if not start_date or not days_to_complete:
        return None

    due_date = start_date
    added_days = 0

    while added_days < days_to_complete:
        due_date = due_date + timezone.timedelta(days=1)
        is_holiday = Holiday.objects.is_holiday(due_date, country)
        if not business_days_only or not is_holiday:
            added_days += 1

    return due_date

