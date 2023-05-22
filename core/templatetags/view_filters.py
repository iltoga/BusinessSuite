from django import template
from datetime import datetime, date, timedelta
from dateutil import relativedelta
from django.conf import settings

register = template.Library()

@register.filter
def months_to_date(value):
    now = datetime.now()
    r = relativedelta.relativedelta(value, now)
    return r.years*12 + r.months

@register.filter
def is_in_notification_period(expiration_date):
    if expiration_date:
        n_days = settings.GLOBAL_SETTINGS['DOCUMENT_EXPIRATION_NOTIFICATION_DAYS']
        return (expiration_date - date.today()) <= timedelta(days=n_days)
    return False