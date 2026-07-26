"""
apps/users/managers.py
----------------------
Custom manager for the Lingi7 User model.

Handles create_user and create_superuser factory methods.
Phone number is normalised to E.164 before saving.
"""

from __future__ import annotations

from django.contrib.auth.base_user import BaseUserManager
from django.utils.translation import gettext_lazy as _

from apps.users.phone_utils import normalize_zambian_phone


class UserManager(BaseUserManager):
    """
    Manager for the Lingi7 custom User model.

    The phone_number field replaces username as the unique identifier.
    All user creation must go through this manager — never call User() directly
    in production code; use UserService instead.
    """

    def _create_user(
        self,
        phone_number: str,
        password: str | None,
        first_name: str,
        last_name: str,
        full_name: str | None = None,
        **extra_fields,
    ) -> "User":  # noqa: F821 — forward ref, model imported at runtime
        """
        Core factory. Normalises phone, hashes password, persists.

        Args:
            phone_number: E.164 Zambian mobile number.
            password: Raw password string. None for unusable-password accounts.
            first_name: User's first name.
            last_name: User's last name.
            full_name: Optional combined full name to split into first and last name.
            **extra_fields: Any additional model fields.

        Returns:
            Saved User instance.

        Raises:
            ValueError: If phone_number is empty.
        """
        if not phone_number:
            raise ValueError(_("A phone number is required."))

        full_name = full_name or extra_fields.pop("full_name", None)
        if full_name:
            parsed_first, parsed_last = self._split_full_name(full_name)
            if not first_name:
                first_name = parsed_first
            if not last_name:
                last_name = parsed_last

        phone_number = self._normalise_phone(phone_number)

        user = self.model(
            phone_number=phone_number,
            first_name=first_name,
            last_name=last_name,
            **extra_fields,
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(
        self,
        phone_number: str,
        password: str | None = None,
        first_name: str = "",
        last_name: str = "",
        full_name: str | None = None,
        **extra_fields,
    ) -> "User":  # noqa: F821
        """
        Create a standard (non-staff, non-superuser) user.

        Args:
            phone_number: E.164 Zambian mobile number.
            password: Raw password. If None, account is unusable until set.
            first_name: User's first name.
            last_name: User's last name.
            **extra_fields: Role, KYC fields, etc.

        Returns:
            Saved User instance.
        """
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        full_name = full_name or extra_fields.pop("full_name", None)
        return self._create_user(
            phone_number,
            password,
            first_name,
            last_name,
            full_name=full_name,
            **extra_fields,
        )

    def create_superuser(
        self,
        phone_number: str,
        password: str,
        first_name: str = "Super",
        last_name: str = "Admin",
        full_name: str | None = None,
        **extra_fields,
    ) -> "User":  # noqa: F821
        """
        Create a superuser with is_staff=True and is_superuser=True.

        Args:
            phone_number: E.164 Zambian mobile number.
            password: Raw password (must not be None for superusers).
            first_name: Defaults to 'Super'.
            last_name: Defaults to 'Admin'.
            **extra_fields: Additional overrides.

        Returns:
            Saved superuser instance.

        Raises:
            ValueError: If is_staff or is_superuser are forced to False.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", "ADMIN")

        if extra_fields.get("is_staff") is not True:
            raise ValueError(_("Superuser must have is_staff=True."))
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(_("Superuser must have is_superuser=True."))

        full_name = full_name or extra_fields.pop("full_name", None)
        return self._create_user(
            phone_number,
            password,
            first_name,
            last_name,
            full_name=full_name,
            **extra_fields,
        )

    # ------------------------------------------------------------------ #
    # Querysets                                                            #
    # ------------------------------------------------------------------ #

    def buyers(self):
        """Return queryset of all BUYER-role users."""
        return self.filter(role="BUYER")

    def vendors(self):
        """Return queryset of all VENDOR-role users."""
        return self.filter(role="VENDOR")

    def kyc_pending(self):
        """Return queryset of users awaiting KYC review."""
        return self.filter(kyc_status="PENDING")

    def active_and_verified(self):
        """
        Return users who are active, KYC-verified, and not frozen.
        Used by escrow service as a pre-transaction eligibility check.
        """
        return self.filter(is_active=True, kyc_status="VERIFIED", is_frozen=False)

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _normalise_phone(phone: str) -> str:
        """
        Normalise phone to E.164 format.

        Strips whitespace and dashes. Converts leading 0 to +260.
        Does not validate format — that is the validator's responsibility.

        Args:
            phone: Raw phone string from user input.

        Returns:
            Cleaned E.164-style string.
        """
        return normalize_zambian_phone(phone)

    @staticmethod
    def _split_full_name(full_name: str) -> tuple[str, str]:
        """
        Parse a combined full name into first and last name.

        If only one name is provided, the remaining last name is empty.
        """
        parts = full_name.strip().split()
        if not parts:
            return "", ""
        if len(parts) == 1:
            return parts[0], ""
        return " ".join(parts[:-1]), parts[-1]
