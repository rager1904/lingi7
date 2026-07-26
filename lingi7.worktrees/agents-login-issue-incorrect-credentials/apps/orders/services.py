"""
apps/orders/services.py

OrderService — sole entry point for all order domain mutations.
Views and tasks are thin; all business logic lives here.

Integration contracts:
  - EscrowService.hold_funds(escrow_account_id, payment_attempt) [Step 4]
  - EscrowService.release_funds(escrow_account_id, actor) [Step 4]
  - EscrowService.refund(escrow_account_id, amount, actor) [Step 4]
  - PaymentAttempt linked via escrow_account (Step 5)
"""
from __future__ import annotations

import logging
import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from apps.orders.constants import (
    DisputeReason,
    DisputeResolution,
    FulfilmentType,
    OrderStatus,
)
from apps.orders.models import (
    InvalidOrderTransitionError,
    Order,
    OrderDispute,
    OrderEvent,
    OrderLine,
    OrderServiceError,
    OrderShipment,
)
from apps.escrow.services import EscrowService

if TYPE_CHECKING:
    from apps.users.models import User

logger = logging.getLogger(__name__)

# ─────────────────────────────── Fee Calculator ───────────────────────────────

class FeeCalculator:
    """
    Platform fee schedule (tiered, ZMW).

    Tier        | Rate
    ------------|------
    0–500 ZMW   | 3.5%
    501–5000 ZMW| 2.5%
    5001+ ZMW   | 1.5%
    """

    TIERS = [
        (Decimal("500.00"),  Decimal("0.035")),
        (Decimal("5000.00"), Decimal("0.025")),
        (None,               Decimal("0.015")),
    ]

    @classmethod
    def calculate(cls, subtotal: Decimal) -> Decimal:
        for threshold, rate in cls.TIERS:
            if threshold is None or subtotal <= threshold:
                return (subtotal * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return (subtotal * cls.TIERS[-1][1]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ─────────────────────────────── OrderService ────────────────────────────────

class OrderService:
    """
    Fat-service entry point for all order lifecycle operations.

    All methods are @staticmethod — stateless, side-effect-free except
    for the DB mutations they explicitly perform.
    """

    # ─────────────── Draft Creation ──────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def create_order(
        *,
        buyer: "User",
        seller: "User",
        lines: list[dict],
        fulfilment_type: str = FulfilmentType.STANDARD_DELIVERY,
        delivery_address: str = "",
        buyer_notes: str = "",
    ) -> Order:
        """
        Create a DRAFT order with one or more line items.

        Args:
            buyer: authenticated buyer User instance
            seller: seller User instance
            lines: list of dicts with keys:
                   product_name (str), unit_price (Decimal), quantity (int),
                   product_id (str, optional), product_sku (str, optional)
            fulfilment_type: FulfilmentType constant
            delivery_address: free-text delivery address
            buyer_notes: optional note to seller
        """
        if buyer == seller:
            raise OrderServiceError("Buyer and seller cannot be the same user.")
        if not lines:
            raise OrderServiceError("An order must have at least one line item.")

        order = Order(
            buyer=buyer,
            seller=seller,
            fulfilment_type=fulfilment_type,
            delivery_address=delivery_address,
            buyer_notes=buyer_notes,
            status=OrderStatus.DRAFT,
        )

        # Create lines first (unsaved) to calculate totals
        line_objs = []
        for item in lines:
            qty = int(item.get("quantity", 1))
            price = Decimal(str(item["unit_price"]))
            if qty < 1:
                raise OrderServiceError("Line quantity must be >= 1.")
            if price <= 0:
                raise OrderServiceError("Line unit_price must be positive.")
            line_objs.append(OrderLine(
                order=order,
                product_name=item["product_name"],
                product_id=item.get("product_id", ""),
                product_sku=item.get("product_sku", ""),
                unit_price=price,
                quantity=qty,
            ))

        subtotal = sum(l.unit_price * l.quantity for l in line_objs)
        fee = FeeCalculator.calculate(subtotal)
        order.subtotal     = subtotal
        order.platform_fee = fee
        order.total_amount = subtotal + fee
        order.save()

        for line in line_objs:
            line.order = order
        OrderLine.objects.bulk_create(line_objs)

        logger.info("Order %s created (DRAFT) for buyer %s", order.reference, buyer.id)
        return order

    # ─────────────── Submit for Payment ──────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def submit_order(*, order: Order, actor: "User") -> Order:
        """
        Transition DRAFT → PENDING_PAYMENT.

        Creates an EscrowAccount for the order.
        The payment flow (Step 5) then calls EscrowService.hold_funds.
        """
        order.assert_transition(OrderStatus.PENDING_PAYMENT)

        from apps.escrow.models import EscrowAccount
        # Create paired escrow account
        escrow_account = EscrowService.create_escrow_account(
            buyer=order.buyer,
            seller=order.seller,
            amount=order.total_amount,
            currency=order.currency,
            metadata={"order_reference": order.reference},
        )

        update_fields = ["status", "submitted_at", "updated_at"]
        order.status = OrderStatus.PENDING_PAYMENT
        order.submitted_at = timezone.now()

        escrow_id = getattr(escrow_account, "id", None)
        if escrow_id is not None:
            try:
                order.escrow_account_id = uuid.UUID(str(escrow_id))
                update_fields.append("escrow_account")
            except ValueError:
                pass

        order.save(update_fields=update_fields)

        OrderEvent.objects.create(
            order=order,
            from_status=OrderStatus.DRAFT,
            to_status=OrderStatus.PENDING_PAYMENT,
            triggered_by=actor,
            note="Order submitted for payment.",
        )

        logger.info("Order %s submitted → PENDING_PAYMENT", order.reference)
        return order

    # ─────────────── Confirm Escrow Hold ─────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def confirm_payment(*, order: Order, payment_attempt, actor: "User") -> Order:
        """
        Transition PENDING_PAYMENT → PAYMENT_RECEIVED.

        Called by Celery payment callback once MoMo / Airtel Money
        escrow hold is confirmed. Receives the PaymentAttempt instance
        from the payments app (Step 5).
        """
        order.assert_transition(OrderStatus.PAYMENT_RECEIVED)

        EscrowService.hold_funds(
            escrow_account_id=order.escrow_account_id,
            payment_attempt=payment_attempt,
        )

        order.status = OrderStatus.PAYMENT_RECEIVED
        order.paid_at = timezone.now()
        order.save(update_fields=["status", "paid_at", "updated_at"])

        OrderEvent.objects.create(
            order=order,
            from_status=OrderStatus.PENDING_PAYMENT,
            to_status=OrderStatus.PAYMENT_RECEIVED,
            triggered_by=actor,
            note=f"Escrow hold confirmed. Payment attempt: {payment_attempt.idempotency_key}",
            metadata={"payment_attempt_id": str(payment_attempt.id)},
        )

        logger.info("Order %s → PAYMENT_RECEIVED (escrow held)", order.reference)
        return order

    # ─────────────── Seller Acknowledgement ──────────────────────────────────

    @staticmethod
    @transaction.atomic
    def acknowledge_order(*, order: Order, actor: "User") -> Order:
        """Transition PAYMENT_RECEIVED → PROCESSING (seller acknowledges)."""
        order.assert_transition(OrderStatus.PROCESSING)

        if actor != order.seller and not actor.is_staff:
            raise OrderServiceError("Only the seller or admin can acknowledge an order.")

        order.status = OrderStatus.PROCESSING
        order.save(update_fields=["status", "updated_at"])

        OrderEvent.objects.create(
            order=order,
            from_status=OrderStatus.PAYMENT_RECEIVED,
            to_status=OrderStatus.PROCESSING,
            triggered_by=actor,
            note="Seller acknowledged order.",
        )
        return order

    # ─────────────── Ship Order ──────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def ship_order(
        *,
        order: Order,
        actor: "User",
        carrier: str,
        tracking_number: str = "",
        tracking_url: str = "",
        estimated_delivery=None,
        notes: str = "",
    ) -> Order:
        """Transition PROCESSING → SHIPPED. Creates OrderShipment record."""
        order.assert_transition(OrderStatus.SHIPPED)

        if actor != order.seller and not actor.is_staff:
            raise OrderServiceError("Only the seller or admin can mark an order as shipped.")
        if not carrier:
            raise OrderServiceError("Carrier name is required to mark as shipped.")

        OrderShipment.objects.create(
            order=order,
            carrier=carrier,
            tracking_number=tracking_number,
            tracking_url=tracking_url,
            estimated_delivery=estimated_delivery,
            notes=notes,
        )

        order.status = OrderStatus.SHIPPED
        order.save(update_fields=["status", "updated_at"])

        OrderEvent.objects.create(
            order=order,
            from_status=OrderStatus.PROCESSING,
            to_status=OrderStatus.SHIPPED,
            triggered_by=actor,
            note=f"Shipped via {carrier}. Tracking: {tracking_number or 'N/A'}",
        )
        return order

    # ─────────────── Confirm Delivery ────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def confirm_delivery(*, order: Order, actor: "User") -> Order:
        """Transition SHIPPED → DELIVERED (buyer confirms receipt)."""
        order.assert_transition(OrderStatus.DELIVERED)

        if actor != order.buyer and not actor.is_staff:
            raise OrderServiceError("Only the buyer or admin can confirm delivery.")

        order.status = OrderStatus.DELIVERED
        order.save(update_fields=["status", "updated_at"])

        OrderEvent.objects.create(
            order=order,
            from_status=OrderStatus.SHIPPED,
            to_status=OrderStatus.DELIVERED,
            triggered_by=actor,
            note="Buyer confirmed delivery.",
        )
        return order

    # ─────────────── Complete Order (Release Escrow) ──────────────────────────

    @staticmethod
    @transaction.atomic
    def complete_order(*, order: Order, actor: "User") -> Order:
        """
        Transition DELIVERED / DISPUTED → COMPLETED.

        Triggers EscrowService.release_funds → seller receives payment.
        """
        order.assert_transition(OrderStatus.COMPLETED)
        from_status = order.status

        EscrowService.release_funds(
            escrow_account_id=order.escrow_account_id,
            actor=actor,
        )

        order.status = OrderStatus.COMPLETED
        order.completed_at = timezone.now()
        order.save(update_fields=["status", "completed_at", "updated_at"])

        OrderEvent.objects.create(
            order=order,
            from_status=from_status,
            to_status=OrderStatus.COMPLETED,
            triggered_by=actor,
            note="Order completed. Escrow released to seller.",
        )

        logger.info("Order %s COMPLETED — escrow released to seller", order.reference)
        return order

    # ─────────────── Cancel Order ────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def cancel_order(*, order: Order, actor: "User", reason: str = "") -> Order:
        """
        Cancel an order from DRAFT or PENDING_PAYMENT states.

        No escrow interaction needed (funds not yet held).
        Admin can cancel up to PROCESSING; this triggers auto-refund path.
        """
        order.assert_transition(OrderStatus.CANCELLED)

        is_admin = actor.is_staff
        if not is_admin and order.status not in OrderStatus.CANCELLABLE_BY_BUYER:
            raise OrderServiceError(
                f"Buyers can only cancel orders in: {OrderStatus.CANCELLABLE_BY_BUYER}. "
                f"Current status: {order.status}"
            )

        from_status = order.status
        order.status = OrderStatus.CANCELLED
        order.cancelled_at = timezone.now()
        order.save(update_fields=["status", "cancelled_at", "updated_at"])

        OrderEvent.objects.create(
            order=order,
            from_status=from_status,
            to_status=OrderStatus.CANCELLED,
            triggered_by=actor,
            note=reason or "Order cancelled.",
        )

        logger.info("Order %s CANCELLED by %s", order.reference, actor.id)
        return order

    # ─────────────── Raise Dispute ───────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def raise_dispute(
        *,
        order: Order,
        raised_by: "User",
        reason: str,
        description: str,
        evidence_urls: list[str] | None = None,
    ) -> OrderDispute:
        """
        Raise a dispute on an order. Transitions order → DISPUTED.

        Valid from: PAYMENT_RECEIVED, PROCESSING, SHIPPED, DELIVERED.
        """
        order.assert_transition(OrderStatus.DISPUTED)

        if raised_by not in (order.buyer, order.seller) and not raised_by.is_staff:
            raise OrderServiceError("Only buyer, seller, or admin can raise a dispute.")

        if reason not in dict(DisputeReason.CHOICES):
            raise OrderServiceError(f"Invalid dispute reason: {reason}")

        from_status = order.status
        order.status = OrderStatus.DISPUTED
        order.save(update_fields=["status", "updated_at"])

        dispute = OrderDispute.objects.create(
            order=order,
            raised_by=raised_by,
            reason=reason,
            description=description,
            evidence_urls=evidence_urls or [],
        )

        OrderEvent.objects.create(
            order=order,
            from_status=from_status,
            to_status=OrderStatus.DISPUTED,
            triggered_by=raised_by,
            note=f"Dispute raised: {reason}",
            metadata={"dispute_id": str(dispute.id)},
        )

        logger.info(
            "Order %s → DISPUTED (raised by %s, reason: %s)",
            order.reference, raised_by.id, reason
        )
        return dispute

    # ─────────────── Resolve Dispute ─────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def resolve_dispute(
        *,
        dispute: OrderDispute,
        resolved_by: "User",
        resolution: str,
        resolution_notes: str = "",
        refund_amount: Decimal | None = None,
    ) -> OrderDispute:
        """
        Admin-only dispute resolution.

        REFUND_BUYER   → EscrowService.refund → order REFUNDED
        RELEASE_SELLER → EscrowService.release_funds → order COMPLETED
        PARTIAL_REFUND → EscrowService.refund(amount) → order COMPLETED
        """
        if not resolved_by.is_staff:
            raise OrderServiceError("Only admin can resolve disputes.")
        if not dispute.is_open:
            raise OrderServiceError("Dispute is already resolved.")
        if resolution not in dict(DisputeResolution.CHOICES):
            raise OrderServiceError(f"Invalid resolution: {resolution}")

        order = dispute.order
        if resolution == DisputeResolution.REFUND_BUYER:
            EscrowService.refund(
                escrow_account_id=order.escrow_account_id,
                amount=order.total_amount,
                actor=resolved_by,
            )
            order.status = OrderStatus.REFUNDED

        elif resolution == DisputeResolution.RELEASE_SELLER:
            EscrowService.release_funds(
                escrow_account_id=order.escrow_account_id,
                actor=resolved_by,
            )
            order.status = OrderStatus.COMPLETED
            order.completed_at = timezone.now()

        elif resolution == DisputeResolution.PARTIAL_REFUND:
            if refund_amount is None or refund_amount <= 0:
                raise OrderServiceError("refund_amount required for PARTIAL_REFUND.")
            EscrowService.refund(
                escrow_account_id=order.escrow_account_id,
                amount=refund_amount,
                actor=resolved_by,
            )
            remaining = order.total_amount - refund_amount
            EscrowService.release_funds(
                escrow_account_id=order.escrow_account_id,
                actor=resolved_by,
            )
            order.status = OrderStatus.COMPLETED
            order.completed_at = timezone.now()

        order.save(update_fields=["status", "completed_at", "updated_at"])

        dispute.resolved_by      = resolved_by
        dispute.resolution       = resolution
        dispute.resolution_notes = resolution_notes
        dispute.refund_amount    = refund_amount
        dispute.resolved_at      = timezone.now()
        dispute.save()

        from_status = OrderStatus.DISPUTED
        OrderEvent.objects.create(
            order=order,
            from_status=from_status,
            to_status=order.status,
            triggered_by=resolved_by,
            note=f"Dispute resolved: {resolution}. {resolution_notes}",
            metadata={"dispute_id": str(dispute.id)},
        )

        logger.info(
            "Dispute %s resolved → %s (order %s)",
            dispute.id, resolution, order.reference
        )
        return dispute
