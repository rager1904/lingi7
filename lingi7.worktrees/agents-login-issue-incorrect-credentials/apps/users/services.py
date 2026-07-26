"""
apps/users/services.py
----------------------
UserService — the single authoritative location for all user and KYC business logic.

Architecture principles (from project spec):
- Fat services, thin views. Zero business logic in models or serializers.
- All state transitions are explicit methods with guard clauses.
- KYC state machine: UNVERIFIED → PENDING → VERIFIED | REJECTED → PENDING (re-submit)
- All mutations go through Django ORM with select_for_update() on concurrency-sensitive paths.
- Signals are fired after successful commits, not inside atomic blocks.

Regulatory alignment:
- BoZ KYC: all four required fields collected before PENDING is reached.
- DPA 2021: consent_given_at recorded at registration.
- FIC AML: freeze capability for suspicious accounts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from .models import KYCStatus, User, UserRole

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# Result / error types                                                #
# ------------------------------------------------------------------ #


class UserServiceError(Exception):
    """Base exception for all UserService failures."""


class DuplicatePhoneError(UserServiceError):
    """Raised when a registration attempt uses an already-registered phone."""


class DuplicateNRCError(UserServiceError):
    """Raised when an NRC number is already linked to another account."""


class InvalidKYCTransitionError(UserServiceError):
    """Raised when a KYC state transition is not permitted."""


class AccountFrozenError(UserServiceError):
    """Raised when an action is attempted on a frozen account."""


class ConsentNotGivenError(UserServiceError):
    """Raised when registration proceeds without explicit DPA consent."""


@dataclass(frozen=True)
class RegistrationResult:
    """Value object returned from register()."""

    user: User
    created: bool  # False if duplicate detected (should not happen in normal flow)


# ------------------------------------------------------------------ #
# Service                                                             #
# ------------------------------------------------------------------ #


class UserService:
    """
    Orchestrates all user lifecycle operations.

    Usage:
        service = UserService()
        result = service.register(phone_number="+260971234567", ...)

    All public methods are safe to call from DRF views or Celery tasks.
    All state-mutating methods are wrapped in transaction.atomic().
    """

    # ---------------------------------------------------------------- #
    # Registration                                                      #
    # ---------------------------------------------------------------- #

    @transaction.atomic
    def register(
        self,
        *,
        phone_number: str,
        password: str,
        first_name: str,
        last_name: str,
        role: str = UserRole.BUYER,
        email: str = "",
        consent_given: bool = False,
    ) -> RegistrationResult:
        """
        Register a new user on the platform.

        Performs:
        1. DPA 2021 consent gate.
        2. Duplicate phone check.
        3. User creation via manager.
        4. Consent timestamp recorded.

        Args:
            phone_number: E.164 Zambian mobile number.
            password: Raw password (will be hashed).
            first_name: User's first name.
            last_name: User's last name.
            role: UserRole.BUYER (default) or UserRole.VENDOR.
            email: Optional email address.
            consent_given: Must be True — Data Protection Act 2021 s.18.

        Returns:
            RegistrationResult with the created User instance.

        Raises:
            ConsentNotGivenError: If consent_given is False.
            DuplicatePhoneError: If phone is already registered.
            ValidationError: If phone format is invalid (from model validator).
        """
        if not consent_given:
            raise ConsentNotGivenError(
                "User must explicitly accept Terms of Service and Privacy Policy "
                "before registration (Zambia Data Protection Act 2021 s.18)."
            )

        if User.objects.filter(phone_number=phone_number).exists():
            raise DuplicatePhoneError(
                f"Phone number {phone_number} is already registered."
            )

        user = User.objects.create_user(
            phone_number=phone_number,
            password=password,
            first_name=first_name,
            last_name=last_name,
            role=role,
            email=email,
            consent_given_at=timezone.now(),
        )

        logger.info(
            "user.registered",
            extra={"user_id": str(user.id), "role": role, "phone": phone_number},
        )
        return RegistrationResult(user=user, created=True)

    # ---------------------------------------------------------------- #
    # KYC submission                                                    #
    # ---------------------------------------------------------------- #

    @transaction.atomic
    def kyc_submit(
        self,
        *,
        user_id: str,
        nrc_number: str,
        physical_address: str,
        province: str,
        nrc_front_key: str,
        nrc_back_key: str,
        selfie_key: str,
    ) -> User:
        """
        Record a KYC document submission and transition status to PENDING.

        Valid from states: UNVERIFIED, REJECTED.
        Invalid from states: PENDING (already submitted), VERIFIED (already done).

        Locks the user row with select_for_update() to prevent concurrent submissions.

        Args:
            user_id: UUID string of the user.
            nrc_number: Zambian NRC in XXXXXX/YY/Z format.
            physical_address: Full physical address in Zambia (BoZ requirement).
            province: Zambian province.
            nrc_front_key: S3/R2 object key for NRC front image.
            nrc_back_key: S3/R2 object key for NRC back image.
            selfie_key: S3/R2 object key for liveness selfie.

        Returns:
            Updated User instance with kyc_status=PENDING.

        Raises:
            User.DoesNotExist: If user_id not found.
            InvalidKYCTransitionError: If current state does not allow submission.
            DuplicateNRCError: If NRC is already linked to another account.
        """
        user = User.objects.select_for_update().get(id=user_id)

        allowed_from = {KYCStatus.UNVERIFIED, KYCStatus.REJECTED}
        if user.kyc_status not in allowed_from:
            raise InvalidKYCTransitionError(
                f"Cannot submit KYC from state '{user.kyc_status}'. "
                f"Allowed states: {[s.value for s in allowed_from]}."
            )

        # NRC uniqueness check — must not belong to another user
        duplicate_qs = User.objects.filter(nrc_number=nrc_number).exclude(id=user_id)
        if duplicate_qs.exists():
            raise DuplicateNRCError(
                f"NRC number {nrc_number} is already registered to another account."
            )

        user.nrc_number = nrc_number
        user.physical_address = physical_address
        user.province = province
        user.nrc_front_key = nrc_front_key
        user.nrc_back_key = nrc_back_key
        user.selfie_key = selfie_key
        user.kyc_status = KYCStatus.PENDING
        user.kyc_submitted_at = timezone.now()
        user.kyc_rejection_reason = ""  # Clear any prior rejection reason
        user.save(
            update_fields=[
                "nrc_number",
                "physical_address",
                "province",
                "nrc_front_key",
                "nrc_back_key",
                "selfie_key",
                "kyc_status",
                "kyc_submitted_at",
                "kyc_rejection_reason",
            ]
        )

        logger.info(
            "kyc.submitted",
            extra={"user_id": str(user.id), "nrc": nrc_number},
        )
        return user

    # ---------------------------------------------------------------- #
    # KYC admin actions                                                 #
    # ---------------------------------------------------------------- #

    @transaction.atomic
    def kyc_approve(self, *, user_id: str, reviewed_by: User) -> User:
        """
        Approve a pending KYC submission. Transitions status to VERIFIED.

        Only valid from PENDING state.

        Args:
            user_id: UUID string of the user being reviewed.
            reviewed_by: Admin User performing the approval.

        Returns:
            Updated User instance with kyc_status=VERIFIED.

        Raises:
            InvalidKYCTransitionError: If user is not in PENDING state.
        """
        user = User.objects.select_for_update().get(id=user_id)

        if user.kyc_status != KYCStatus.PENDING:
            raise InvalidKYCTransitionError(
                f"Cannot approve KYC: user is in '{user.kyc_status}' state, expected PENDING."
            )

        user.kyc_status = KYCStatus.VERIFIED
        user.kyc_reviewed_at = timezone.now()
        user.kyc_reviewed_by = reviewed_by
        user.kyc_rejection_reason = ""
        user.save(
            update_fields=[
                "kyc_status",
                "kyc_reviewed_at",
                "kyc_reviewed_by",
                "kyc_rejection_reason",
            ]
        )

        logger.info(
            "kyc.approved",
            extra={
                "user_id": str(user.id),
                "reviewed_by": str(reviewed_by.id),
            },
        )
        return user

    @transaction.atomic
    def kyc_reject(
        self,
        *,
        user_id: str,
        reviewed_by: User,
        rejection_reason: str,
    ) -> User:
        """
        Reject a pending KYC submission. Transitions status to REJECTED.

        rejection_reason is mandatory — it is shown to the user so they
        can correct their submission.

        Args:
            user_id: UUID string of the user being reviewed.
            reviewed_by: Admin User performing the rejection.
            rejection_reason: Human-readable reason shown to the user.

        Returns:
            Updated User instance with kyc_status=REJECTED.

        Raises:
            ValueError: If rejection_reason is empty.
            InvalidKYCTransitionError: If user is not in PENDING state.
        """
        if not rejection_reason.strip():
            raise ValueError("rejection_reason is required when rejecting a KYC submission.")

        user = User.objects.select_for_update().get(id=user_id)

        if user.kyc_status != KYCStatus.PENDING:
            raise InvalidKYCTransitionError(
                f"Cannot reject KYC: user is in '{user.kyc_status}' state, expected PENDING."
            )

        user.kyc_status = KYCStatus.REJECTED
        user.kyc_reviewed_at = timezone.now()
        user.kyc_reviewed_by = reviewed_by
        user.kyc_rejection_reason = rejection_reason
        user.save(
            update_fields=[
                "kyc_status",
                "kyc_reviewed_at",
                "kyc_reviewed_by",
                "kyc_rejection_reason",
            ]
        )

        logger.info(
            "kyc.rejected",
            extra={
                "user_id": str(user.id),
                "reviewed_by": str(reviewed_by.id),
                "reason": rejection_reason,
            },
        )
        return user

    # ---------------------------------------------------------------- #
    # Fraud / compliance actions                                        #
    # ---------------------------------------------------------------- #

    @transaction.atomic
    def freeze_account(
        self,
        *,
        user_id: str,
        reason: str,
        frozen_by: User | None = None,
    ) -> User:
        """
        Freeze a user account. Used by the fraud rule engine and admin.

        Frozen users cannot initiate escrow, payment, or order operations.
        The `can_transact` property returns False for frozen accounts.

        Args:
            user_id: UUID of the account to freeze.
            reason: Machine-readable or human-readable freeze reason (logged).
            frozen_by: Admin or system user triggering the freeze (None = automated).

        Returns:
            Updated frozen User instance.
        """
        user = User.objects.select_for_update().get(id=user_id)
        user.is_frozen = True
        user.frozen_at = timezone.now()
        user.frozen_reason = reason
        user.save(update_fields=["is_frozen", "frozen_at", "frozen_reason"])

        actor = str(frozen_by.id) if frozen_by else "system"
        logger.warning(
            "account.frozen",
            extra={"user_id": str(user.id), "reason": reason, "actor": actor},
        )
        return user

    @transaction.atomic
    def unfreeze_account(self, *, user_id: str, unfrozen_by: User) -> User:
        """
        Unfreeze a previously frozen account after manual review.

        Args:
            user_id: UUID of the account to unfreeze.
            unfrozen_by: Admin user authorising the unfreeze.

        Returns:
            Updated unfrozen User instance.
        """
        user = User.objects.select_for_update().get(id=user_id)
        user.is_frozen = False
        user.frozen_reason = ""
        user.save(update_fields=["is_frozen", "frozen_reason"])

        logger.info(
            "account.unfrozen",
            extra={"user_id": str(user.id), "unfrozen_by": str(unfrozen_by.id)},
        )
        return user

    @transaction.atomic
    def request_data_deletion(self, *, user_id: str) -> User:
        """
        Record a data deletion request under DPA 2021 s.72 (right to erasure).

        Does NOT immediately delete data. Triggers a Celery task (Phase 2)
        to anonymise the account within 30 days, subject to ZRA 7-year
        transaction record retention obligation.

        Args:
            user_id: UUID of the requesting user.

        Returns:
            Updated User instance with data_deletion_requested_at set.
        """
        user = User.objects.select_for_update().get(id=user_id)
        if user.data_deletion_requested_at is None:
            user.data_deletion_requested_at = timezone.now()
            user.save(update_fields=["data_deletion_requested_at"])
            logger.info("user.deletion_requested", extra={"user_id": str(user.id)})
        return user
