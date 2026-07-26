"""
apps/escrow/models.py

Database models for the Lingi7 escrow system.

Schema isolation: EscrowAccount and LedgerEntry live in the
'escrow_ledger' PostgreSQL schema, enforced via Meta.db_table.
FraudGateLog and ReconciliationLog share the default schema because
they are operational logs rather than financial records.

Immutability contract
---------------------
LedgerEntry rows are NEVER updated or deleted. Corrections are made
via reversal entries (equal and opposite debit/credit pairs).
The ORM-level guards in LedgerEntry.save() and .delete() enforce this.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import connection, models
from django.utils import timezone

from apps.escrow.state_machine import EscrowState


class EscrowAccount(models.Model):
    """
    One EscrowAccount per Order. Tracks the current state and the
    running balance of held funds in ZMW.

    The balance field is a denormalised aggregate — it is updated
    atomically alongside every LedgerEntry pair. The reconciliation
    task verifies it matches the ledger sum nightly.
    """

    class Meta:
        db_table = "escrow_account" if connection.vendor == "sqlite" else '"escrow_ledger"."escrow_account"'
        indexes = [
            models.Index(fields=["state"], name="idx_escrow_account_state"),
            models.Index(fields=["order_ref"], name="idx_escrow_account_order_ref"),
        ]

    STATE_CHOICES = [(s, s) for s in EscrowState.ALL]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Loose FK to orders — avoids circular app dependency in Phase 1.
    # Enforced by application logic; the FK is replaced with a real
    # ForeignKey once apps/orders/ is built (Step 7).
    order_ref = models.UUIDField(unique=True, db_index=True)

    # Owning user references (denormalised for audit speed)
    buyer_ref = models.UUIDField(db_index=True)
    vendor_ref = models.UUIDField(null=True, blank=True, db_index=True)

    state = models.CharField(
        max_length=20,
        choices=STATE_CHOICES,
        default=EscrowState.PENDING,
        db_index=True,
    )

    # Balance in ZMW — always >= 0; updated only via EscrowService
    balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    # Optimistic concurrency control — incremented on every balance/state mutation
    version = models.PositiveIntegerField(default=0)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    released_at = models.DateTimeField(null=True, blank=True)
    frozen_at = models.DateTimeField(null=True, blank=True)

    # Metadata
    currency = models.CharField(max_length=3, default="ZMW")
    notes = models.TextField(blank=True)

    def __str__(self) -> str:
        return f"EscrowAccount({self.id}, order={self.order_ref}, state={self.state})"

    @property
    def is_terminal(self) -> bool:
        """True if no further state transitions are possible."""
        from apps.escrow.state_machine import EscrowStateMachine
        return EscrowStateMachine.is_terminal(self.state)


class LedgerEntry(models.Model):
    """
    Immutable double-entry ledger record.

    Every fund movement creates exactly TWO rows: one DEBIT and one CREDIT
    with equal amounts. The system asserts this invariant after every
    EscrowService operation.

    This model intentionally overrides save() and delete() to prevent
    post-creation mutation. Corrections must use reversal entries.
    """

    class Meta:
        db_table = "ledger_entry" if connection.vendor == "sqlite" else '"escrow_ledger"."ledger_entry"'
        indexes = [
            models.Index(fields=["account", "created_at"], name="idx_ledger_account_ts"),
            models.Index(fields=["entry_type"], name="idx_ledger_entry_type"),
            models.Index(fields=["operation_ref"], name="idx_ledger_op_ref"),
        ]

    class EntryType(models.TextChoices):
        DEBIT = "DEBIT", "Debit"
        CREDIT = "CREDIT", "Credit"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(
        EscrowAccount,
        on_delete=models.PROTECT,
        related_name="ledger_entries",
        db_column="account_id",
    )
    entry_type = models.CharField(max_length=6, choices=EntryType.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    description = models.CharField(max_length=255)

    # Groups the paired debit+credit for a single atomic operation
    operation_ref = models.UUIDField(db_index=True, default=uuid.uuid4)

    # Snapshot of account state after this entry was applied
    balance_after = models.DecimalField(max_digits=14, decimal_places=2)

    created_at = models.DateTimeField(default=timezone.now, editable=False)

    # Actor who triggered this entry (admin UUID or system sentinel)
    created_by_ref = models.UUIDField(null=True, blank=True)

    # Account version at the time of this entry — immutable audit sequence number
    account_version = models.PositiveIntegerField(default=0)

    _is_new = True  # Sentinel used by save() guard

    def save(self, *args, **kwargs) -> None:  # type: ignore[override]
        """Block any update after initial creation (immutability guard)."""
        if not self._is_new and self.pk is not None:
            raise RuntimeError(
                "LedgerEntry records are immutable. Create a reversal entry instead."
            )
        super().save(*args, **kwargs)
        self._is_new = False

    def delete(self, *args, **kwargs):  # type: ignore[override]
        """LedgerEntry rows must never be deleted."""
        raise RuntimeError(
            "LedgerEntry records cannot be deleted. The ledger is append-only."
        )

    def __str__(self) -> str:
        return (
            f"LedgerEntry({self.entry_type} ZMW {self.amount} | "
            f"account={self.account_id} | op={self.operation_ref})"
        )


class EscrowHold(models.Model):
    """
    Links an EscrowAccount to the payment and payout references that
    funded it. One row per escrow lifecycle.

    This is the audit anchor used by reconciliation and by finance
    to cross-reference mobile money provider receipts.
    """

    class Meta:
        db_table = "escrow_hold"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.OneToOneField(
        EscrowAccount, on_delete=models.PROTECT, related_name="hold"
    )

    # Payment provider references
    collection_ref = models.CharField(max_length=120, blank=True)  # MoMo/Airtel receipt
    disbursement_ref = models.CharField(max_length=120, blank=True)  # payout receipt
    payment_provider = models.CharField(max_length=20, blank=True)  # MTN | AIRTEL

    gross_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    fee_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    net_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"EscrowHold(account={self.account_id}, provider={self.payment_provider})"


class FraudGateLog(models.Model):
    """
    Records every fraud gate evaluation that occurred before a
    RELEASED transition was attempted.

    Even when the gate clears (no freeze), a row is written for full
    audit traceability as required by FIC AML obligations.
    """

    class Meta:
        db_table = "fraud_gate_log"
        indexes = [
            models.Index(fields=["account", "created_at"], name="idx_fgl_account_ts"),
        ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(
        EscrowAccount,
        on_delete=models.PROTECT,
        related_name="fraud_gate_logs",
    )

    # Fraud engine verdict
    rule_flags = models.JSONField(default=list)       # Layer 1 triggered rules
    ml_risk_score = models.DecimalField(
        max_digits=5, decimal_places=4, null=True, blank=True
    )
    verdict = models.CharField(max_length=10)         # CLEAR | FREEZE
    freeze_reason = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_by_ref = models.UUIDField(null=True, blank=True)  # admin who reviewed if frozen
    reviewed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"FraudGateLog(account={self.account_id}, verdict={self.verdict})"


class ReconciliationLog(models.Model):
    """
    Written once per nightly reconciliation run.

    The task computes the expected total from LedgerEntry rows and
    compares it against the sum of EscrowAccount.balance. Any
    discrepancy triggers a P0 alert.
    """

    class Meta:
        db_table = "reconciliation_log"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    run_at = models.DateTimeField(auto_now_add=True)

    # Snapshot values at reconciliation time
    total_accounts_checked = models.IntegerField(default=0)
    ledger_debit_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    ledger_credit_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    account_balance_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    discrepancy_amount = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00")
    )
    discrepancy_detected = models.BooleanField(default=False)
    discrepancy_details = models.JSONField(default=list)  # list of {account_id, expected, actual}

    # PASS | FAIL
    status = models.CharField(max_length=10, default="PASS")
    error_message = models.TextField(blank=True)

    def __str__(self) -> str:
        return f"ReconciliationLog({self.run_at.date()}, status={self.status})"
