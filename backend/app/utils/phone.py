"""Phone number validation utilities."""

import re

from app.core.exceptions import InvalidPhoneNumberError

# E.164: + followed by 7-15 digits
E164_PATTERN = re.compile(r"^\+[1-9]\d{6,14}$")

# Common local formats before normalization
INDIA_LOCAL_PATTERN = re.compile(r"^[6-9]\d{9}$")
INDIA_WITHOUT_PLUS_PATTERN = re.compile(r"^91[6-9]\d{9}$")


def normalize_phone(phone: str) -> str:
    """
    Normalize common phone formats to E.164.

    Supports:
    - +919876543210 (already valid)
    - 919876543210 (India, missing +)
    - 9876543210 (10-digit India mobile)
    """
    normalized = phone.strip().replace(" ", "").replace("-", "")

    if INDIA_LOCAL_PATTERN.match(normalized):
        normalized = f"+91{normalized}"
    elif INDIA_WITHOUT_PLUS_PATTERN.match(normalized):
        normalized = f"+{normalized}"

    return normalized


def validate_phone(phone: str) -> str:
    """
    Validate and normalize a phone number to E.164 format.

    Raises InvalidPhoneNumberError if the format is invalid.
    """
    normalized = normalize_phone(phone)
    if not E164_PATTERN.match(normalized):
        raise InvalidPhoneNumberError(phone)
    return normalized
