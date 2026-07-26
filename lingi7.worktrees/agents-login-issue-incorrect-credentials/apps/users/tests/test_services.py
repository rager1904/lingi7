"""
apps/users/tests/test_services.py
----------------------------------
Tests for UserService — all registration and KYC lifecycle paths.

Coverage:
- register(): happy path, duplicate phone, no consent, invalid phone
- kyc_submit(): valid transition, duplicate NRC, invalid state transitions
- kyc_approve(): happy path, wrong state
- kyc_reject(): happy path, missing reason, wrong state
- REJECTED → PENDING re-submission
- freeze_account() / unfreeze_account()
- request_data_deletion()
- Idempotency checks
"""

import pytest
from django.utils import timezone

from apps.users.models import KYCStatus, User, UserRole
from apps.users.services import (
    ConsentNotGivenError,
    DuplicateNRCError,
    DuplicatePhoneError,
    InvalidKYCTransitionError,
    UserService,
)


# ------------------------------------------------------------------ #
# Fixtures                                                            #
# ------------------------------------------------------------------ #


@pytest.fixture
def service() -> UserService:
    return UserService()


@pytest.fixture
def admin_user(db) -> User:
    return User.objects.create_superuser(
        phone_number="+260971000001",
        password="Admin@pass1!",
        first_name="Admin",
        last_name="Lingi7",
    )


@pytest.fixture
def fresh_user(db) -> User:
    """Freshly registered user — UNVERIFIED KYC, not frozen."""
    return User.objects.create_user(
        phone_number="+260971000002",
        password="Buyer@pass1!",
        first_name="Fresh",
        last_name="User",
    )


@pytest.fixture
def pending_user(fresh_user: User, service: UserService) -> User:
    """User who has submitted KYC — status PENDING."""
    return service.kyc_submit(
        user_id=str(fresh_user.id),
        nrc_number="123456/78/1",
        physical_address="Plot 12, Kabwe Road, Kitwe",
        province="Copperbelt",
        nrc_front_key="kyc/nrc_front_abc123.jpg",
        nrc_back_key="kyc/nrc_back_abc123.jpg",
        selfie_key="kyc/selfie_abc123.jpg",
    )


@pytest.fixture
def verified_user(pending_user: User, admin_user: User, service: UserService) -> User:
    """User with approved KYC — status VERIFIED."""
    return service.kyc_approve(
        user_id=str(pending_user.id), reviewed_by=admin_user
    )


@pytest.fixture
def rejected_user(pending_user: User, admin_user: User, service: UserService) -> User:
    """User with rejected KYC — status REJECTED."""
    return service.kyc_reject(
        user_id=str(pending_user.id),
        reviewed_by=admin_user,
        rejection_reason="NRC image is blurry. Please resubmit a clearer photo.",
    )


# ------------------------------------------------------------------ #
# register()                                                          #
# ------------------------------------------------------------------ #


class TestRegister:
    def test_creates_user_successfully(self, db, service: UserService):
        result = service.register(
            phone_number="+260977111111",
            password="Secure@pass1!",
            first_name="John",
            last_name="Phiri",
            consent_given=True,
        )
        assert result.created is True
        assert result.user.phone_number == "+260977111111"
        assert result.user.kyc_status == KYCStatus.UNVERIFIED
        assert result.user.role == UserRole.BUYER

    def test_consent_given_at_is_recorded(self, db, service: UserService):
        before = timezone.now()
        result = service.register(
            phone_number="+260977222222",
            password="Secure@pass1!",
            first_name="Jane",
            last_name="Mulenga",
            consent_given=True,
        )
        assert result.user.consent_given_at is not None
        assert result.user.consent_given_at >= before

    def test_raises_without_consent(self, db, service: UserService):
        with pytest.raises(ConsentNotGivenError):
            service.register(
                phone_number="+260977333333",
                password="pass",
                first_name="No",
                last_name="Consent",
                consent_given=False,
            )

    def test_raises_on_duplicate_phone(self, fresh_user: User, service: UserService):
        with pytest.raises(DuplicatePhoneError):
            service.register(
                phone_number=fresh_user.phone_number,
                password="Secure@pass1!",
                first_name="Dup",
                last_name="User",
                consent_given=True,
            )

    def test_vendor_role_assigned(self, db, service: UserService):
        result = service.register(
            phone_number="+260977444444",
            password="Secure@pass1!",
            first_name="Vendor",
            last_name="User",
            role=UserRole.VENDOR,
            consent_given=True,
        )
        assert result.user.role == UserRole.VENDOR


# ------------------------------------------------------------------ #
# kyc_submit()                                                        #
# ------------------------------------------------------------------ #


class TestKYCSubmit:
    def _submit(self, service: UserService, user: User, nrc: str = "123456/78/2") -> User:
        return service.kyc_submit(
            user_id=str(user.id),
            nrc_number=nrc,
            physical_address="Plot 5, Ndola, Copperbelt",
            province="Copperbelt",
            nrc_front_key="kyc/front.jpg",
            nrc_back_key="kyc/back.jpg",
            selfie_key="kyc/selfie.jpg",
        )

    def test_transitions_to_pending(self, fresh_user: User, service: UserService):
        user = self._submit(service, fresh_user)
        assert user.kyc_status == KYCStatus.PENDING

    def test_nrc_is_saved(self, fresh_user: User, service: UserService):
        user = self._submit(service, fresh_user, nrc="654321/99/3")
        user.refresh_from_db()
        assert user.nrc_number == "654321/99/3"

    def test_kyc_submitted_at_is_set(self, fresh_user: User, service: UserService):
        before = timezone.now()
        user = self._submit(service, fresh_user)
        assert user.kyc_submitted_at is not None
        assert user.kyc_submitted_at >= before

    def test_raises_on_duplicate_nrc(self, fresh_user: User, service: UserService, db: None):
        """Two different users cannot share the same NRC."""
        other_user = User.objects.create_user(
            phone_number="+260977555555",
            password="pass",
            first_name="Other",
            last_name="User",
        )
        # First user claims the NRC
        self._submit(service, fresh_user, nrc="111111/11/1")

        # Second user attempts to use the same NRC
        with pytest.raises(DuplicateNRCError):
            service.kyc_submit(
                user_id=str(other_user.id),
                nrc_number="111111/11/1",
                physical_address="Plot 6, Lusaka",
                province="Lusaka",
                nrc_front_key="kyc/front2.jpg",
                nrc_back_key="kyc/back2.jpg",
                selfie_key="kyc/selfie2.jpg",
            )

    def test_raises_when_already_pending(self, pending_user: User, service: UserService):
        """Cannot re-submit while already PENDING."""
        with pytest.raises(InvalidKYCTransitionError):
            self._submit(service, pending_user)

    def test_raises_when_already_verified(self, verified_user: User, service: UserService):
        """Cannot re-submit when already VERIFIED."""
        with pytest.raises(InvalidKYCTransitionError):
            self._submit(service, verified_user)

    def test_resubmission_allowed_after_rejection(
        self, rejected_user: User, service: UserService
    ):
        """REJECTED → PENDING is a valid transition."""
        user = self._submit(service, rejected_user, nrc="222222/22/2")
        assert user.kyc_status == KYCStatus.PENDING
        assert user.kyc_rejection_reason == ""  # Cleared on re-submit


# ------------------------------------------------------------------ #
# kyc_approve()                                                       #
# ------------------------------------------------------------------ #


class TestKYCApprove:
    def test_transitions_to_verified(
        self, pending_user: User, admin_user: User, service: UserService
    ):
        user = service.kyc_approve(
            user_id=str(pending_user.id), reviewed_by=admin_user
        )
        assert user.kyc_status == KYCStatus.VERIFIED

    def test_reviewed_by_is_recorded(
        self, pending_user: User, admin_user: User, service: UserService
    ):
        user = service.kyc_approve(
            user_id=str(pending_user.id), reviewed_by=admin_user
        )
        user.refresh_from_db()
        assert user.kyc_reviewed_by == admin_user

    def test_kyc_reviewed_at_is_set(
        self, pending_user: User, admin_user: User, service: UserService
    ):
        before = timezone.now()
        user = service.kyc_approve(
            user_id=str(pending_user.id), reviewed_by=admin_user
        )
        assert user.kyc_reviewed_at >= before

    def test_raises_when_not_pending(
        self, fresh_user: User, admin_user: User, service: UserService
    ):
        """Cannot approve from UNVERIFIED state."""
        with pytest.raises(InvalidKYCTransitionError):
            service.kyc_approve(user_id=str(fresh_user.id), reviewed_by=admin_user)

    def test_raises_when_already_verified(
        self, verified_user: User, admin_user: User, service: UserService
    ):
        with pytest.raises(InvalidKYCTransitionError):
            service.kyc_approve(user_id=str(verified_user.id), reviewed_by=admin_user)

    def test_user_not_found_raises(self, admin_user: User, service: UserService):
        import uuid
        with pytest.raises(User.DoesNotExist):
            service.kyc_approve(user_id=str(uuid.uuid4()), reviewed_by=admin_user)


# ------------------------------------------------------------------ #
# kyc_reject()                                                        #
# ------------------------------------------------------------------ #


class TestKYCReject:
    def test_transitions_to_rejected(
        self, pending_user: User, admin_user: User, service: UserService
    ):
        user = service.kyc_reject(
            user_id=str(pending_user.id),
            reviewed_by=admin_user,
            rejection_reason="NRC image too blurry.",
        )
        assert user.kyc_status == KYCStatus.REJECTED

    def test_rejection_reason_is_saved(
        self, pending_user: User, admin_user: User, service: UserService
    ):
        user = service.kyc_reject(
            user_id=str(pending_user.id),
            reviewed_by=admin_user,
            rejection_reason="Selfie does not match NRC photo.",
        )
        user.refresh_from_db()
        assert user.kyc_rejection_reason == "Selfie does not match NRC photo."

    def test_raises_without_rejection_reason(
        self, pending_user: User, admin_user: User, service: UserService
    ):
        with pytest.raises(ValueError, match="rejection_reason is required"):
            service.kyc_reject(
                user_id=str(pending_user.id),
                reviewed_by=admin_user,
                rejection_reason="",
            )

    def test_raises_with_whitespace_only_reason(
        self, pending_user: User, admin_user: User, service: UserService
    ):
        with pytest.raises(ValueError):
            service.kyc_reject(
                user_id=str(pending_user.id),
                reviewed_by=admin_user,
                rejection_reason="   ",
            )

    def test_raises_when_not_pending(
        self, fresh_user: User, admin_user: User, service: UserService
    ):
        with pytest.raises(InvalidKYCTransitionError):
            service.kyc_reject(
                user_id=str(fresh_user.id),
                reviewed_by=admin_user,
                rejection_reason="Some reason.",
            )


# ------------------------------------------------------------------ #
# freeze_account() / unfreeze_account()                               #
# ------------------------------------------------------------------ #


class TestFreezeUnfreeze:
    def test_freeze_sets_is_frozen(self, fresh_user: User, admin_user: User, service: UserService):
        user = service.freeze_account(
            user_id=str(fresh_user.id),
            reason="Suspicious login pattern detected.",
            frozen_by=admin_user,
        )
        assert user.is_frozen is True
        assert user.frozen_reason == "Suspicious login pattern detected."
        assert user.frozen_at is not None

    def test_unfreeze_clears_frozen(self, fresh_user: User, admin_user: User, service: UserService):
        service.freeze_account(
            user_id=str(fresh_user.id), reason="Test freeze.", frozen_by=admin_user
        )
        user = service.unfreeze_account(
            user_id=str(fresh_user.id), unfrozen_by=admin_user
        )
        assert user.is_frozen is False
        assert user.frozen_reason == ""

    def test_system_freeze_no_actor(self, fresh_user: User, service: UserService):
        """Automated fraud engine can freeze without a human actor."""
        user = service.freeze_account(
            user_id=str(fresh_user.id),
            reason="fraud_rule:velocity_exceeded",
            frozen_by=None,
        )
        assert user.is_frozen is True


# ------------------------------------------------------------------ #
# request_data_deletion()                                             #
# ------------------------------------------------------------------ #


class TestDataDeletion:
    def test_sets_deletion_timestamp(self, fresh_user: User, service: UserService):
        before = timezone.now()
        user = service.request_data_deletion(user_id=str(fresh_user.id))
        assert user.data_deletion_requested_at is not None
        assert user.data_deletion_requested_at >= before

    def test_idempotent_on_repeat_call(self, fresh_user: User, service: UserService):
        """Second call should not overwrite the original timestamp."""
        user1 = service.request_data_deletion(user_id=str(fresh_user.id))
        first_ts = user1.data_deletion_requested_at

        user2 = service.request_data_deletion(user_id=str(fresh_user.id))
        assert user2.data_deletion_requested_at == first_ts
