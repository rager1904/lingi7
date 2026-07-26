"""
apps/users/validators.py
------------------------
Field-level validators for Zambian-specific identity formats.

References:
- MTN Zambia / Airtel Zambia number prefixes (correct as of 2024)
- NRC format from NRCA: XXXXXX/YY/Z
  XXXXXX = sequential district number
  YY     = year suffix
  Z      = check digit (1-9)
"""

import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.users.phone_utils import is_valid_zambian_phone, normalize_zambian_phone


class ZambianPhoneValidator:
    """
    Validates that a phone number is a valid Zambian mobile number in E.164 format.

    Accepted prefixes (mobile only — MoMo-capable):
        MTN:    096/076/056  → +26096… / +26076… / +26056…
        Airtel: 097/077/057  → +26097… / +26077… / +26057…
        Zamtel: 095/075/055  → +26095… / +26075… / +26055…
    """

    message = _(
        "Enter a valid Zambian mobile number (e.g. +260971234567, +260771234567). "
        "MTN, Airtel, and Zamtel mobile numbers are accepted."
    )
    code = "invalid_zambian_phone"

    def __call__(self, value: str) -> None:
        normalized = normalize_zambian_phone(value)
        if not is_valid_zambian_phone(normalized):
            raise ValidationError(self.message, code=self.code)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, ZambianPhoneValidator)

    def deconstruct(self):
        """Allow Django migrations to serialize this validator."""
        return (
            "apps.users.validators.ZambianPhoneValidator",
            [],
            {},
        )


class ZambianNRCValidator:
    """
    Validates Zambian National Registration Card (NRC) number format.

    Format: XXXXXX/YY/Z
        XXXXXX = 6-digit district-sequential number
        YY     = 2-digit year suffix
        Z      = 1-digit check character (1–9, no zero)

    Examples:
        123456/78/1  ✓
        000001/99/9  ✓
        123456/78/0  ✗  (check digit cannot be 0)
    """

    PATTERN = re.compile(r"^\d{6}/\d{2}/[1-9]$")
    message = _(
        "Enter a valid Zambian NRC number in the format XXXXXX/YY/Z "
        "(e.g. 123456/78/1). The final digit cannot be zero."
    )
    code = "invalid_zambian_nrc"

    def __call__(self, value: str) -> None:
        if not self.PATTERN.match(value):
            raise ValidationError(self.message, code=self.code)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, ZambianNRCValidator)

    def deconstruct(self):
        """Allow Django migrations to serialize this validator."""
        return (
            "apps.users.validators.ZambianNRCValidator",
            [],
            {},
        )
