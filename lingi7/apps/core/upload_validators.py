"""
Shared upload validation for KYC, disputes, and product images.
"""

from __future__ import annotations

import os

from django.core.exceptions import ValidationError

MAX_KYC_BYTES = 5 * 1024 * 1024
MAX_PRODUCT_IMAGE_BYTES = 10 * 1024 * 1024
MAX_EVIDENCE_BYTES = 25 * 1024 * 1024

KYC_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
EVIDENCE_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".mp4"}


def _ext(name: str) -> str:
    return os.path.splitext(name or "")[1].lower()


def validate_upload_file(
    file_obj,
    *,
    allowed_extensions: set[str],
    max_bytes: int,
    label: str = "file",
) -> None:
    if not file_obj:
        raise ValidationError({label: "File is required."})
    ext = _ext(getattr(file_obj, "name", ""))
    if ext not in allowed_extensions:
        raise ValidationError(
            {label: f"Allowed types: {', '.join(sorted(allowed_extensions))}."}
        )
    size = getattr(file_obj, "size", 0) or 0
    if size > max_bytes:
        raise ValidationError(
            {label: f"File too large. Maximum size is {max_bytes // (1024 * 1024)} MB."}
        )


def validate_kyc_storage_key(key: str, user_id: str) -> str:
    """Ensure object key belongs to the submitting user."""
    prefix = f"kyc/{user_id}/"
    normalized = key.strip().replace("\\", "/")
    if ".." in normalized or not normalized.startswith(prefix):
        raise ValidationError(
            {"detail": "Invalid document key for this account."}
        )
    return normalized
