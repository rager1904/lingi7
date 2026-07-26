"""
apps/escrow/tests/test_services.py

Comprehensive pytest suite for EscrowService.

Covers:
- Account creation
- Full lifecycle: PENDING → HELD → IN_TRANSIT → DELIVERED → RELEASED
- Double-entry ledger integrity
- Fraud gate: clear path and freeze path
- Dispute → refund path
- Manual freeze
- Concurrent write safety (select_for_update)
- Invalid operation guards
- LedgerEntry immutability
"""
from __future__ import annotations

import threading
import uuid
from decimal import Decimal

import pytest

from apps.escrow.exceptions import (
    EscrowAlreadyExistsError,
    FraudGateError,
    InsufficientBalanceError,
    InvalidTransitionError,
    LedgerImbalanceError,
)
from apps.escrow.models import (
    EscrowAccount,
    FraudGateLog,
    LedgerEntry,
)
from apps.escrow.services import EscrowService
from apps.escrow.state_machine import EscrowState

pytestmark = pytest.mark.django_db(transaction=True)


# ===========================================================================
# Account creation
# ===========================================================================

class TestCreateAccount:

    def test_creates_in_pending_state(self, order_ref, buyer_ref) -> None:
        account = EscrowService.create_account(
            order_ref=order_ref, buyer_ref=buyer_ref
        )
        assert account.state == EscrowState.PENDING
        assert account.balance == Decimal("0.00")
        assert account.currency == "ZMW"

    def test_sets_buyer_and_vendor_refs(self, order_ref, buyer_ref, vendor_ref) -> None:
        account = EscrowService.create_account(
            order_ref=order_ref, buyer_ref=buyer_ref, vendor_ref=vendor_ref
        )
        assert account.buyer_ref == buyer_ref
        assert account.vendor_ref == vendor_ref

    def test_duplicate_order_ref_raises(self, order_ref, buyer_ref) -> None:
        EscrowService.create_account(order_ref=order_ref, buyer_ref=buyer_ref)
        with pytest.raises(EscrowAlreadyExistsError):
            EscrowService.create_account(order_ref=order_ref, buyer_ref=buyer_ref)

    def test_stores_in_db(self, order_ref, buyer_ref) -> None:
        account = EscrowService.create_account(
            order_ref=order_ref, buyer_ref=buyer_ref
        )
        db_account = EscrowAccount.objects.get(pk=account.id)
        assert db_account.state == EscrowState.PENDING


# ===========================================================================
# Hold funds (PENDING → HELD)
# ===========================================================================

class TestHoldFunds:

    def test_transitions_to_held(self, pending_account) -> None:
        account = EscrowService.hold_funds(
            account_id=pending_account.id,
            amount=Decimal("500.00"),
            payment_provider="MTN",
            collection_ref="REF-001",
        )
        assert account.state == EscrowState.HELD

    def test_updates_balance(self, pending_account) -> None:
        account = EscrowService.hold_funds(
            account_id=pending_account.id,
            amount=Decimal("750.00"),
            payment_provider="AIRTEL",
            collection_ref="REF-002",
        )
        assert account.balance == Decimal("750.00")

    def test_writes_ledger_pair(self, pending_account) -> None:
        EscrowService.hold_funds(
            account_id=pending_account.id,
            amount=Decimal("1000.00"),
            payment_provider="MTN",
            collection_ref="REF-003",
        )
        entries = LedgerEntry.objects.filter(account=pending_account)
        assert entries.count() == 2
        debits = entries.filter(entry_type=LedgerEntry.EntryType.DEBIT)
        credits = entries.filter(entry_type=LedgerEntry.EntryType.CREDIT)
        assert debits.count() == 1
        assert credits.count() == 1
        assert debits.first().amount == credits.first().amount == Decimal("1000.00")

    def test_same_operation_ref_on_pair(self, pending_account) -> None:
        EscrowService.hold_funds(
            account_id=pending_account.id,
            amount=Decimal("200.00"),
            payment_provider="MTN",
            collection_ref="REF-004",
        )
        entries = LedgerEntry.objects.filter(account=pending_account)
        refs = set(entries.values_list("operation_ref", flat=True))
        assert len(refs) == 1  # Both entries share the same operation_ref

    def test_zero_amount_raises(self, pending_account) -> None:
        with pytest.raises(ValueError, match="positive"):
            EscrowService.hold_funds(
                account_id=pending_account.id,
                amount=Decimal("0.00"),
                payment_provider="MTN",
                collection_ref="REF-005",
            )

    def test_negative_amount_raises(self, pending_account) -> None:
        with pytest.raises(ValueError, match="positive"):
            EscrowService.hold_funds(
                account_id=pending_account.id,
                amount=Decimal("-100.00"),
                payment_provider="MTN",
                collection_ref="REF-006",
            )

    def test_invalid_transition_raises(self, held_account) -> None:
        """Can't hold funds on an already-HELD account."""
        with pytest.raises(InvalidTransitionError):
            EscrowService.hold_funds(
                account_id=held_account.id,
                amount=Decimal("500.00"),
                payment_provider="MTN",
                collection_ref="REF-DUP",
            )

    def test_creates_escrow_hold_record(self, pending_account) -> None:
        EscrowService.hold_funds(
            account_id=pending_account.id,
            amount=Decimal("1200.00"),
            payment_provider="AIRTEL",
            collection_ref="AIRTEL-REF-001",
        )
        assert hasattr(pending_account, "hold") or \
               pending_account.__class__.objects.get(pk=pending_account.id).hold is not None


# ===========================================================================
# Mark in-transit (HELD → IN_TRANSIT)
# ===========================================================================

class TestMarkInTransit:

    def test_transitions_to_in_transit(self, held_account) -> None:
        account = EscrowService.mark_in_transit(account_id=held_account.id)
        assert account.state == EscrowState.IN_TRANSIT

    def test_balance_unchanged(self, held_account) -> None:
        original_balance = held_account.balance
        account = EscrowService.mark_in_transit(account_id=held_account.id)
        assert account.balance == original_balance

    def test_no_new_ledger_entries(self, held_account) -> None:
        entry_count_before = LedgerEntry.objects.filter(account=held_account).count()
        EscrowService.mark_in_transit(account_id=held_account.id)
        entry_count_after = LedgerEntry.objects.filter(account=held_account).count()
        assert entry_count_before == entry_count_after

    def test_invalid_from_pending_raises(self, pending_account) -> None:
        with pytest.raises(InvalidTransitionError):
            EscrowService.mark_in_transit(account_id=pending_account.id)


# ===========================================================================
# Mark delivered (IN_TRANSIT → DELIVERED)
# ===========================================================================

class TestMarkDelivered:

    def test_transitions_to_delivered(self, in_transit_account) -> None:
        account = EscrowService.mark_delivered(account_id=in_transit_account.id)
        assert account.state == EscrowState.DELIVERED

    def test_invalid_from_held_raises(self, held_account) -> None:
        """HELD → DELIVERED is NOT valid. Must go through IN_TRANSIT."""
        with pytest.raises(InvalidTransitionError):
            EscrowService.mark_delivered(account_id=held_account.id)
        
    def test_invalid_from_pending_raises(self, pending_account) -> None:
        with pytest.raises(InvalidTransitionError):
            EscrowService.mark_delivered(account_id=pending_account.id)


# ===========================================================================
# Release funds (DELIVERED → RELEASED) — core financial path
# ===========================================================================

class TestReleaseFunds:

    def test_transitions_to_released(self, delivered_account) -> None:
        account = EscrowService.release_funds(account_id=delivered_account.id)
        assert account.state == EscrowState.RELEASED

    def test_balance_zeroed_on_release(self, delivered_account) -> None:
        account = EscrowService.release_funds(account_id=delivered_account.id)
        assert account.balance == Decimal("0.00")

    def test_released_at_set(self, delivered_account) -> None:
        account = EscrowService.release_funds(account_id=delivered_account.id)
        assert account.released_at is not None

    def test_default_fee_rate_5_percent(self, delivered_account) -> None:
        """Default fee = 5% of ZMW 1000 = ZMW 50. Net = ZMW 950."""
        EscrowService.release_funds(account_id=delivered_account.id)
        entries = LedgerEntry.objects.filter(account=delivered_account)
        fee_entry = entries.filter(description__icontains="Platform fee").first()
        net_entry = entries.filter(description__icontains="Vendor net").first()
        assert fee_entry is not None
        assert net_entry is not None
        assert fee_entry.amount == Decimal("50.00")
        assert net_entry.amount == Decimal("950.00")

    def test_custom_fee_rate(self, delivered_account) -> None:
        """3% fee on ZMW 1000 = ZMW 30. Net = ZMW 970."""
        EscrowService.release_funds(
            account_id=delivered_account.id,
            fee_rate=Decimal("0.03"),
        )
        fee_entry = LedgerEntry.objects.filter(
            account=delivered_account, description__icontains="fee"
        ).first()
        assert fee_entry.amount == Decimal("30.00")

    def test_three_ledger_entries_on_release(self, delivered_account) -> None:
        """Release creates 3 entries: gross debit + fee credit + net credit."""
        entries_before = LedgerEntry.objects.filter(account=delivered_account).count()
        EscrowService.release_funds(account_id=delivered_account.id)
        entries_after = LedgerEntry.objects.filter(account=delivered_account).count()
        new_entries = entries_after - entries_before
        assert new_entries == 3

    def test_double_entry_integrity_on_release(self, delivered_account) -> None:
        """Sum of release debits must equal sum of release credits."""
        EscrowService.release_funds(account_id=delivered_account.id)
        # Get the release operation_ref (the last set of entries)
        last_op = (
            LedgerEntry.objects.filter(account=delivered_account)
            .order_by("-created_at")
            .values_list("operation_ref", flat=True)
            .first()
        )
        entries = LedgerEntry.objects.filter(account=delivered_account, operation_ref=last_op)
        debit_total = sum(e.amount for e in entries if e.entry_type == LedgerEntry.EntryType.DEBIT)
        credit_total = sum(e.amount for e in entries if e.entry_type == LedgerEntry.EntryType.CREDIT)
        assert debit_total == credit_total

    def test_fraud_gate_clears_with_no_flags(self, delivered_account) -> None:
        """No flags, no ML score → gate clears, release succeeds."""
        account = EscrowService.release_funds(
            account_id=delivered_account.id,
            fraud_rule_flags=[],
            ml_risk_score=None,
        )
        assert account.state == EscrowState.RELEASED
        log = FraudGateLog.objects.filter(account=delivered_account).first()
        assert log.verdict == "CLEAR"

    def test_fraud_gate_freezes_on_rule_flag(self, delivered_account) -> None:
        with pytest.raises(FraudGateError):
            EscrowService.release_funds(
                account_id=delivered_account.id,
                fraud_rule_flags=["HIGH_VALUE_NEW_ACCOUNT"],
            )
        # The freeze happens inside the atomic block before the exception propagates.
        # With transaction=True tests, we verify via the FraudGateLog instead.
        log = FraudGateLog.objects.filter(account_id=delivered_account.id).first()
        assert log is not None
        assert log.verdict == "FREEZE"

    def test_fraud_gate_freezes_on_high_ml_score(self, delivered_account) -> None:
        with pytest.raises(FraudGateError):
            EscrowService.release_funds(
                account_id=delivered_account.id,
                fraud_rule_flags=[],
                ml_risk_score=Decimal("0.75"),
            )
        log = FraudGateLog.objects.filter(account_id=delivered_account.id).first()
        assert log is not None
        assert log.verdict == "FREEZE"
        assert log.ml_risk_score == Decimal("0.75")

    def test_fraud_gate_log_written_on_freeze(self, delivered_account) -> None:
        with pytest.raises(FraudGateError):
            EscrowService.release_funds(
                account_id=delivered_account.id,
                fraud_rule_flags=["IP_BLACKLIST"],
                ml_risk_score=Decimal("0.80"),
            )
        log = FraudGateLog.objects.filter(account_id=delivered_account.id).first()
        assert log is not None
        assert log.verdict == "FREEZE"
        assert log.freeze_reason != ""
        
    def test_fraud_gate_clears_at_threshold_minus_epsilon(self, delivered_account) -> None:
        """ML score just below threshold → gate clears."""
        account = EscrowService.release_funds(
            account_id=delivered_account.id,
            fraud_rule_flags=[],
            ml_risk_score=Decimal("0.6499"),
        )
        assert account.state == EscrowState.RELEASED

    def test_fraud_gate_log_written_on_clear(self, delivered_account) -> None:
        EscrowService.release_funds(account_id=delivered_account.id)
        log = FraudGateLog.objects.filter(account=delivered_account).first()
        assert log is not None
        assert log.verdict == "CLEAR"

    def test_zero_balance_raises_insufficient(self, order_ref, buyer_ref) -> None:
        """Cannot release an account with zero balance."""
        account = EscrowService.create_account(order_ref=order_ref, buyer_ref=buyer_ref)
        # Force state to DELIVERED without funds
        EscrowAccount.objects.filter(pk=account.id).update(state=EscrowState.DELIVERED)
        account.refresh_from_db()
        with pytest.raises(InsufficientBalanceError):
            EscrowService.release_funds(account_id=account.id)

    def test_cannot_release_twice(self, delivered_account) -> None:
        EscrowService.release_funds(account_id=delivered_account.id)
        with pytest.raises(InvalidTransitionError):
            EscrowService.release_funds(account_id=delivered_account.id)


# ===========================================================================
# Raise dispute
# ===========================================================================

class TestRaiseDispute:

    def test_transitions_held_to_disputed(self, held_account) -> None:
        account = EscrowService.raise_dispute(account_id=held_account.id)
        assert account.state == EscrowState.DISPUTED

    def test_transitions_in_transit_to_disputed(self, in_transit_account) -> None:
        account = EscrowService.raise_dispute(account_id=in_transit_account.id)
        assert account.state == EscrowState.DISPUTED

    def test_transitions_delivered_to_disputed(self, delivered_account) -> None:
        account = EscrowService.raise_dispute(account_id=delivered_account.id)
        assert account.state == EscrowState.DISPUTED

    def test_balance_preserved_on_dispute(self, held_account) -> None:
        original_balance = held_account.balance
        account = EscrowService.raise_dispute(account_id=held_account.id)
        assert account.balance == original_balance

    def test_invalid_from_pending_raises(self, pending_account) -> None:
        with pytest.raises(InvalidTransitionError):
            EscrowService.raise_dispute(account_id=pending_account.id)


# ===========================================================================
# Refund
# ===========================================================================

class TestRefund:

    def test_refund_disputed_account(self, held_account) -> None:
        EscrowService.raise_dispute(account_id=held_account.id)
        account = EscrowService.refund(
            account_id=held_account.id, reason="Goods not received"
        )
        assert account.state == EscrowState.REFUNDED
        assert account.balance == Decimal("0.00")

    def test_refund_writes_ledger_entries(self, held_account) -> None:
        EscrowService.raise_dispute(account_id=held_account.id)
        entries_before = LedgerEntry.objects.filter(account=held_account).count()
        EscrowService.refund(account_id=held_account.id, reason="Test refund")
        entries_after = LedgerEntry.objects.filter(account=held_account).count()
        assert entries_after > entries_before

    def test_refund_double_entry_integrity(self, held_account) -> None:
        EscrowService.raise_dispute(account_id=held_account.id)
        EscrowService.refund(account_id=held_account.id, reason="Test")
        # Across ALL entries for this account, debits must equal credits
        entries = LedgerEntry.objects.filter(account=held_account)
        total_debit = sum(
            e.amount for e in entries if e.entry_type == LedgerEntry.EntryType.DEBIT
        )
        total_credit = sum(
            e.amount for e in entries if e.entry_type == LedgerEntry.EntryType.CREDIT
        )
        assert total_debit == total_credit

    def test_cannot_refund_released(self, delivered_account) -> None:
        EscrowService.release_funds(account_id=delivered_account.id)
        with pytest.raises(InvalidTransitionError):
            EscrowService.refund(account_id=delivered_account.id)

    def test_refund_from_held_directly(self, held_account) -> None:
        """HELD → REFUNDED is a valid path (seller SLA breach)."""
        account = EscrowService.refund(
            account_id=held_account.id, reason="Seller SLA breach"
        )
        assert account.state == EscrowState.REFUNDED


# ===========================================================================
# Manual freeze
# ===========================================================================

class TestFreeze:

    def test_freeze_held_account(self, held_account) -> None:
        account = EscrowService.freeze(account_id=held_account.id, reason="Manual review")
        assert account.state == EscrowState.FROZEN

    def test_frozen_at_set(self, held_account) -> None:
        account = EscrowService.freeze(account_id=held_account.id)
        assert account.frozen_at is not None

    def test_cannot_freeze_released(self, delivered_account) -> None:
        EscrowService.release_funds(account_id=delivered_account.id)
        with pytest.raises(InvalidTransitionError):
            EscrowService.freeze(account_id=delivered_account.id)

    def test_release_after_manual_freeze(self, delivered_account) -> None:
        """DELIVERED → FROZEN → (admin clears) → RELEASED."""
        EscrowService.freeze(account_id=delivered_account.id, reason="Suspected fraud")
        account = EscrowService.release_funds(
            account_id=delivered_account.id,
            fraud_rule_flags=[],
            ml_risk_score=Decimal("0.10"),
        )
        assert account.state == EscrowState.RELEASED


# ===========================================================================
# LedgerEntry immutability guards
# ===========================================================================

class TestLedgerImmutability:

    def test_ledger_entry_cannot_be_updated(self, held_account) -> None:
        entry = LedgerEntry.objects.filter(account=held_account).first()
        entry.description = "TAMPERED"
        entry._is_new = False  # simulate post-creation update attempt
        with pytest.raises(RuntimeError, match="immutable"):
            entry.save()

    def test_ledger_entry_cannot_be_deleted(self, held_account) -> None:
        entry = LedgerEntry.objects.filter(account=held_account).first()
        with pytest.raises(RuntimeError, match="cannot be deleted"):
            entry.delete()


# ===========================================================================
# Concurrent write safety
# ===========================================================================

class TestConcurrentWriteSafety:

    def test_concurrent_holds_produce_correct_ledger(
        self, order_ref, buyer_ref, vendor_ref
    ) -> None:
        """
        Two threads attempt to hold funds on the same account simultaneously.
        select_for_update() must ensure only one succeeds; the second will
        get an InvalidTransitionError since the account is already HELD.
        """
        account = EscrowService.create_account(
            order_ref=order_ref, buyer_ref=buyer_ref, vendor_ref=vendor_ref
        )

        results = []
        errors = []

        def hold(amount_str: str, ref: str) -> None:
            try:
                EscrowService.hold_funds(
                    account_id=account.id,
                    amount=Decimal(amount_str),
                    payment_provider="MTN",
                    collection_ref=ref,
                )
                results.append("success")
            except (InvalidTransitionError, Exception) as exc:
                errors.append(str(exc))

        t1 = threading.Thread(target=hold, args=("500.00", "REF-T1"))
        t2 = threading.Thread(target=hold, args=("700.00", "REF-T2"))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Exactly one should succeed
        assert len(results) == 1
        assert len(errors) == 1

        account.refresh_from_db()
        # Balance should match only the successful hold
        assert account.balance in (Decimal("500.00"), Decimal("700.00"))

        # Ledger should have exactly one debit+credit pair
        entries = LedgerEntry.objects.filter(account=account)
        assert entries.count() == 2
