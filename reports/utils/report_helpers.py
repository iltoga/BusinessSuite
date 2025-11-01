from django.conf import settings


def format_currency(amount):
    """Format amount as currency based on settings."""
    currency_symbol = getattr(settings, "CURRENCY_SYMBOL", "Rp")
    decimal_places = getattr(settings, "CURRENCY_DECIMAL_PLACES", 0)

    if decimal_places == 0:
        return f"{currency_symbol} {amount:,.0f}"
    else:
        return f"{currency_symbol} {amount:,.{decimal_places}f}"


def get_trend_indicator(current, previous):
    """
    Returns trend indicator (up/down/neutral) and percentage change.
    """
    if previous == 0:
        if current > 0:
            return "up", 100.0
        return "neutral", 0.0

    change = ((current - previous) / previous) * 100

    if change > 0:
        return "up", change
    elif change < 0:
        return "down", abs(change)
    else:
        return "neutral", 0.0
