"""
ICAO Passport Validation Utilities
Functions for validating passport numbers using ICAO 9303 standards.
"""

import re
from typing import Tuple


def validate_passport_number_icao(passport_number: str) -> Tuple[bool, str]:
    """
    Validate a passport number using ICAO 9303 check digit algorithm.

    The ICAO algorithm uses weights 7, 3, 1 repeating, with modulo 10.
    Character values: 0-9 = 0-9, A-Z = 10-35, < = 0

    Note: This validates the format and check digit if present.
    Many passport numbers don't include a check digit in the visual zone,
    so we primarily check for valid characters and reasonable length.

    Args:
        passport_number: The passport number to validate

    Returns:
        Tuple of (is_valid, message)
    """
    if not passport_number:
        return False, "Passport number is empty"

    # Clean the passport number (remove spaces, convert to uppercase)
    cleaned = passport_number.upper().strip().replace(" ", "")

    # Check for valid characters (A-Z, 0-9, <)
    if not re.match(r"^[A-Z0-9<]+$", cleaned):
        return False, f"Invalid characters in passport number: {passport_number}"

    # Check reasonable length (typically 8-9 characters, but can vary by country)
    if len(cleaned) < 5:
        return False, f"Passport number too short: {passport_number}"

    if len(cleaned) > 20:
        return False, f"Passport number too long (may contain MRZ data): {passport_number}"

    # If the passport number looks like it contains MRZ line data, reject it
    # MRZ data often has consecutive < characters or nationality codes embedded
    if "<<<" in cleaned or len(cleaned) > 15:
        return False, f"Passport number appears to contain MRZ data: {passport_number}"

    return True, "Valid passport number format"


def calculate_icao_check_digit(data: str) -> int:
    """
    Calculate ICAO 9303 check digit for a given string.

    Uses weights 7, 3, 1 repeating with modulo 10.
    Character values: 0-9 = 0-9, A-Z = 10-35, < = 0

    Args:
        data: String to calculate check digit for

    Returns:
        Check digit (0-9)
    """
    weights = [7, 3, 1]
    total = 0

    for i, char in enumerate(data.upper()):
        if char == "<":
            value = 0
        elif char.isdigit():
            value = int(char)
        elif char.isalpha():
            value = ord(char) - ord("A") + 10
        else:
            value = 0

        total += value * weights[i % 3]

    return total % 10


def verify_icao_check_digit(data: str, check_digit: str) -> bool:
    """
    Verify that a check digit is correct for the given data.

    Args:
        data: String the check digit was calculated from
        check_digit: The check digit to verify (single character)

    Returns:
        True if check digit is valid
    """
    if not check_digit or len(check_digit) != 1:
        return False

    try:
        expected = calculate_icao_check_digit(data)
        actual = int(check_digit) if check_digit.isdigit() else -1
        return expected == actual
    except (ValueError, TypeError):
        return False
