"""
apps/escrow/tests/test_reconciliation.py

Tests for the daily_reconciliation Celery task.

Covers:
- Clean pass when all balances match the ledger.
- Discrepancy detection when a balance is manually corrupted.
- ReconciliationLog row written for every run.
- Status field: PASS vs FAIL.
- discrepancy_detected flag.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.escrow.models import EscrowAccount, ReconciliationLog
from apps.escrow.services import EscrowService
from apps.escrow.state_machine import EscrowState
from apps.escrow.tasks import daily_reconciliation

pytestmark = pytest.mark.django_db(transaction=True)


def _run_reconciliation() -> dict:
    """Helper: call reconciliation task directly (bypasses Celery broker)."""
    return daily_reconciliation.apply().get()


class TestReconciliationCleanPass:

    def test_passes_with_no_accounts(self) -> None:
        result = _run_reconciliation()
        assert result["status"] == "PASS"
        assert result["accounts_checked"] == 0
        assert result["discrepancy_count"] == 0

    def test_passes_with_balanced_account(self, held_account) -> None:
        result = _run_reconciliation()
        assert result["status"] == "PASS"
        assert result["discrepancy_count"] == 0

    def test_log_row_written_on_clean_pass(self, held_account) -> None:
        _run_reconciliation()
        log = ReconciliationLog.objects.order_by("-run_at").first()
        assert log is not None
        assert log.status == "PASS"
        assert log.discrepancy_detected is False

    def test_terminal_accounts_excluded(self, delivered_account) -> None:
        """RELEASED accounts should not be checked (balance = 0 by design)."""
        EscrowService.release_funds(account_id=delivered_account.id)
        result = _run_reconciliation()
        # Released account excluded from check
        assert result["accounts_checked"] == 0

    def test_passes_with_multiple_balanced_accounts(self, buyer_ref) -> None:
        for _ in range(3):
            acc = EscrowService.create_account(
                order_ref=uuid.uuid4(), buyer_ref=buyer_ref
            )
            EscrowService.hold_funds(
                account_id=acc.id,
                amount=Decimal("500.00"),
                payment_provider="MTN",
                collection_ref=f"REF-{uuid.uuid4()}",
            )
        result = _run_reconciliation()
        assert result["status"] == "PASS"
        assert result["accounts_checked"] == 3


class TestReconciliationDiscrepancyDetection:

    def test_detects_injected_discrepancy(self, held_account) -> None:
        """
        Manually corrupt the balance field (simulating a rogue DB write).
        Reconciliation must detect and flag this.
        """
        EscrowAccount.objects.filter(pk=held_account.id).update(
            balance=Decimal("9999.00")  # Should be 1000.00
        )
        result = _run_reconciliation()
        assert result["status"] == "FAIL"
        assert result["discrepancy_count"] == 1

    def test_discrepancy_log_contains_account_id(self, held_account) -> None:
        EscrowAccount.objects.filter(pk=held_account.id).update(
            balance=Decimal("9999.00")
        )
        _run_reconciliation()
        log = ReconciliationLog.objects.order_by("-run_at").first()
        assert log.discrepancy_detected is True
        assert len(log.discrepancy_details) == 1
        detail = log.discrepancy_details[0]
        assert str(held_account.id) == detail["account_id"]
        assert detail["expected_balance"] == "1000.00"
        assert detail["actual_balance"] == "9999.00"

    def test_discrepancy_log_status_is_fail(self, held_account) -> None:
        EscrowAccount.objects.filter(pk=held_account.id).update(
            balance=Decimal("0.00")  # Was 1000
        )
        _run_reconciliation()
        log = ReconciliationLog.objects.order_by("-run_at").first()
        assert log.status == "FAIL"

    def test_discrepancy_amount_calculated_correctly(self, held_account) -> None:
        EscrowAccount.objects.filter(pk=held_account.id).update(
            balance=Decimal("1500.00")  # 500 more than expected 1000
        )
        _run_reconciliation()
        log = ReconciliationLog.objects.order_by("-run_at").first()
        assert log.discrepancy_amount == Decimal("500.00")

    def test_sentry_called_on_discrepancy(self, held_account) -> None:
        EscrowAccount.objects.filter(pk=held_account.id).update(
            balance=Decimal("5000.00")
        )
        with patch("sentry_sdk.capture_message") as mock_sentry:
            _run_reconciliation()
            mock_sentry.assert_called_once()
            call_args = mock_sentry.call_args[0][0]
            assert "discrepancy" in call_args.lower()

    def test_multiple_discrepancies_all_logged(self, buyer_ref) -> None:
        accounts = []
        for _ in range(3):
            acc = EscrowService.create_account(
                order_ref=uuid.uuid4(), buyer_ref=buyer_ref
            )
            EscrowService.hold_funds(
                account_id=acc.id,
                amount=Decimal("200.00"),
                payment_provider="MTN",
                collection_ref=f"REF-{uuid.uuid4()}",
            )
            accounts.append(acc)

        # Corrupt all three
        for acc in accounts:
            EscrowAccount.objects.filter(pk=acc.id).update(balance=Decimal("999.00"))

        result = _run_reconciliation()
        assert result["discrepancy_count"] == 3
        log = ReconciliationLog.objects.order_by("-run_at").first()
        assert len(log.discrepancy_details) == 3

    def test_clean_account_not_flagged_alongside_corrupt_one(self, buyer_ref) -> None:
        # Clean account
        clean = EscrowService.create_account(order_ref=uuid.uuid4(), buyer_ref=buyer_ref)
        EscrowService.hold_funds(
            account_id=clean.id, amount=Decimal("300.00"),
            payment_provider="MTN", collection_ref="CLEAN-REF",
        )
        # Corrupt account
        corrupt = EscrowService.create_account(order_ref=uuid.uuid4(), buyer_ref=buyer_ref)
        EscrowService.hold_funds(
            account_id=corrupt.id, amount=Decimal("300.00"),
            payment_provider="MTN", collection_ref="CORRUPT-REF",
        )
        EscrowAccount.objects.filter(pk=corrupt.id).update(balance=Decimal("9999.00"))

        result = _run_reconciliation()
        assert result["discrepancy_count"] == 1
        log = ReconciliationLog.objects.order_by("-run_at").first()
        assert log.discrepancy_details[0]["account_id"] == str(corrupt.id)


class TestReconciliationLedgerTotals:

    def test_ledger_totals_recorded(self, held_account) -> None:
        _run_reconciliation()
        log = ReconciliationLog.objects.order_by("-run_at").first()
        # held_account has ZMW 1000 debit and ZMW 1000 credit
        assert log.ledger_debit_total == Decimal("1000.00")
        assert log.ledger_credit_total == Decimal("1000.00")
        assert log.account_balance_total == Decimal("1000.00")

    def test_accounts_checked_count(self, buyer_ref) -> None:
        for _ in range(4):
            acc = EscrowService.create_account(order_ref=uuid.uuid4(), buyer_ref=buyer_ref)
            EscrowService.hold_funds(
                account_id=acc.id, amount=Decimal("100.00"),
                payment_provider="AIRTEL", collection_ref=f"R-{uuid.uuid4()}",
            )
        result = _run_reconciliation()
        assert result["accounts_checked"] == 4
