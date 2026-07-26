"""
apps/orders/models.py

Order lifecycle models for Lingi7 escrow marketplace.

Design principles:
- All monetary values stored as Decimal, ZMW only
- FK relationships to users, escrow accounts, payment attempts
- Immutable order lines — modifications create new orders
- Dispute model is append-only
- Carrier / tracking info captured on OrderShipment
"""
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.orders.constants import (
    DisputeReason,
    DisputeResolution,
    FulfilmentType,
    ORDER_TRANSITIONS,
    OrderStatus,
)


def _order_ref():
    """Generate human-readable order reference: LG7-YYYYMMDD-XXXXX."""
    import random
    import string
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
    return f"LG7-{timezone.now().strftime('%Y%m%d')}-{suffix}"


class Order(models.Model):
    """
    Master order record.

    One order = one escrow account (1:1).
    Multiple OrderLine items allowed.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(
        max_length=24,
        unique=True,
        default=_order_ref,
        db_index=True,
        help_text="Human-readable order reference shown to buyers/sellers.",
    )

    # Parties
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="orders_as_buyer",
    )
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="orders_as_seller",
    )

    # Escrow link (populated on PAYMENT_RECEIVED)
    escrow_account = models.OneToOneField(
        "escrow.EscrowAccount",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="order",
    )

    # Financials
    subtotal    = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    platform_fee = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    currency    = models.CharField(max_length=3, default="ZMW")

    # State machine
    status = models.CharField(
        max_length=20,
        choices=OrderStatus.CHOICES,
        default=OrderStatus.DRAFT,
        db_index=True,
    )

    Status = OrderStatus

    # Fulfilment
    fulfilment_type = models.CharField(
        max_length=20,
        choices=FulfilmentType.CHOICES,
        default=FulfilmentType.STANDARD_DELIVERY,
    )
    delivery_address = models.TextField(blank=True, default="")
    buyer_notes      = models.TextField(blank=True, default="")

    # Timestamps
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)
    submitted_at  = models.DateTimeField(null=True, blank=True)
    paid_at       = models.DateTimeField(null=True, blank=True)
    completed_at  = models.DateTimeField(null=True, blank=True)
    cancelled_at  = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["buyer", "status"]),
            models.Index(fields=["seller", "status"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self):
        return f"Order {self.reference} [{self.status}]"

    # ─────────────────────── State Machine ───────────────────────

    def can_transition_to(self, new_status: str) -> bool:
        allowed = ORDER_TRANSITIONS.get(self.status, set())
        return new_status in allowed

    def assert_transition(self, new_status: str):
        if not self.can_transition_to(new_status):
            raise InvalidOrderTransitionError(
                f"Order {self.reference}: cannot transition from "
                f"{self.status} → {new_status}"
            )

    # ─────────────────────── Computed Properties ─────────────────

    @property
    def is_terminal(self) -> bool:
        return self.status in OrderStatus.TERMINAL

    @property
    def has_active_dispute(self) -> bool:
        return self.disputes.filter(resolved_at__isnull=True).exists()

    def calculate_totals(self):
        """Recalculate subtotal, fee, and total from order lines."""
        from apps.orders.services import FeeCalculator
        self.subtotal = sum(
            line.unit_price * line.quantity for line in self.lines.all()
        )
        self.platform_fee = FeeCalculator.calculate(self.subtotal)
        self.total_amount = self.subtotal + self.platform_fee


class OrderLine(models.Model):
    """
    Immutable line item on an order.

    Snapshot of product price at time of order — never updated.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="lines")

    # Product snapshot — we store strings so changes to catalogue don't corrupt history
    product_id    = models.CharField(max_length=100, blank=True, default="")
    product_name  = models.CharField(max_length=255)
    product_sku   = models.CharField(max_length=100, blank=True, default="")
    unit_price    = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    quantity = models.PositiveIntegerField(default=1)
    currency = models.CharField(max_length=3, default="ZMW")

    class Meta:
        ordering = ["product_name"]

    def __str__(self):
        return f"{self.quantity}x {self.product_name} @ {self.unit_price} {self.currency}"

    @property
    def line_total(self) -> Decimal:
        return self.unit_price * self.quantity


class OrderEvent(models.Model):
    """
    Immutable audit trail of order state transitions.

    Append-only — never updated or deleted.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="events")

    from_status = models.CharField(max_length=20, choices=OrderStatus.CHOICES)
    to_status   = models.CharField(max_length=20, choices=OrderStatus.CHOICES)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="order_events_triggered",
    )
    note        = models.TextField(blank=True, default="")
    created_at  = models.DateTimeField(auto_now_add=True)
    metadata    = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.order.reference}: {self.from_status} → {self.to_status}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ImmutableOrderEventError("OrderEvent records cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableOrderEventError("OrderEvent records cannot be deleted.")


class OrderShipment(models.Model):
    """
    Carrier and tracking information for a shipped order.

    Created when order transitions to SHIPPED.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.OneToOneField(Order, on_delete=models.PROTECT, related_name="shipment")

    carrier          = models.CharField(max_length=100)
    tracking_number  = models.CharField(max_length=200, blank=True, default="")
    tracking_url     = models.URLField(blank=True, default="")
    estimated_delivery = models.DateField(null=True, blank=True)
    shipped_at       = models.DateTimeField(default=timezone.now)
    notes            = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Shipment for {self.order.reference} via {self.carrier}"


class OrderDispute(models.Model):
    """
    Dispute record attached to an order.

    Raising a dispute transitions the order to DISPUTED.
    Resolution by admin drives to COMPLETED or REFUNDED.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="disputes")

    raised_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="order_disputes_raised",
    )
    reason     = models.CharField(max_length=30, choices=DisputeReason.CHOICES)
    description = models.TextField()
    evidence_urls = models.JSONField(default=list, blank=True)

    # Resolution
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="order_disputes_resolved",
    )
    resolution        = models.CharField(
        max_length=20,
        choices=DisputeResolution.CHOICES,
        blank=True,
        default="",
    )
    resolution_notes  = models.TextField(blank=True, default="")
    refund_amount     = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Dispute on {self.order.reference} — {self.reason}"

    @property
    def is_open(self) -> bool:
        return self.resolved_at is None


# ─────────────────────────────── Domain Exceptions ───────────────────────────

class InvalidOrderTransitionError(Exception):
    """Raised when a state transition violates the order state machine."""


class ImmutableOrderEventError(Exception):
    """Raised when someone attempts to mutate an OrderEvent record."""


class OrderServiceError(Exception):
    """General OrderService domain error."""
