"""
apps/users/models.py
--------------------
Custom User model for Lingi7 — Zambian fintech-grade escrow platform.

Design decisions:
- AbstractBaseUser for full control over auth fields (no username — phone is the identity)
- Phone number is the primary login identifier (MTN/Airtel MoMo alignment)
- NRC (National Registration Card) is unique and required for KYC (BoZ requirement)
- KYC state machine: UNVERIFIED → PENDING → VERIFIED | REJECTED
- Role-based: BUYER, VENDOR, ADMIN — enforced via DRF permissions layer
- All PII fields encrypted at rest via django-encrypted-model-fields (Phase 2 hardening)
- Data Protection Act 2021: consent timestamp, data_deletion_requested flag
- Audit timestamps on every state-changing field
"""

import uuid
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .managers import UserManager
from .validators import ZambianPhoneValidator, ZambianNRCValidator


class UserRole(models.TextChoices):
    """Platform roles. ADMIN is granted via is_staff — not self-assignable."""

    BUYER = "BUYER", _("Buyer")
    VENDOR = "VENDOR", _("Vendor")
    ADMIN = "ADMIN", _("Admin")


class KYCStatus(models.TextChoices):
    """
    BoZ-aligned KYC verification state machine.

    Transitions (enforced in UserService, not here):
        UNVERIFIED → PENDING   : user submits NRC + selfie
        PENDING    → VERIFIED  : admin approves
        PENDING    → REJECTED  : admin rejects (rejection_reason required)
        REJECTED   → PENDING   : user re-submits
    """

    UNVERIFIED = "UNVERIFIED", _("Unverified")
    PENDING = "PENDING", _("Pending Review")
    VERIFIED = "VERIFIED", _("Verified")
    REJECTED = "REJECTED", _("Rejected")


class User(AbstractBaseUser, PermissionsMixin):
    """
    Primary identity model for the Lingi7 platform.

    Authentication: phone_number (E.164 format) + password.
    KYC: NRC number + document image upload, reviewed by admin.
    Compliance: Data Protection Act 2021, BoZ KYC, FIC AML.

    Phone is the canonical identifier because MTN MoMo and Airtel Money
    are tied to phone numbers — aligning auth identity with payment identity
    eliminates a class of fraud vectors.
    """

    # ------------------------------------------------------------------ #
    # Core identity                                                        #
    # ------------------------------------------------------------------ #
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_("Immutable UUID — used as the external identifier in all APIs."),
    )
    phone_number = models.CharField(
        max_length=15,
        unique=True,
        validators=[ZambianPhoneValidator()],
        help_text=_(
            "E.164 format, e.g. +260971234567. Must be a valid MTN or Airtel Zambia number."
        ),
    )
    email = models.EmailField(
        blank=True,
        default="",
        help_text=_("Optional. Used for transactional emails only — not for login."),
    )

    # ------------------------------------------------------------------ #
    # Profile                                                              #
    # ------------------------------------------------------------------ #
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    role = models.CharField(
        max_length=10,
        choices=UserRole.choices,
        default=UserRole.BUYER,
        db_index=True,
    )

    # ------------------------------------------------------------------ #
    # KYC — BoZ National Registration Card                                #
    # ------------------------------------------------------------------ #
    nrc_number = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        validators=[ZambianNRCValidator()],
        help_text=_(
            "Zambian NRC format: XXXXXX/XX/X (e.g. 123456/78/1). "
            "Unique per user. Required for KYC verification."
        ),
    )
    kyc_status = models.CharField(
        max_length=12,
        choices=KYCStatus.choices,
        default=KYCStatus.UNVERIFIED,
        db_index=True,
    )
    kyc_submitted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Timestamp when KYC documents were last submitted."),
    )
    kyc_reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Timestamp when KYC was last reviewed by an admin."),
    )
    kyc_reviewed_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="kyc_reviews_performed",
        help_text=_("Admin user who performed the last KYC review."),
    )
    kyc_rejection_reason = models.TextField(
        blank=True,
        default="",
        help_text=_("Mandatory when kyc_status = REJECTED. Shown to user."),
    )

    # ------------------------------------------------------------------ #
    # KYC document storage (S3/R2 keys — not full URLs)                  #
    # ------------------------------------------------------------------ #
    nrc_front_key = models.CharField(
        max_length=512,
        blank=True,
        default="",
        help_text=_("S3/R2 object key for NRC front image. Never expose as public URL."),
    )
    nrc_back_key = models.CharField(
        max_length=512,
        blank=True,
        default="",
        help_text=_("S3/R2 object key for NRC back image."),
    )
    selfie_key = models.CharField(
        max_length=512,
        blank=True,
        default="",
        help_text=_("S3/R2 object key for liveness selfie image."),
    )

    # ------------------------------------------------------------------ #
    # Address — BoZ KYC requires physical address                         #
    # ------------------------------------------------------------------ #
    physical_address = models.TextField(
        blank=True,
        default="",
        help_text=_(
            "Physical address in Zambia. Required for KYC completion. "
            "BoZ mandates collection and retention."
        ),
    )
    province = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text=_("Zambian province (e.g. Copperbelt, Lusaka)."),
    )

    # ------------------------------------------------------------------ #
    # Fraud / risk surface                                                 #
    # ------------------------------------------------------------------ #
    is_frozen = models.BooleanField(
        default=False,
        db_index=True,
        help_text=_(
            "True when account is frozen by fraud system or admin. "
            "Frozen users cannot initiate transactions."
        ),
    )
    frozen_at = models.DateTimeField(null=True, blank=True)
    frozen_reason = models.TextField(blank=True, default="")
    device_fingerprint = models.CharField(
        max_length=256,
        blank=True,
        default="",
        help_text=_("Latest device fingerprint hash from FingerprintJS (Phase 2)."),
    )

    # ------------------------------------------------------------------ #
    # Data Protection Act 2021 compliance                                 #
    # ------------------------------------------------------------------ #
    consent_given_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_(
            "Timestamp when user explicitly accepted Terms of Service and Privacy Policy. "
            "Required under Zambia Data Protection Act 2021."
        ),
    )
    data_deletion_requested_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_(
            "Set when user exercises right to erasure. "
            "Triggers anonymisation workflow within 30 days (DPA 2021 s.72)."
        ),
    )

    # ------------------------------------------------------------------ #
    # Django auth machinery                                                #
    # ------------------------------------------------------------------ #
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(
        default=False,
        help_text=_("Designates admin panel access. Does not imply ADMIN role."),
    )
    date_joined = models.DateTimeField(default=timezone.now)

    # Email verified flag (sent during registration)
    email_verified = models.BooleanField(default=False)
    phone_verified = models.BooleanField(
        default=False,
        help_text=_("True after OTP verification on registration."),
    )

    USERNAME_FIELD = "phone_number"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = UserManager()

    class Meta:
        verbose_name = _("User")
        verbose_name_plural = _("Users")
        indexes = [
            models.Index(fields=["kyc_status", "role"], name="idx_user_kyc_role"),
            models.Index(fields=["is_frozen"], name="idx_user_frozen"),
            models.Index(fields=["nrc_number"], name="idx_user_nrc"),
        ]

    def __str__(self) -> str:
        return f"{self.get_full_name()} ({self.phone_number})"

    # ------------------------------------------------------------------ #
    # Properties                                                           #
    # ------------------------------------------------------------------ #

    def get_full_name(self) -> str:
        """Return the user's full name."""
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self) -> str:
        """Return the user's first name."""
        return self.first_name

    @property
    def is_kyc_verified(self) -> bool:
        """True only when KYC is fully approved. Used by escrow permission guards."""
        return self.kyc_status == KYCStatus.VERIFIED

    @property
    def is_buyer(self) -> bool:
        return self.role == UserRole.BUYER

    @property
    def is_vendor(self) -> bool:
        return self.role == UserRole.VENDOR

    @property
    def can_transact(self) -> bool:
        """
        Composite gate: user must be active, KYC-verified, and not frozen
        before any escrow or payment operation is allowed.
        """
        return self.is_active and self.is_kyc_verified and not self.is_frozen
