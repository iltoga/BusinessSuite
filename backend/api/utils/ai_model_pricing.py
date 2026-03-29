"""Helpers for resolving AI model pricing data for API responses."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

PRICE_MULTIPLIER = Decimal("1000000")


def price_to_display(value: Any) -> str | None:
    """Convert a stored per-token price to a per-1M-token display string."""

    if value is None or value == "":
        return None

    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None

    formatted = format(decimal_value * PRICE_MULTIPLIER, "f")
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return formatted or "0"
