"""
apps/escrow/services.py

EscrowService — the single authoritative point of entry for all
escrow state transitions and fund movements on the Lingi7 platform.

Architecture contract
---------------------
- Views and tasks call EscrowService methods; they never touch
  EscrowAccount or LedgerEntry directly.
- Every fund movement is wrapped in transaction.atomic().
- Every EscrowAccount read-before-write uses select_for_update()
  to prevent concurrent balance corruption.
- Every operation writes a paired DEBIT + CREDIT LedgerEntry.
- The fraud gate MUST run before any RELEASED transition.
- All state transitions are logged to AdminAuditLog (apps/admin_audit/).

Zambian regulatory compliance
------------------------------
- Double-entry ledger satisfies ZRA 7-year financial record retention.
- FraudGateLog on every release satisfies FIC AML audit trail obligations.
- AdminAuditLog integration satisfies BoZ KYC transaction monitoring.
"""
from __future__ import annotations

import logging
import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from django.db import transaction
from django.utils import timezone

from apps.escrow.exceptions import (
    EscrowAlreadyExistsError,
    EscrowError,
    FraudGateError,
    InsufficientBalanceError,
    InvalidTransitionError,
    LedgerImbalanceError,
)
from apps.escrow.models import (
    EscrowAccount,
    EscrowHold,
    FraudGateLog,
    LedgerEntry,
    ReconciliationLog,
)
from apps.escrow.state_machine import EscrowState, EscrowStateMachine

logger = logging.getLogger(__name__)

# Platform default take rate — overridden per-store in Phase 2
DEFAULT_FEE_RATE = Decimal("0.0500")

# Fraud risk score threshold above which the escrow is frozen
FRAUD_FREEZE_THRESHOLD = Decimal("0.65")


class EscrowService:
    """
    Stateless service class for all escrow lifecycle operations.

    All methods are @staticmethod — instantiation is never required.
    This keeps the service easily testable without DI overhead.
    """

    # ------------------------------------------------------------------
    # Account creation
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def create_account(
        *,
        order_ref: uuid.UUID,
        buyer_ref: uuid.UUID,
        vendor_ref: Optional[uuid.UUID] = None,
        currency: str = "ZMW",
        notes: str = "",
    ) -> EscrowAccount:
        """
        Create a new EscrowAccount in PENDING state for an order.

        Args:
            order_ref: UUID of the associated order.
            buyer_ref: UUID of the buyer user.
            vendor_ref: UUID of the vendor user (may be assigned later).
            currency: ISO currency code, defaults to ZMW.
            notes: Optional freeform notes for audit purposes.

        Returns:
            The newly created EscrowAccount instance.

        Raises:
            EscrowAlreadyExistsError: If an account already exists for order_ref.
        """
        if EscrowAccount.objects.filter(order_ref=order_ref).exists():
            raise EscrowAlreadyExistsError(
                f"EscrowAccount already exists for order_ref={order_ref}"
            )

        account = EscrowAccount.objects.create(
            order_ref=order_ref,
            buyer_ref=buyer_ref,
            vendor_ref=vendor_ref,
            state=EscrowState.PENDING,
            balance=Decimal("0.00"),
            currency=currency,
            notes=notes,
        )
        logger.info("EscrowAccount created: id=%s order=%s", account.id, order_ref)
        return account

    create_escrow_account = create_account

    # ------------------------------------------------------------------
    # Fund deposit (PENDING → HELD)
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def hold_funds(
        *,
        account_id: uuid.UUID,
        amount: Decimal,
        payment_provider: str,
        collection_ref: str,
        actor_ref: Optional[uuid.UUID] = None,
    ) -> EscrowAccount:
        """
        Confirm payment received and transition account to HELD state.

        Called by the payment webhook handler (apps/payments/) after a
        successful MTN MoMo or Airtel Money collection webhook.

        Args:
            account_id: PK of the EscrowAccount to update.
            amount: Confirmed payment amount in ZMW (must be > 0).
            payment_provider: 'MTN' or 'AIRTEL'.
            collection_ref: Provider's payment reference / receipt number.
            actor_ref: UUID of the system actor (webhook handler sentinel).

        Returns:
            Updated EscrowAccount in HELD state.

        Raises:
            EscrowAccount.DoesNotExist: If account_id is invalid.
            InvalidTransitionError: If account is not in PENDING state.
            ValueError: If amount is <= 0.
        """
        if amount <= Decimal("0.00"):
            raise ValueError(f"hold_funds: amount must be positive, got {amount}")

        account = EscrowAccount.objects.select_for_update().get(pk=account_id)
        EscrowStateMachine.validate(account.state, EscrowState.HELD)

        operation_ref = uuid.uuid4()

        # Double-entry: DEBIT the escrow account (funds in), CREDIT platform liability
        EscrowService._write_ledger_pair(
            account=account,
            amount=amount,
            debit_description=f"Payment received via {payment_provider} | ref={collection_ref}",
            credit_description=f"Buyer liability offset | ref={collection_ref}",
            operation_ref=operation_ref,
            actor_ref=actor_ref,
            new_balance=account.balance + amount,
        )

        account.balance = account.balance + amount
        account.state = EscrowState.HELD
        account.save(update_fields=["balance", "state", "updated_at"])

        # Upsert the EscrowHold record
        EscrowHold.objects.update_or_create(
            account=account,
            defaults={
                "payment_provider": payment_provider,
                "collection_ref": collection_ref,
                "gross_amount": amount,
            },
        )

        EscrowService._log_audit(
            actor_ref=actor_ref,
            action="ESCROW_HELD",
            object_id=account.id,
            before_state=EscrowState.PENDING,
            after_state=EscrowState.HELD,
            notes=f"amount=ZMW {amount}, provider={payment_provider}, ref={collection_ref}",
        )

        logger.info(
            "Funds held: account=%s amount=ZMW %s provider=%s",
            account.id, amount, payment_provider,
        )
        return account

    # ------------------------------------------------------------------
    # Transit (HELD → IN_TRANSIT)
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def mark_in_transit(
        *,
        account_id: uuid.UUID,
        actor_ref: Optional[uuid.UUID] = None,
        notes: str = "",
    ) -> EscrowAccount:
        """
        Transition account to IN_TRANSIT once the vendor has shipped the order.

        Args:
            account_id: PK of the EscrowAccount.
            actor_ref: UUID of the vendor or system actor.
            notes: Optional tracking/shipment reference for the audit log.

        Returns:
            Updated EscrowAccount in IN_TRANSIT state.
        """
        account = EscrowAccount.objects.select_for_update().get(pk=account_id)
        EscrowStateMachine.validate(account.state, EscrowState.IN_TRANSIT)

        before_state = account.state
        account.state = EscrowState.IN_TRANSIT
        account.save(update_fields=["state", "updated_at"])

        EscrowService._log_audit(
            actor_ref=actor_ref,
            action="ESCROW_IN_TRANSIT",
            object_id=account.id,
            before_state=before_state,
            after_state=EscrowState.IN_TRANSIT,
            notes=notes,
        )
        return account

    # ------------------------------------------------------------------
    # Delivery confirmation (IN_TRANSIT / HELD → DELIVERED)
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def mark_delivered(
        *,
        account_id: uuid.UUID,
        actor_ref: Optional[uuid.UUID] = None,
        notes: str = "",
    ) -> EscrowAccount:
        """
        Mark the order as delivered.

        Can be triggered by:
        - Buyer confirming receipt via the frontend.
        - Logistics DELIVERED tracking event (apps/logistics/).
        - Celery auto-confirm task after 7-day timeout.

        Args:
            account_id: PK of the EscrowAccount.
            actor_ref: UUID of the actor (buyer, system, or logistics webhook).
            notes: Source of the delivery confirmation for audit trail.

        Returns:
            Updated EscrowAccount in DELIVERED state.
        """
        account = EscrowAccount.objects.select_for_update().get(pk=account_id)
        EscrowStateMachine.validate(account.state, EscrowState.DELIVERED)

        before_state = account.state
        account.state = EscrowState.DELIVERED
        account.save(update_fields=["state", "updated_at"])

        EscrowService._log_audit(
            actor_ref=actor_ref,
            action="ESCROW_DELIVERED",
            object_id=account.id,
            before_state=before_state,
            after_state=EscrowState.DELIVERED,
            notes=notes,
        )
        return account

    # ------------------------------------------------------------------
    # Release (DELIVERED → RELEASED) — fraud gate mandatory
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def release_funds(
        *,
        account_id: uuid.UUID,
        fee_rate: Decimal = DEFAULT_FEE_RATE,
        actor_ref: Optional[uuid.UUID] = None,
        fraud_rule_flags: Optional[list] = None,
        ml_risk_score: Optional[Decimal] = None,
    ) -> EscrowAccount:
        """
        Release held funds to the vendor after passing the fraud gate.

        This is the most critical path in the entire platform. The
        sequence is:
        1. select_for_update() on the EscrowAccount.
        2. Validate the state transition (DELIVERED → RELEASED).
        3. Run fraud gate — freeze and raise if flagged.
        4. Compute platform fee and net vendor payout.
        5. Write three double-entry ledger entries.
        6. Update account balance and state atomically.
        7. Log to FraudGateLog and AdminAuditLog.

        Args:
            account_id: PK of the EscrowAccount.
            fee_rate: Platform fee rate (default 5%). Per-store rate in Phase 2.
            actor_ref: UUID of the admin or system actor triggering release.
            fraud_rule_flags: List of Layer 1 rule flags from the fraud engine.
            ml_risk_score: XGBoost risk score (0.0 – 1.0) from the ML scorer.

        Returns:
            Updated EscrowAccount in RELEASED state.

        Raises:
            FraudGateError: If fraud gate triggers a FREEZE. Account will be
                            in FROZEN state when this exception is raised.
            InvalidTransitionError: If account is not in DELIVERED state.
            InsufficientBalanceError: If balance is zero or negative.
            LedgerImbalanceError: If the double-entry integrity check fails.
        """
        fraud_rule_flags = fraud_rule_flags or []

        account = EscrowAccount.objects.select_for_update().get(pk=account_id)
        EscrowStateMachine.validate(account.state, EscrowState.RELEASED)

        if account.balance <= Decimal("0.00"):
            raise InsufficientBalanceError(
                f"Cannot release: account {account_id} has zero or negative balance."
            )

        # --- Fraud gate ---
        should_freeze = EscrowService._evaluate_fraud_gate(
            rule_flags=fraud_rule_flags,
            ml_risk_score=ml_risk_score,
        )

        gate_verdict = "FREEZE" if should_freeze else "CLEAR"
        freeze_reason = ""
        if should_freeze:
            if ml_risk_score is not None and ml_risk_score >= FRAUD_FREEZE_THRESHOLD:
                freeze_reason = f"ML risk score {ml_risk_score} >= threshold {FRAUD_FREEZE_THRESHOLD}"
            elif fraud_rule_flags:
                freeze_reason = f"Rule flags: {', '.join(fraud_rule_flags)}"

        FraudGateLog.objects.create(
            account=account,
            rule_flags=fraud_rule_flags,
            ml_risk_score=ml_risk_score,
            verdict=gate_verdict,
            freeze_reason=freeze_reason,
        )

        if should_freeze:
            account.state = EscrowState.FROZEN
            account.frozen_at = timezone.now()
            account.save(update_fields=["state", "frozen_at", "updated_at"])
            EscrowService._log_audit(
                actor_ref=actor_ref,
                action="ESCROW_FROZEN",
                object_id=account.id,
                before_state=EscrowState.DELIVERED,
                after_state=EscrowState.FROZEN,
                notes=freeze_reason,
            )
            raise FraudGateError(
                f"Escrow {account_id} frozen by fraud gate. Reason: {freeze_reason}"
            )

        # --- Fee calculation ---
        gross_amount = account.balance
        fee_amount = (gross_amount * fee_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        net_amount = gross_amount - fee_amount

        operation_ref = uuid.uuid4()

        # --- Three ledger entries for a release ---
        # 1. DEBIT escrow account for gross (funds out)
        # 2. CREDIT platform fee account
        # 3. CREDIT vendor payout account
        entries_to_create = [
            LedgerEntry(
                account=account,
                entry_type=LedgerEntry.EntryType.DEBIT,
                amount=gross_amount,
                description="Escrow release — gross disbursement",
                operation_ref=operation_ref,
                balance_after=Decimal("0.00"),
                created_by_ref=actor_ref,
            ),
            LedgerEntry(
                account=account,
                entry_type=LedgerEntry.EntryType.CREDIT,
                amount=fee_amount,
                description=f"Platform fee @ {fee_rate * 100:.2f}%",
                operation_ref=operation_ref,
                balance_after=Decimal("0.00"),
                created_by_ref=actor_ref,
            ),
            LedgerEntry(
                account=account,
                entry_type=LedgerEntry.EntryType.CREDIT,
                amount=net_amount,
                description="Vendor net payout",
                operation_ref=operation_ref,
                balance_after=Decimal("0.00"),
                created_by_ref=actor_ref,
            ),
        ]

        # Integrity check before write
        total_debit = sum(e.amount for e in entries_to_create if e.entry_type == LedgerEntry.EntryType.DEBIT)
        total_credit = sum(e.amount for e in entries_to_create if e.entry_type == LedgerEntry.EntryType.CREDIT)
        if total_debit != total_credit:
            raise LedgerImbalanceError(
                f"Debit total ZMW {total_debit} != Credit total ZMW {total_credit}"
            )

        for entry in entries_to_create:
            entry.save()

        # Update hold record with disbursement amounts
        EscrowHold.objects.filter(account=account).update(
            fee_amount=fee_amount,
            net_amount=net_amount,
        )

        account.balance = Decimal("0.00")
        account.state = EscrowState.RELEASED
        account.released_at = timezone.now()
        account.save(update_fields=["balance", "state", "released_at", "updated_at"])

        EscrowService._log_audit(
            actor_ref=actor_ref,
            action="ESCROW_RELEASED",
            object_id=account.id,
            before_state=EscrowState.DELIVERED,
            after_state=EscrowState.RELEASED,
            notes=(
                f"gross=ZMW {gross_amount}, fee=ZMW {fee_amount} "
                f"({fee_rate * 100:.2f}%), net=ZMW {net_amount}"
            ),
        )
        logger.info(
            "Escrow released: account=%s gross=ZMW %s fee=ZMW %s net=ZMW %s",
            account.id, gross_amount, fee_amount, net_amount,
        )
        return account

    # ------------------------------------------------------------------
    # Dispute (HELD / IN_TRANSIT / DELIVERED → DISPUTED)
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def raise_dispute(
        *,
        account_id: uuid.UUID,
        actor_ref: Optional[uuid.UUID] = None,
        reason: str = "",
    ) -> EscrowAccount:
        """
        Freeze funds pending dispute resolution.

        Funds remain in the EscrowAccount — no disbursement occurs until
        the dispute is resolved via resolve_dispute().

        Args:
            account_id: PK of the EscrowAccount.
            actor_ref: UUID of the buyer raising the dispute.
            reason: Buyer-provided dispute reason for the audit log.

        Returns:
            Updated EscrowAccount in DISPUTED state.
        """
        account = EscrowAccount.objects.select_for_update().get(pk=account_id)
        EscrowStateMachine.validate(account.state, EscrowState.DISPUTED)

        before_state = account.state
        account.state = EscrowState.DISPUTED
        account.save(update_fields=["state", "updated_at"])

        EscrowService._log_audit(
            actor_ref=actor_ref,
            action="ESCROW_DISPUTED",
            object_id=account.id,
            before_state=before_state,
            after_state=EscrowState.DISPUTED,
            notes=reason,
        )
        return account

    # ------------------------------------------------------------------
    # Refund (DISPUTED / HELD → REFUNDED)
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def refund(
        *,
        account_id: uuid.UUID,
        actor_ref: Optional[uuid.UUID] = None,
        reason: str = "",
    ) -> EscrowAccount:
        """
        Refund held funds to the buyer.

        Triggered when:
        - Dispute is resolved in the buyer's favour.
        - Vendor fails to fulfil within the SLA.

        Creates paired reversal ledger entries to maintain double-entry
        integrity, then sets balance to zero.

        Args:
            account_id: PK of the EscrowAccount.
            actor_ref: UUID of the admin resolving the dispute.
            reason: Refund reason for the audit trail.

        Returns:
            Updated EscrowAccount in REFUNDED state.
        """
        account = EscrowAccount.objects.select_for_update().get(pk=account_id)
        EscrowStateMachine.validate(account.state, EscrowState.REFUNDED)

        if account.balance > Decimal("0.00"):
            operation_ref = uuid.uuid4()
            EscrowService._write_ledger_pair(
                account=account,
                amount=account.balance,
                debit_description=f"Refund to buyer — {reason}",
                credit_description=f"Buyer refund reversal — {reason}",
                operation_ref=operation_ref,
                actor_ref=actor_ref,
                new_balance=Decimal("0.00"),
            )

        before_state = account.state
        account.balance = Decimal("0.00")
        account.state = EscrowState.REFUNDED
        account.save(update_fields=["balance", "state", "updated_at"])

        EscrowService._log_audit(
            actor_ref=actor_ref,
            action="ESCROW_REFUNDED",
            object_id=account.id,
            before_state=before_state,
            after_state=EscrowState.REFUNDED,
            notes=reason,
        )
        return account

    # ------------------------------------------------------------------
    # Manual freeze (admin or fraud engine — any non-terminal → FROZEN)
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def freeze(
        *,
        account_id: uuid.UUID,
        actor_ref: Optional[uuid.UUID] = None,
        reason: str = "",
    ) -> EscrowAccount:
        """
        Freeze the escrow account for manual review.

        Can be called directly by the fraud engine or by an admin.

        Args:
            account_id: PK of the EscrowAccount.
            actor_ref: UUID of the actor triggering the freeze.
            reason: Reason for freezing (rule flag, ML score, etc.).

        Returns:
            Updated EscrowAccount in FROZEN state.
        """
        account = EscrowAccount.objects.select_for_update().get(pk=account_id)
        EscrowStateMachine.validate(account.state, EscrowState.FROZEN)

        before_state = account.state
        account.state = EscrowState.FROZEN
        account.frozen_at = timezone.now()
        account.save(update_fields=["state", "frozen_at", "updated_at"])

        EscrowService._log_audit(
            actor_ref=actor_ref,
            action="ESCROW_FROZEN",
            object_id=account.id,
            before_state=before_state,
            after_state=EscrowState.FROZEN,
            notes=reason,
        )
        return account

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _write_ledger_pair(
        *,
        account: EscrowAccount,
        amount: Decimal,
        debit_description: str,
        credit_description: str,
        operation_ref: uuid.UUID,
        actor_ref: Optional[uuid.UUID],
        new_balance: Decimal,
    ) -> tuple[LedgerEntry, LedgerEntry]:
        """
        Write a paired DEBIT + CREDIT LedgerEntry for a fund movement.

        The two entries share the same operation_ref so they can be
        grouped for reconciliation and audit.

        Returns:
            Tuple of (debit_entry, credit_entry).

        Raises:
            LedgerImbalanceError: If the amounts don't match (sanity check).
        """
        debit = LedgerEntry(
            account=account,
            entry_type=LedgerEntry.EntryType.DEBIT,
            amount=amount,
            description=debit_description,
            operation_ref=operation_ref,
            balance_after=new_balance,
            created_by_ref=actor_ref,
        )
        credit = LedgerEntry(
            account=account,
            entry_type=LedgerEntry.EntryType.CREDIT,
            amount=amount,
            description=credit_description,
            operation_ref=operation_ref,
            balance_after=new_balance,
            created_by_ref=actor_ref,
        )
        if debit.amount != credit.amount:
            raise LedgerImbalanceError(
                f"Paired entries have mismatched amounts: {debit.amount} vs {credit.amount}"
            )
        debit.save()
        credit.save()
        return debit, credit

    @staticmethod
    def _evaluate_fraud_gate(
        *,
        rule_flags: list,
        ml_risk_score: Optional[Decimal],
    ) -> bool:
        """
        Determine whether the fraud gate should freeze the transaction.

        A freeze is triggered if:
        - Any Layer 1 rule flags are present, OR
        - The ML risk score meets or exceeds FRAUD_FREEZE_THRESHOLD.

        In Phase 1, the ML score may be None (model not yet deployed).
        Layer 1 flags alone are sufficient to trigger a freeze.

        Args:
            rule_flags: List of triggered rule identifiers from FraudRuleEngine.
            ml_risk_score: Decimal risk score from MLScorer, or None.

        Returns:
            True if the transaction should be frozen, False if clear.
        """
        if rule_flags:
            return True
        if ml_risk_score is not None and ml_risk_score >= FRAUD_FREEZE_THRESHOLD:
            return True
        return False

    @staticmethod
    def _log_audit(
        *,
        actor_ref: Optional[uuid.UUID],
        action: str,
        object_id: uuid.UUID,
        before_state: str,
        after_state: str,
        notes: str = "",
    ) -> None:
        """
        Write an immutable audit entry via AdminAuditLog (apps/admin_audit/).

        This is a best-effort call — failures are logged but do NOT
        propagate to callers, because the escrow operation itself has
        already succeeded by this point.

        Args:
            actor_ref: UUID of the actor; None for system-initiated events.
            action: Event label for the audit log.
            object_id: UUID of the EscrowAccount.
            before_state: State before the transition.
            after_state: State after the transition.
            notes: Additional context string.
        """
        try:
            from apps.admin_audit.models import AdminAuditLog  # avoid circular at module level

            AdminAuditLog.objects.create(
                actor_id=actor_ref,
                action=action,
                object_id=str(object_id),
                content_type_label="escrow.escrowaccount",
                before_state={"state": before_state},
                after_state={"state": after_state},
                notes=notes,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to write AdminAuditLog for escrow action=%s object=%s: %s",
                action,
                object_id,
                exc,
            )
