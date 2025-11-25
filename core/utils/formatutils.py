from django.conf import settings
from django.contrib.humanize.templatetags.humanize import intcomma
from django.template.defaultfilters import floatformat


def as_currency_no_symbol(value):
    CURRENCY_DECIMAL_PLACES = getattr(settings, "CURRENCY_DECIMAL_PLACES", 0)
    if value == "":
        value = 0
    value = floatformat(value, CURRENCY_DECIMAL_PLACES)
    return intcomma(value)


def as_currency(value):
    CURRENCY_SYMBOL = getattr(settings, "CURRENCY_SYMBOL", "Rp")
    return f"{CURRENCY_SYMBOL} {as_currency_no_symbol(value)}"


def as_date_str(value):
    return value.strftime("%d/%m/%Y")


def as_long_date_str(value):
    """Return date like '25 November 2025' (day month-name year)."""
    return value.strftime("%d %B %Y")


def as_date_dash_str(value):
    """Return date like '25-11-2025' (day-month-year with dashes)."""
    return value.strftime("%d-%m-%Y")
