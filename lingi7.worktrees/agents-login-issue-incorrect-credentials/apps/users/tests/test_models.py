"""
apps/users/tests/test_models.py
--------------------------------
Tests for the User model, UserManager, and field validators.

Coverage:
- User creation via manager (create_user, create_superuser)
- Phone normalisation (local → E.164)
- NRC uniqueness constraint
- Role assignment and property accessors
- KYCStatus property guards
- can_transact composite property
- ZambianPhoneValidator accepted and rejected inputs
- ZambianNRCValidator accepted and rejected inputs
- Data Protection Act fields
"""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.users.models import KYCStatus, User, UserRole
from apps.users.validators import ZambianNRCValidator, ZambianPhoneValidator


# ------------------------------------------------------------------ #
# Fixtures                                                            #
# ------------------------------------------------------------------ #


@pytest.fixture
def buyer(db) -> User:
    return User.objects.create_user(
        phone_number="+260971234567",
        password="Str0ngP@ssword!",
        first_name="Alice",
        last_name="Banda",
        role=UserRole.BUYER,
    )


@pytest.fixture
def vendor(db) -> User:
    return User.objects.create_user(
        phone_number="+260761234567",
        password="Str0ngP@ssword!",
        first_name="Bob",
        last_name="Mwale",
        role=UserRole.VENDOR,
    )


@pytest.fixture
def verified_buyer(buyer: User) -> User:
    buyer.kyc_status = KYCStatus.VERIFIED
    buyer.save(update_fields=["kyc_status"])
    return buyer


# ------------------------------------------------------------------ #
# Manager: create_user                                                #
# ------------------------------------------------------------------ #


class TestUserManagerCreateUser:
    def test_creates_user_with_correct_fields(self, buyer: User):
        assert buyer.phone_number == "+260971234567"
        assert buyer.first_name == "Alice"
        assert buyer.last_name == "Banda"
        assert buyer.role == UserRole.BUYER
        assert buyer.is_active is True
        assert buyer.is_staff is False
        assert buyer.is_superuser is False

    def test_password_is_hashed(self, buyer: User):
        assert buyer.password != "Str0ngP@ssword!"
        assert buyer.check_password("Str0ngP@ssword!")

    def test_kyc_status_defaults_to_unverified(self, buyer: User):
        assert buyer.kyc_status == KYCStatus.UNVERIFIED

    def test_is_frozen_defaults_false(self, buyer: User):
        assert buyer.is_frozen is False

    def test_raises_on_empty_phone(self, db):
        with pytest.raises(ValueError, match="phone number is required"):
            User.objects.create_user(phone_number="", password="pass", first_name="X", last_name="Y")

    def test_normalises_local_format(self, db):
        """Phone starting with 0 should be converted to +260."""
        user = User.objects.create_user(
            phone_number="0971234568",
            password="pass",
            first_name="C",
            last_name="D",
        )
        assert user.phone_number == "+260971234568"

    def test_phone_uniqueness_enforced(self, buyer: User, db):
        with pytest.raises(IntegrityError):
            User.objects.create_user(
                phone_number="+260971234567",  # Same as buyer
                password="another",
                first_name="Other",
                last_name="User",
            )


class TestUserManagerCreateSuperuser:
    def test_creates_superuser(self, db):
        admin = User.objects.create_superuser(
            phone_number="+260971999999",
            password="AdminP@ss1!",
        )
        assert admin.is_staff is True
        assert admin.is_superuser is True
        assert admin.role == UserRole.ADMIN

    def test_raises_if_is_staff_forced_false(self, db):
        with pytest.raises(ValueError, match="is_staff=True"):
            User.objects.create_superuser(
                phone_number="+260971888888",
                password="pass",
                is_staff=False,
            )

    def test_raises_if_is_superuser_forced_false(self, db):
        with pytest.raises(ValueError, match="is_superuser=True"):
            User.objects.create_superuser(
                phone_number="+260971777777",
                password="pass",
                is_superuser=False,
            )


# ------------------------------------------------------------------ #
# Manager querysets                                                   #
# ------------------------------------------------------------------ #


class TestUserManagerQuerysets:
    def test_buyers_returns_only_buyers(self, buyer: User, vendor: User):
        buyers = User.objects.buyers()
        assert buyer in buyers
        assert vendor not in buyers

    def test_vendors_returns_only_vendors(self, buyer: User, vendor: User):
        vendors = User.objects.vendors()
        assert vendor in vendors
        assert buyer not in vendors

    def test_kyc_pending_filters_correctly(self, buyer: User, db):
        buyer.kyc_status = KYCStatus.PENDING
        buyer.save(update_fields=["kyc_status"])
        assert buyer in User.objects.kyc_pending()

    def test_active_and_verified_filters(self, db):
        unverified = User.objects.create_user(
            phone_number="+260971000010",
            password="pass",
            first_name="Unverified",
            last_name="User",
        )
        verified = User.objects.create_user(
            phone_number="+260971000011",
            password="pass",
            first_name="Verified",
            last_name="User",
            kyc_status=KYCStatus.VERIFIED,
        )
        qs = User.objects.active_and_verified()
        assert verified in qs
        assert unverified not in qs


# ------------------------------------------------------------------ #
# Model properties                                                    #
# ------------------------------------------------------------------ #


class TestUserProperties:
    def test_get_full_name(self, buyer: User):
        assert buyer.get_full_name() == "Alice Banda"

    def test_str_representation(self, buyer: User):
        assert "+260971234567" in str(buyer)
        assert "Alice Banda" in str(buyer)

    def test_is_buyer(self, buyer: User):
        assert buyer.is_buyer is True
        assert buyer.is_vendor is False

    def test_is_vendor(self, vendor: User):
        assert vendor.is_vendor is True
        assert vendor.is_buyer is False

    def test_is_kyc_verified_false_when_unverified(self, buyer: User):
        assert buyer.is_kyc_verified is False

    def test_is_kyc_verified_true_when_verified(self, verified_buyer: User):
        assert verified_buyer.is_kyc_verified is True

    def test_can_transact_requires_kyc(self, buyer: User):
        """Unverified user cannot transact."""
        assert buyer.can_transact is False

    def test_can_transact_requires_not_frozen(self, verified_buyer: User):
        """KYC-verified but frozen user cannot transact."""
        verified_buyer.is_frozen = True
        verified_buyer.save(update_fields=["is_frozen"])
        assert verified_buyer.can_transact is False

    def test_can_transact_true_when_all_clear(self, verified_buyer: User):
        assert verified_buyer.can_transact is True


# ------------------------------------------------------------------ #
# NRC uniqueness                                                      #
# ------------------------------------------------------------------ #


class TestNRCUniqueness:
    def test_nrc_is_unique(self, buyer: User, vendor: User, db):
        """Two users cannot share the same NRC number."""
        buyer.nrc_number = "123456/78/1"
        buyer.save(update_fields=["nrc_number"])

        vendor.nrc_number = "123456/78/1"
        with pytest.raises(IntegrityError):
            vendor.save(update_fields=["nrc_number"])

    def test_nrc_can_be_null(self, db):
        """NRC is optional until KYC submission."""
        user = User.objects.create_user(
            phone_number="+260975555555",
            password="pass",
            first_name="No",
            last_name="NRC",
        )
        assert user.nrc_number is None

    def test_multiple_users_can_have_null_nrc(self, buyer: User, vendor: User):
        """NULL is not subject to uniqueness constraint in PostgreSQL."""
        assert buyer.nrc_number is None
        assert vendor.nrc_number is None  # Both NULL — no conflict


# ------------------------------------------------------------------ #
# Validators                                                          #
# ------------------------------------------------------------------ #


class TestZambianPhoneValidator:
    valid_numbers = [
        "+260971234567",  # Airtel
        "+260977654321",  # Airtel
        "+260761234567",  # MTN
        "+260767654321",  # MTN
        "+260951234567",  # Zamtel
        "+260751234567",  # Zamtel
    ]
    invalid_numbers = [
        "0971234567",          # Missing +260 prefix (not normalised yet)
        "+260211123456",       # Landline
        "+27971234567",        # South African number
        "+260971234",          # Too short
        "+2609712345678",      # Too long
        "not-a-number",
        "",
    ]

    @pytest.mark.parametrize("phone", valid_numbers)
    def test_valid_phone_passes(self, phone: str):
        validator = ZambianPhoneValidator()
        validator(phone)  # Should not raise

    @pytest.mark.parametrize("phone", invalid_numbers)
    def test_invalid_phone_raises(self, phone: str):
        validator = ZambianPhoneValidator()
        with pytest.raises(ValidationError):
            validator(phone)


class TestZambianNRCValidator:
    valid_nrcs = [
        "123456/78/1",
        "000001/99/9",
        "654321/00/5",
    ]
    invalid_nrcs = [
        "12345/78/1",      # Too few digits in segment 1
        "1234567/78/1",    # Too many digits in segment 1
        "123456/789/1",    # Too many digits in segment 2
        "123456/78/0",     # Check digit cannot be 0
        "123456-78-1",     # Wrong separator
        "123456/78/",      # Missing check digit
        "",
        "ABC456/78/1",     # Non-numeric
    ]

    @pytest.mark.parametrize("nrc", valid_nrcs)
    def test_valid_nrc_passes(self, nrc: str):
        validator = ZambianNRCValidator()
        validator(nrc)

    @pytest.mark.parametrize("nrc", invalid_nrcs)
    def test_invalid_nrc_raises(self, nrc: str):
        validator = ZambianNRCValidator()
        with pytest.raises(ValidationError):
            validator(nrc)
