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
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from apps.orders.access import assert_order_party
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
from apps.products.exceptions import InsufficientStockError
from apps.products.models import Product, Store
from apps.products.services import ProductService
from apps.users.models import KYCStatus

if TYPE_CHECKING:
    from apps.users.models import User

logger = logging.getLogger(__name__)


def _assert_can_transact(user: "User") -> None:
    """Defense-in-depth: BoZ KYC + AML freeze gate."""
    if not user.is_active:
        raise OrderServiceError("Account is inactive.")
    if user.kyc_status != KYCStatus.VERIFIED:
        raise OrderServiceError(
            "Your identity must be verified before you can place orders."
        )
    if user.is_frozen:
        raise OrderServiceError(
            "Your account is frozen. Contact support@lingi7.com for assistance."
        )


def _resolve_order_line(*, seller: "User", item: dict) -> tuple[Product, dict]:
    """Load approved product owned by seller; price from server catalog."""
    try:
        product = (
            Product.objects.select_related("store", "inventory", "category")
            .get(
                pk=int(item["product_id"]),
                store__owner=seller,
                store__status=Store.Status.APPROVED,
                status=Product.Status.APPROVED,
            )
        )
    except (Product.DoesNotExist, ValueError, TypeError):
        raise OrderServiceError(
            "Product not found, not approved, or not sold by this vendor."
        )

    qty = int(item.get("quantity", 1))
    if qty < 1:
        raise OrderServiceError("Line quantity must be >= 1.")

    return product, {
        "product_name": product.name,
        "product_id": str(product.pk),
        "product_sku": product.sku,
        "unit_price": product.price,
        "quantity": qty,
    }


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
            lines: list of dicts with product_id (int) and quantity (int) only
            fulfilment_type: FulfilmentType constant
            delivery_address: free-text delivery address
            buyer_notes: optional note to seller
        """
        _assert_can_transact(buyer)
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

        line_objs: list[OrderLine] = []
        products_for_stock: list[tuple[Product, int]] = []
        for item in lines:
            product, line_data = _resolve_order_line(seller=seller, item=item)
            line_objs.append(OrderLine(order=order, **line_data))
            products_for_stock.append((product, line_data["quantity"]))

        subtotal = sum(l.unit_price * l.quantity for l in line_objs)
        fee = FeeCalculator.calculate(subtotal)
        order.subtotal     = subtotal
        order.platform_fee = fee
        order.total_amount = subtotal + fee
        order.save()

        for line in line_objs:
            line.order = order
        OrderLine.objects.bulk_create(line_objs)

        for product, qty in products_for_stock:
            try:
                ProductService.reserve_stock(product, qty)
            except InsufficientStockError as exc:
                raise OrderServiceError(str(exc)) from exc

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
        assert_order_party(order, actor, allow_buyer=True, allow_seller=False)

        escrow_account = EscrowService.create_account(
            order_ref=order.id,
            buyer_ref=order.buyer_id,
            vendor_ref=order.seller_id,
            currency=order.currency,
            notes=f"Order {order.reference}",
        )

        order.status = OrderStatus.PENDING_PAYMENT
        order.submitted_at = timezone.now()
        order.escrow_account = escrow_account
        order.save(
            update_fields=["status", "submitted_at", "escrow_account", "updated_at"]
        )

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
        if order.status == OrderStatus.PAYMENT_RECEIVED:
            return order

        order.assert_transition(OrderStatus.PAYMENT_RECEIVED)

        if not order.escrow_account_id:
            raise OrderServiceError("Order has no linked escrow account.")

        provider = getattr(payment_attempt, "provider", "MTN_MOMO")
        provider_label = "AIRTEL" if provider == "AIRTEL" else "MTN"
        collection_ref = (
            payment_attempt.provider_reference
            or payment_attempt.idempotency_key
        )

        if payment_attempt.amount != order.total_amount:
            raise OrderServiceError(
                "Payment amount does not match order total."
            )

        EscrowService.hold_funds(
            account_id=order.escrow_account_id,
            amount=payment_attempt.amount,
            payment_provider=provider_label,
            collection_ref=collection_ref,
            actor_ref=getattr(actor, "id", None),
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
        assert_order_party(
            order, actor, allow_buyer=False, allow_seller=True, allow_staff=True
        )

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
        assert_order_party(
            order, actor, allow_buyer=False, allow_seller=True, allow_staff=True
        )

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

        if order.escrow_account_id:
            EscrowService.mark_in_transit(
                account_id=order.escrow_account_id,
                actor_ref=getattr(actor, "id", None),
                notes=f"{carrier} {tracking_number}".strip(),
            )

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
        assert_order_party(
            order, actor, allow_buyer=True, allow_seller=False, allow_staff=True
        )

        if actor != order.buyer and not actor.is_staff:
            raise OrderServiceError("Only the buyer or admin can confirm delivery.")

        order.status = OrderStatus.DELIVERED
        order.save(update_fields=["status", "updated_at"])

        if order.escrow_account_id:
            EscrowService.mark_delivered(
                account_id=order.escrow_account_id,
                actor_ref=getattr(actor, "id", None),
                notes="Buyer confirmed delivery.",
            )

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

        if actor not in (order.buyer, order.seller) and not actor.is_staff:
            raise OrderServiceError(
                "Only the buyer, seller, or admin can complete an order."
            )

        if not order.escrow_account_id:
            raise OrderServiceError("Order has no linked escrow account.")

        EscrowService.release_funds(
            account_id=order.escrow_account_id,
            actor_ref=getattr(actor, "id", None),
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
        assert_order_party(order, actor, allow_buyer=True, allow_seller=False)

        is_admin = actor.is_staff
        if not is_admin and actor != order.buyer:
            raise OrderServiceError("Only the buyer or admin can cancel this order.")
        if not is_admin and order.status not in OrderStatus.CANCELLABLE_BY_BUYER:
            raise OrderServiceError(
                f"Buyers can only cancel orders in: {OrderStatus.CANCELLABLE_BY_BUYER}. "
                f"Current status: {order.status}"
            )

        from_status = order.status
        order.status = OrderStatus.CANCELLED
        order.cancelled_at = timezone.now()
        order.save(update_fields=["status", "cancelled_at", "updated_at"])

        for line in order.lines.all():
            if line.product_id:
                try:
                    product = Product.objects.get(pk=int(line.product_id))
                    ProductService.release_stock(product, line.quantity)
                except (Product.DoesNotExist, ValueError):
                    pass

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
        if not order.escrow_account_id:
            raise OrderServiceError("Order has no linked escrow account.")
        account_id = order.escrow_account_id
        actor_ref = getattr(resolved_by, "id", None)

        if resolution == DisputeResolution.REFUND_BUYER:
            EscrowService.refund(
                account_id=account_id,
                actor_ref=actor_ref,
                reason=resolution_notes or "Dispute resolved: refund buyer",
            )
            order.status = OrderStatus.REFUNDED

        elif resolution == DisputeResolution.RELEASE_SELLER:
            EscrowService.release_funds(
                account_id=account_id,
                actor_ref=actor_ref,
            )
            order.status = OrderStatus.COMPLETED
            order.completed_at = timezone.now()

        elif resolution == DisputeResolution.PARTIAL_REFUND:
            if refund_amount is None or refund_amount <= 0:
                raise OrderServiceError("refund_amount required for PARTIAL_REFUND.")
            if refund_amount >= order.escrow_account.balance:
                raise OrderServiceError(
                    "For partial refund, refund_amount must be less than the escrow balance."
                )
            EscrowService.partial_refund(
                account_id=account_id,
                amount=refund_amount,
                actor_ref=actor_ref,
                reason=f"Partial refund ZMW {refund_amount}",
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
