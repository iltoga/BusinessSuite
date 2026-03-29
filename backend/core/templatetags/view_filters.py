"""
FILE_ROLE: Provides template filters for notification-period checks in templates.

KEY_COMPONENTS:
- is_in_notification_period: Returns whether a document expiration is within the configured notification window.

INTERACTIONS:
- Depends on: django.template, django.conf.settings, date/timedelta helpers.

AI_GUIDELINES:
- Keep filters presentation-only and deterministic.
- Do not add business logic here beyond the small date-window check already used by templates.
"""

from datetime import date, timedelta

from django import template
from django.conf import settings

register = template.Library()


@register.filter
def is_in_notification_period(expiration_date):
    if expiration_date:
        n_days = settings.GLOBAL_SETTINGS["DOCUMENT_EXPIRATION_NOTIFICATION_DAYS"]
        return (expiration_date - date.today()) <= timedelta(days=n_days)
    return False
