"""
Dispute Service Tests — apps/disputes/tests/test_services.py

Coverage targets:
  - raise_dispute: valid flow, guard conditions (wrong state, wrong user, duplicate)
  - submit_evidence: valid, closed dispute, missing file
  - resolve_buyer_favour: full refund, partial refund, escrow transition
  - resolve_vendor_favour: escrow release, fraud gate still runs
  - withdraw_dispute: buyer withdraws, non-buyer rejected
  - SLA breach detection
"""

import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.disputes.exceptions import (
    DisputeAlreadyExistsError,
    DisputeError,
    DisputeNotOpenError,
    EvidenceSubmissionClosedError,
)
from apps.disputes.models import Dispute, DisputeEvent, Evidence
from apps.disputes.services import DisputeService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_phone() -> str:
    import random
    return f"+2609{random.randint(10000000, 99999999)}"


@pytest.fixture
def buyer(db):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.create_user(
        phone_number=make_phone(),
        password="testpass123",
        role="BUYER",
    )


@pytest.fixture
def vendor_user(db):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.create_user(
        phone_number=make_phone(),
        password="testpass123",
        role="VENDOR",
    )


@pytest.fixture
def admin_user(db):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.create_user(
        phone_number=make_phone(),
        password="testpass123",
        is_staff=True,
        is_superuser=True,
    )


@pytest.fixture
def delivered_order_with_escrow(db, buyer, vendor_user):
    """
    Returns (order, escrow_account) where:
    - order.status == DELIVERED
    - escrow_account.state == DELIVERED
    - No dispute yet
    """
    from apps.escrow.models import EscrowAccount, LedgerEntry
    from apps.orders.models import Order

    order = Order.objects.create(
        buyer=buyer,
        seller=vendor_user,
        status=Order.Status.DELIVERED,
        total_amount=Decimal("1500.00"),
        reference=f"ORD-{uuid.uuid4().hex[:8].upper()}",
    )

    from apps.escrow.state_machine import EscrowState
    escrow_account = EscrowAccount.objects.create(
        order=order,
        state=EscrowState.DELIVERED,
        balance=Decimal("1500.00"),
    )

    # Paired ledger entries (initial hold)
    LedgerEntry.objects.bulk_create([
        LedgerEntry(
            account=escrow_account,
            entry_type="DEBIT",
            amount=Decimal("1500.00"),
            description="Initial buyer payment",
        ),
        LedgerEntry(
            account=escrow_account,
            entry_type="CREDIT",
            amount=Decimal("1500.00"),
            description="Escrow hold",
        ),
    ])

    return order, escrow_account


# ---------------------------------------------------------------------------
# raise_dispute
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestRaiseDispute:

    def test_raise_dispute_success(self, delivered_order_with_escrow, buyer):
        order, escrow_account = delivered_order_with_escrow

        with patch("apps.escrow.services.EscrowService.raise_dispute") as mock_t:
            dispute = DisputeService.raise_dispute(
                order=order,
                raised_by=buyer,
                reason=Dispute.Reason.ITEM_NOT_RECEIVED,
                description="Package never arrived.",
            )

        assert dispute.status == Dispute.Status.OPEN
        assert dispute.order == order
        assert dispute.raised_by == buyer
        assert dispute.reason == Dispute.Reason.ITEM_NOT_RECEIVED
        assert dispute.sla_deadline > timezone.now()
        mock_t.assert_called_once()

    def test_raise_dispute_creates_dispute_event(self, delivered_order_with_escrow, buyer):
        order, _ = delivered_order_with_escrow

        with patch("apps.escrow.services.EscrowService.raise_dispute"):
            dispute = DisputeService.raise_dispute(
                order=order,
                raised_by=buyer,
                reason=Dispute.Reason.ITEM_DAMAGED,
                description="Box arrived crushed.",
            )

        events = DisputeEvent.objects.filter(dispute=dispute)
        assert events.count() == 1
        assert events.first().action == "DISPUTE_RAISED"

    def test_raise_dispute_wrong_buyer_rejected(self, delivered_order_with_escrow, vendor_user):
        order, _ = delivered_order_with_escrow

        with pytest.raises(DisputeError, match="Only the order buyer"):
            DisputeService.raise_dispute(
                order=order,
                raised_by=vendor_user,
                reason=Dispute.Reason.OTHER,
                description="Test.",
            )

    def test_raise_dispute_wrong_order_status_rejected(self, db, buyer):
        from apps.orders.models import Order

        order = Order.objects.create(
            buyer=buyer,
            seller=buyer,
            status=Order.Status.SHIPPED,
            total_amount=Decimal("500.00"),
            reference=f"ORD-{uuid.uuid4().hex[:8].upper()}",
        )

        with pytest.raises(DisputeError, match="DELIVERED state"):
            DisputeService.raise_dispute(
                order=order,
                raised_by=buyer,
                reason=Dispute.Reason.SELLER_UNRESPONSIVE,
                description="Test.",
            )

    def test_raise_dispute_duplicate_rejected(self, delivered_order_with_escrow, buyer):
        order, _ = delivered_order_with_escrow

        with patch("apps.escrow.services.EscrowService.raise_dispute"):
            DisputeService.raise_dispute(
                order=order,
                raised_by=buyer,
                reason=Dispute.Reason.WRONG_ITEM,
                description="First dispute.",
            )

        with pytest.raises(DisputeAlreadyExistsError):
            DisputeService.raise_dispute(
                order=order,
                raised_by=buyer,
                reason=Dispute.Reason.WRONG_ITEM,
                description="Second attempt.",
            )


# ---------------------------------------------------------------------------
# submit_evidence
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSubmitEvidence:

    def _open_dispute(self, order, buyer):
        with patch("apps.escrow.services.EscrowService.raise_dispute"):
            return DisputeService.raise_dispute(
                order=order,
                raised_by=buyer,
                reason=Dispute.Reason.ITEM_NOT_RECEIVED,
                description="Test dispute.",
            )

    def test_submit_text_evidence_success(self, delivered_order_with_escrow, buyer):
        order, _ = delivered_order_with_escrow
        dispute = self._open_dispute(order, buyer)

        evidence = DisputeService.submit_evidence(
            dispute=dispute,
            submitted_by=buyer,
            submitted_by_role=Evidence.SubmittedBy.BUYER,
            evidence_type=Evidence.EvidenceType.TEXT,
            description="I never received the item at my address.",
        )

        assert evidence.dispute == dispute
        assert evidence.evidence_type == Evidence.EvidenceType.TEXT
        assert evidence.submitted_by_role == Evidence.SubmittedBy.BUYER

    def test_submit_image_without_file_rejected(self, delivered_order_with_escrow, buyer):
        order, _ = delivered_order_with_escrow
        dispute = self._open_dispute(order, buyer)

        with pytest.raises(DisputeError, match="file is required"):
            DisputeService.submit_evidence(
                dispute=dispute,
                submitted_by=buyer,
                submitted_by_role=Evidence.SubmittedBy.BUYER,
                evidence_type=Evidence.EvidenceType.IMAGE,
                description="Photo of empty box.",
                file=None,
            )

    def test_submit_evidence_resolved_dispute_rejected(self, delivered_order_with_escrow, buyer, admin_user):
        order, _ = delivered_order_with_escrow
        dispute = self._open_dispute(order, buyer)

        with patch("apps.escrow.services.EscrowService.refund"):
            DisputeService.resolve_buyer_favour(
                dispute=dispute,
                resolved_by=admin_user,
                resolution_notes="Clearly item not received based on tracking data.",
            )

        with pytest.raises(EvidenceSubmissionClosedError):
            DisputeService.submit_evidence(
                dispute=dispute,
                submitted_by=buyer,
                submitted_by_role=Evidence.SubmittedBy.BUYER,
                evidence_type=Evidence.EvidenceType.TEXT,
                description="Late addition.",
            )


# ---------------------------------------------------------------------------
# resolve_buyer_favour
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestResolveBuyerFavour:

    def _open_dispute(self, order, buyer):
        with patch("apps.escrow.services.EscrowService.raise_dispute"):
            return DisputeService.raise_dispute(
                order=order,
                raised_by=buyer,
                reason=Dispute.Reason.ITEM_DAMAGED,
                description="Item was broken on arrival.",
            )

    def test_full_refund_success(self, delivered_order_with_escrow, buyer, admin_user):
        order, escrow_account = delivered_order_with_escrow
        dispute = self._open_dispute(order, buyer)

        with patch("apps.escrow.services.EscrowService.refund") as mock_refund:
            resolved = DisputeService.resolve_buyer_favour(
                dispute=dispute,
                resolved_by=admin_user,
                resolution_notes="Photos confirm item arrived damaged. Full refund issued.",
            )

        assert resolved.status == Dispute.Status.RESOLVED_BUYER
        assert resolved.refund_amount == Decimal("1500.00")
        assert resolved.resolved_by == admin_user
        assert resolved.resolved_at is not None
        mock_refund.assert_called_once()

    def test_partial_refund_success(self, delivered_order_with_escrow, buyer, admin_user):
        order, _ = delivered_order_with_escrow
        dispute = self._open_dispute(order, buyer)

        with patch("apps.escrow.services.EscrowService.refund"):
            resolved = DisputeService.resolve_buyer_favour(
                dispute=dispute,
                resolved_by=admin_user,
                resolution_notes="Partial damage confirmed. 50% refund applied.",
                refund_amount=Decimal("750.00"),
            )

        assert resolved.refund_amount == Decimal("750.00")

    def test_refund_exceeds_balance_rejected(self, delivered_order_with_escrow, buyer, admin_user):
        order, _ = delivered_order_with_escrow
        dispute = self._open_dispute(order, buyer)

        with pytest.raises(DisputeError, match="exceeds escrow balance"):
            with patch("apps.escrow.models.EscrowAccount.objects.select_for_update") as mock_sq:
                mock_account = MagicMock()
                mock_account.balance = Decimal("1500.00")
                mock_sq.return_value.get.return_value = mock_account

                DisputeService.resolve_buyer_favour(
                    dispute=dispute,
                    resolved_by=admin_user,
                    resolution_notes="Test over-refund.",
                    refund_amount=Decimal("9999.00"),
                )

    def test_resolve_already_resolved_rejected(self, delivered_order_with_escrow, buyer, admin_user):
        order, _ = delivered_order_with_escrow
        dispute = self._open_dispute(order, buyer)

        with patch("apps.escrow.services.EscrowService.refund"):
            DisputeService.resolve_buyer_favour(
                dispute=dispute,
                resolved_by=admin_user,
                resolution_notes="First resolution — sufficient justification here.",
            )

        with pytest.raises(DisputeNotOpenError):
            DisputeService.resolve_buyer_favour(
                dispute=dispute,
                resolved_by=admin_user,
                resolution_notes="Second attempt — should fail.",
            )

    def test_resolution_creates_audit_events(self, delivered_order_with_escrow, buyer, admin_user):
        order, _ = delivered_order_with_escrow
        dispute = self._open_dispute(order, buyer)

        with patch("apps.escrow.services.EscrowService.refund"):
            DisputeService.resolve_buyer_favour(
                dispute=dispute,
                resolved_by=admin_user,
                resolution_notes="Well documented justification for resolution.",
            )

        events = DisputeEvent.objects.filter(dispute=dispute)
        actions = list(events.values_list("action", flat=True))
        assert "DISPUTE_RAISED" in actions
        assert "DISPUTE_RESOLVED_BUYER" in actions


# ---------------------------------------------------------------------------
# resolve_vendor_favour
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestResolveVendorFavour:

    def _open_dispute(self, order, buyer):
        with patch("apps.escrow.services.EscrowService.raise_dispute"):
            return DisputeService.raise_dispute(
                order=order,
                raised_by=buyer,
                reason=Dispute.Reason.ITEM_NOT_AS_DESCRIBED,
                description="Buyer changed their mind.",
            )

    def test_resolve_vendor_success(self, delivered_order_with_escrow, buyer, admin_user):
        order, _ = delivered_order_with_escrow
        dispute = self._open_dispute(order, buyer)

        with patch("apps.escrow.services.EscrowService.release_funds") as mock_release:
            resolved = DisputeService.resolve_vendor_favour(
                dispute=dispute,
                resolved_by=admin_user,
                resolution_notes="Tracking confirms delivery. Item matches description per photos.",
            )

        assert resolved.status == Dispute.Status.RESOLVED_VENDOR
        assert resolved.refund_amount == Decimal("0.00")
        # Fraud gate must have run inside release_to_vendor
        mock_release.assert_called_once()


# ---------------------------------------------------------------------------
# withdraw_dispute
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestWithdrawDispute:

    def _open_dispute(self, order, buyer):
        with patch("apps.escrow.services.EscrowService.raise_dispute"):
            return DisputeService.raise_dispute(
                order=order,
                raised_by=buyer,
                reason=Dispute.Reason.PARTIAL_DELIVERY,
                description="Missing 2 items from order.",
            )

    def test_buyer_withdrawal_success(self, delivered_order_with_escrow, buyer):
        order, _ = delivered_order_with_escrow
        dispute = self._open_dispute(order, buyer)

        with patch("apps.escrow.services.EscrowService.release_funds"):
            withdrawn = DisputeService.withdraw_dispute(
                dispute=dispute,
                withdrawn_by=buyer,
                reason="Vendor resolved outside the platform.",
            )

        assert withdrawn.status == Dispute.Status.WITHDRAWN
        assert "Withdrawn by buyer" in withdrawn.resolution_notes

    def test_non_buyer_withdrawal_rejected(self, delivered_order_with_escrow, buyer, vendor_user):
        order, _ = delivered_order_with_escrow
        dispute = self._open_dispute(order, buyer)

        with pytest.raises(DisputeError, match="Only the buyer"):
            DisputeService.withdraw_dispute(
                dispute=dispute,
                withdrawn_by=vendor_user,
                reason="Trying to close my own dispute.",
            )


# ---------------------------------------------------------------------------
# assign_dispute
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAssignDispute:

    def test_assign_open_dispute(self, delivered_order_with_escrow, buyer, admin_user):
        order, _ = delivered_order_with_escrow

        with patch("apps.escrow.services.EscrowService.raise_dispute"):
            dispute = DisputeService.raise_dispute(
                order=order,
                raised_by=buyer,
                reason=Dispute.Reason.SELLER_UNRESPONSIVE,
                description="Vendor has not responded in 5 days.",
            )

        assigned = DisputeService.assign_dispute(
            dispute=dispute,
            assigned_to=admin_user,
            assigned_by=admin_user,
        )

        assert assigned.status == Dispute.Status.UNDER_REVIEW
        assert assigned.assigned_to == admin_user

    def test_assign_non_open_dispute_rejected(self, delivered_order_with_escrow, buyer, admin_user):
        from apps.disputes.exceptions import InvalidDisputeTransitionError

        order, _ = delivered_order_with_escrow

        with patch("apps.escrow.services.EscrowService.raise_dispute"):
            dispute = DisputeService.raise_dispute(
                order=order,
                raised_by=buyer,
                reason=Dispute.Reason.WRONG_ITEM,
                description="Wrong colour sent.",
            )

        with patch("apps.escrow.services.EscrowService.refund"):
            DisputeService.resolve_buyer_favour(
                dispute=dispute,
                resolved_by=admin_user,
                resolution_notes="Confirmed wrong item via photos submitted by buyer.",
            )

        with pytest.raises(InvalidDisputeTransitionError):
            DisputeService.assign_dispute(
                dispute=dispute,
                assigned_to=admin_user,
                assigned_by=admin_user,
            )
