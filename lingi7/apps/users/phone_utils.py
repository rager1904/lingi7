"""
Shared Zambian mobile phone normalization and validation.

Accepted E.164 prefixes after +260:
  MTN:    96, 76, 56 (local 096, 076, 056)
  Airtel: 97, 77, 57 (local 097, 077, 057)
  Zamtel: 95, 75, 55 (local 095, 075, 055)
"""

from __future__ import annotations

import re

# 9-digit national mobile number (without country code)
_ZM_MOBILE_NATIONAL = re.compile(r"^(9[5-7]|7[5-7]|5[5-7])\d{7}$")
_ZM_E164 = re.compile(r"^\+260(9[5-7]|7[5-7]|5[5-7])\d{7}$")


def normalize_zambian_phone(phone: str) -> str:
    """
    Normalise user input to E.164 (+260XXXXXXXXX).

    Accepts:
      +260971234567, 260971234567, 0971234567, 771234567, 0561234567, etc.
    """
    if not phone:
        return ""

    cleaned = phone.strip().replace(" ", "").replace("-", "")

    if cleaned.startswith("+"):
        return cleaned

    if cleaned.startswith("260") and len(cleaned) >= 12:
        return "+" + cleaned

    if cleaned.startswith("0") and len(cleaned) >= 10:
        return "+260" + cleaned[1:]

    digits = re.sub(r"\D", "", cleaned)
    if len(digits) == 9 and _ZM_MOBILE_NATIONAL.match(digits):
        return "+260" + digits
    if len(digits) == 12 and digits.startswith("260"):
        return "+" + digits

    # Partial entry while typing — keep +260 prefix if user only typed digits
    if digits and not cleaned.startswith("+"):
        if digits.startswith("260"):
            return "+" + digits
        return "+260" + digits

    return cleaned


def is_valid_zambian_phone(phone: str) -> bool:
    """Return True if phone is a valid Zambian mobile number in E.164 form."""
    return bool(_ZM_E164.match(normalize_zambian_phone(phone)))
