"""
Dispute Service — apps/disputes/services.py

Single entry point for all dispute domain operations. Enforces:
  - Atomic escrow transition on dispute creation (DISPUTED state)
  - Immutable evidence records
  - Resolution always paired with escrow REFUNDED or RELEASED transition
  - Full audit trail via DisputeEvent on every state change

Pattern: fat service, thin views. No business logic in models or views.
"""

import logging
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from django.db import transaction
from django.utils import timezone

from apps.admin_audit.models import AdminAuditLog
from apps.escrow.exceptions import EscrowError
from apps.escrow.models import EscrowAccount
from apps.escrow.state_machine import EscrowState

from .exceptions import (
    DisputeAlreadyExistsError,
    DisputeError,
    DisputeNotOpenError,
    EvidenceSubmissionClosedError,
    InvalidDisputeTransitionError,
)
from .models import Dispute, DisputeEvent, Evidence

logger = logging.getLogger(__name__)

# SLA window — admin must resolve within this period
DISPUTE_SLA_HOURS = 72


class DisputeService:
    """
    Orchestrates the full dispute lifecycle.

    All public methods are static and wrapped in transaction.atomic() where
    they touch financial state (escrow). Evidence submission does not require
    a transaction guard as it is non-financial.
    """

    # ------------------------------------------------------------------
    # Dispute Creation
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def raise_dispute(
        *,
        order,
        raised_by,
        reason: str,
        description: str,
    ) -> Dispute:
        """
        Open a dispute for an order in DELIVERED state.

        Atomically transitions the linked EscrowAccount from DELIVERED → DISPUTED,
        preventing auto-confirm from triggering a release during review.

        Args:
            order: The Order instance being disputed. Must be in DELIVERED state.
            raised_by: The User raising the dispute (must be the order buyer).
            reason: One of Dispute.Reason choices.
            description: Buyer's written explanation of the dispute.

        Returns:
            The newly created Dispute instance.

        Raises:
            DisputeError: If the order is not disputable.
            DisputeAlreadyExistsError: If a dispute already exists for this order.
            EscrowError: If the escrow transition fails.
        """
        from apps.escrow.services import EscrowService
        from apps.orders.models import Order

        # Guard: must be the buyer
        if order.buyer_id != raised_by.pk:
            raise DisputeError("Only the order buyer may raise a dispute.")

        # Guard: order must be in DELIVERED state (auto-confirm not yet triggered)
        if order.status != Order.Status.DELIVERED:
            raise DisputeError(
                f"Cannot dispute an order in '{order.status}' state. "
                "Order must be in DELIVERED state."
            )

        # Guard: no duplicate dispute
        if hasattr(order, "dispute"):
            raise DisputeAlreadyExistsError(
                f"A dispute already exists for order {order.pk}."
            )

        # Acquire lock on escrow account before transition
        escrow_account = (
            EscrowAccount.objects.select_for_update()
            .select_related("order")
            .get(order=order)
        )

        if escrow_account.state != EscrowState.DELIVERED:
            raise EscrowError(
                f"EscrowAccount is in '{escrow_account.state}' state — "
                "expected DELIVERED to raise dispute."
            )

        # Transition escrow → DISPUTED (atomic, inside outer transaction)
        EscrowService.raise_dispute(
            account_id=escrow_account.pk,
            actor_ref=raised_by.pk,
            reason=f"Buyer dispute raised: {reason}",
        )

        # Transition order → DISPUTED
        from apps.orders.models import Order as OrderModel
        order.status = OrderModel.Status.DISPUTED
        order.save(update_fields=["status", "updated_at"])

        sla_deadline = timezone.now() + timedelta(hours=DISPUTE_SLA_HOURS)

        dispute = Dispute.objects.create(
            order=order,
            escrow_account=escrow_account,
            raised_by=raised_by,
            reason=reason,
            description=description,
            status=Dispute.Status.OPEN,
            sla_deadline=sla_deadline,
        )

        DisputeEvent.objects.create(
            dispute=dispute,
            actor=raised_by,
            action="DISPUTE_RAISED",
            before_status="",
            after_status=Dispute.Status.OPEN,
            notes=f"Reason: {reason}. SLA deadline: {sla_deadline.isoformat()}",
        )

        AdminAuditLog.objects.create(
            actor=raised_by,
            action_type="DISPUTE_RAISED",
            target_content_type="disputes.dispute",
            target_object_id=str(dispute.pk),
            target_repr=f"Dispute({dispute.pk})",
            before_state=None,
            after_state={"status": Dispute.Status.OPEN},
        )

        logger.info(
            "Dispute raised: dispute=%s order=%s raised_by=%s reason=%s",
            dispute.pk,
            order.pk,
            raised_by.pk,
            reason,
        )

        return dispute

    # ------------------------------------------------------------------
    # Admin Assignment
    # ------------------------------------------------------------------

    @staticmethod
    def assign_dispute(
        *,
        dispute: Dispute,
        assigned_to,
        assigned_by,
    ) -> Dispute:
        """
        Assign an OPEN dispute to a support agent and move it to UNDER_REVIEW.

        Args:
            dispute: The Dispute to assign.
            assigned_to: The staff User taking ownership.
            assigned_by: The admin User performing the assignment.

        Returns:
            Updated Dispute instance.

        Raises:
            InvalidDisputeTransitionError: If dispute is not in OPEN state.
        """
        if dispute.status != Dispute.Status.OPEN:
            raise InvalidDisputeTransitionError(
                f"Cannot assign dispute in '{dispute.status}' state. Must be OPEN."
            )

        before_status = dispute.status
        dispute.status = Dispute.Status.UNDER_REVIEW
        dispute.assigned_to = assigned_to
        dispute.save(update_fields=["status", "assigned_to", "updated_at"])

        DisputeEvent.objects.create(
            dispute=dispute,
            actor=assigned_by,
            action="DISPUTE_ASSIGNED",
            before_status=before_status,
            after_status=dispute.status,
            notes=f"Assigned to {assigned_to.get_full_name() or assigned_to.email}",
        )

        return dispute

    # ------------------------------------------------------------------
    # Evidence Submission
    # ------------------------------------------------------------------

    @staticmethod
    def submit_evidence(
        *,
        dispute: Dispute,
        submitted_by,
        submitted_by_role: str,
        evidence_type: str,
        description: str,
        file=None,
    ) -> Evidence:
        """
        Submit evidence for an open dispute.

        Both buyer and vendor may submit. Evidence is immutable after creation.

        Args:
            dispute: The Dispute receiving the evidence.
            submitted_by: The User submitting.
            submitted_by_role: One of Evidence.SubmittedBy choices.
            evidence_type: One of Evidence.EvidenceType choices.
            description: Written statement or file caption.
            file: Optional uploaded file object (for non-TEXT types).

        Returns:
            The created Evidence instance.

        Raises:
            EvidenceSubmissionClosedError: If dispute is no longer open.
            DisputeError: If evidence_type requires a file but none provided.
        """
        if not dispute.is_open:
            raise EvidenceSubmissionClosedError(
                f"Evidence cannot be submitted for a dispute in '{dispute.status}' state."
            )

        if evidence_type != Evidence.EvidenceType.TEXT and file is None:
            raise DisputeError(
                f"A file is required for evidence type '{evidence_type}'."
            )

        evidence = Evidence.objects.create(
            dispute=dispute,
            submitted_by_user=submitted_by,
            submitted_by_role=submitted_by_role,
            evidence_type=evidence_type,
            description=description,
            file=file,
        )

        DisputeEvent.objects.create(
            dispute=dispute,
            actor=submitted_by,
            action="EVIDENCE_SUBMITTED",
            before_status=dispute.status,
            after_status=dispute.status,
            notes=f"Evidence type: {evidence_type}. Role: {submitted_by_role}.",
        )

        logger.info(
            "Evidence submitted: dispute=%s evidence=%s type=%s by=%s",
            dispute.pk,
            evidence.pk,
            evidence_type,
            submitted_by.pk,
        )

        return evidence

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def resolve_buyer_favour(
        *,
        dispute: Dispute,
        resolved_by,
        resolution_notes: str,
        refund_amount: Optional[Decimal] = None,
    ) -> Dispute:
        """
        Resolve dispute in buyer's favour — triggers full or partial refund.

        Transitions:
            Dispute → RESOLVED_BUYER
            EscrowAccount → REFUNDED

        Args:
            dispute: The Dispute to resolve.
            resolved_by: The admin User performing the resolution.
            resolution_notes: Mandatory written justification.
            refund_amount: ZMW amount to refund. Defaults to full escrow balance.

        Returns:
            Updated Dispute instance.

        Raises:
            DisputeNotOpenError: If dispute is already resolved.
            EscrowError: If escrow transition fails.
        """
        DisputeService._assert_open(dispute)

        from apps.escrow.services import EscrowService

        escrow_account = (
            EscrowAccount.objects.select_for_update().get(pk=dispute.escrow_account_id)
        )

        actual_refund = (
            refund_amount
            if refund_amount is not None
            else escrow_account.balance
        )
        actual_refund = actual_refund.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if actual_refund > escrow_account.balance:
            raise DisputeError(
                f"Refund amount {actual_refund} exceeds escrow balance {escrow_account.balance}."
            )

        # Transition escrow — full or partial refund
        if actual_refund >= escrow_account.balance:
            # Full refund
            EscrowService.refund(
                account_id=escrow_account.pk,
                actor_ref=resolved_by.pk,
                reason=f"Dispute resolved buyer favour: {resolution_notes}",
            )
        else:
            # Partial refund — retains remaining balance for vendor
            EscrowService.partial_refund(
                account_id=escrow_account.pk,
                amount=actual_refund,
                actor_ref=resolved_by.pk,
                reason=f"Dispute resolved buyer favour (partial): {resolution_notes}",
            )

        before_status = dispute.status
        dispute.status = Dispute.Status.RESOLVED_BUYER
        dispute.resolved_by = resolved_by
        dispute.resolved_at = timezone.now()
        dispute.resolution_notes = resolution_notes
        dispute.refund_amount = actual_refund
        dispute.save(
            update_fields=[
                "status",
                "resolved_by",
                "resolved_at",
                "resolution_notes",
                "refund_amount",
                "updated_at",
            ]
        )

        DisputeService._log_resolution(
            dispute=dispute,
            actor=resolved_by,
            before_status=before_status,
            action="DISPUTE_RESOLVED_BUYER",
            notes=f"Refund: ZMW {actual_refund}. {resolution_notes}",
        )

        logger.info(
            "Dispute resolved buyer favour: dispute=%s refund=ZMW%s by=%s",
            dispute.pk,
            actual_refund,
            resolved_by.pk,
        )

        return dispute

    @staticmethod
    @transaction.atomic
    def resolve_vendor_favour(
        *,
        dispute: Dispute,
        resolved_by,
        resolution_notes: str,
    ) -> Dispute:
        """
        Resolve dispute in vendor's favour — releases held funds to vendor.

        Transitions:
            Dispute → RESOLVED_VENDOR
            EscrowAccount → RELEASED (fraud gate still runs)

        Args:
            dispute: The Dispute to resolve.
            resolved_by: The admin User performing the resolution.
            resolution_notes: Mandatory written justification.

        Returns:
            Updated Dispute instance.

        Raises:
            DisputeNotOpenError: If dispute is already resolved.
        """
        DisputeService._assert_open(dispute)

        from apps.escrow.services import EscrowService

        escrow_account = (
            EscrowAccount.objects.select_for_update().get(pk=dispute.escrow_account_id)
        )

        # Fraud gate STILL runs before release — even in vendor-favour disputes
        EscrowService.release_funds(
            account_id=escrow_account.pk,
            actor_ref=resolved_by.pk,
        )

        before_status = dispute.status
        dispute.status = Dispute.Status.RESOLVED_VENDOR
        dispute.resolved_by = resolved_by
        dispute.resolved_at = timezone.now()
        dispute.resolution_notes = resolution_notes
        dispute.refund_amount = Decimal("0.00")
        dispute.save(
            update_fields=[
                "status",
                "resolved_by",
                "resolved_at",
                "resolution_notes",
                "refund_amount",
                "updated_at",
            ]
        )

        DisputeService._log_resolution(
            dispute=dispute,
            actor=resolved_by,
            before_status=before_status,
            action="DISPUTE_RESOLVED_VENDOR",
            notes=resolution_notes,
        )

        logger.info(
            "Dispute resolved vendor favour: dispute=%s by=%s",
            dispute.pk,
            resolved_by.pk,
        )

        return dispute

    @staticmethod
    @transaction.atomic
    def withdraw_dispute(
        *,
        dispute: Dispute,
        withdrawn_by,
        reason: str,
    ) -> Dispute:
        """
        Buyer withdraws their own dispute.

        Releases escrow funds to vendor (fraud gate runs).

        Args:
            dispute: The Dispute to withdraw.
            withdrawn_by: The buyer User withdrawing.
            reason: Written explanation for withdrawal.

        Returns:
            Updated Dispute instance.

        Raises:
            DisputeError: If the withdrawing user is not the dispute raiser.
            DisputeNotOpenError: If dispute is already resolved.
        """
        DisputeService._assert_open(dispute)

        if dispute.raised_by_id != withdrawn_by.pk:
            raise DisputeError("Only the buyer who raised the dispute may withdraw it.")

        from apps.escrow.services import EscrowService

        escrow_account = (
            EscrowAccount.objects.select_for_update().get(pk=dispute.escrow_account_id)
        )

        # Withdrawal = buyer conceding → vendor receives funds
        EscrowService.release_funds(
            account_id=escrow_account.pk,
            actor_ref=withdrawn_by.pk,
        )

        before_status = dispute.status
        dispute.status = Dispute.Status.WITHDRAWN
        dispute.resolved_at = timezone.now()
        dispute.resolution_notes = f"Withdrawn by buyer. Reason: {reason}"
        dispute.refund_amount = Decimal("0.00")
        dispute.save(
            update_fields=[
                "status",
                "resolved_at",
                "resolution_notes",
                "refund_amount",
                "updated_at",
            ]
        )

        DisputeService._log_resolution(
            dispute=dispute,
            actor=withdrawn_by,
            before_status=before_status,
            action="DISPUTE_WITHDRAWN",
            notes=reason,
        )

        return dispute

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _assert_open(dispute: Dispute) -> None:
        """Raise DisputeNotOpenError if dispute is no longer actionable."""
        if not dispute.is_open:
            raise DisputeNotOpenError(
                f"Dispute {dispute.pk} is in '{dispute.status}' state — "
                "cannot perform this action."
            )

    @staticmethod
    def _log_resolution(
        *,
        dispute: Dispute,
        actor,
        before_status: str,
        action: str,
        notes: str,
    ) -> None:
        """Write DisputeEvent and AdminAuditLog for a resolution action."""
        DisputeEvent.objects.create(
            dispute=dispute,
            actor=actor,
            action=action,
            before_status=before_status,
            after_status=dispute.status,
            notes=notes,
        )
        AdminAuditLog.objects.create(
            actor=actor,
            action_type=action,
            target_content_type="disputes.dispute",
            target_object_id=str(dispute.pk),
            target_repr=f"Dispute({dispute.pk})",
            before_state={"status": before_status},
            after_state={"status": dispute.status},
        )
