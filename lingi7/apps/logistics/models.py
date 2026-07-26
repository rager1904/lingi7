"""
Logistics models for Lingi7.

Covers the full physical supply chain lifecycle from China dispatch
to Zambia last-mile delivery. Tracking events feed directly into the
escrow state machine — a DELIVERED event starts the auto-confirm timer.

Reference: LG7-BE-009 | apps/logistics/
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class Shipment(models.Model):
    """
    Represents a physical shipment tied to one Order.

    Status flows from CREATED through to DELIVERED. Each status
    change produces a TrackingEvent row. The DELIVERED event is the
    trigger that starts the escrow auto-confirm window.

    A single Order maps to one Shipment. One Shipment may have many
    TrackingEvents.
    """

    class Status(models.TextChoices):
        CREATED = "CREATED", "Created — Awaiting Dispatch"
        DISPATCHED = "DISPATCHED", "Dispatched from Origin"
        IN_TRANSIT = "IN_TRANSIT", "In Transit (International)"
        CUSTOMS = "CUSTOMS", "At Zambia Customs (ZRA / ASYCUDA)"
        CLEARED = "CLEARED", "Customs Cleared"
        OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY", "Out for Last-Mile Delivery"
        DELIVERED = "DELIVERED", "Delivered to Buyer"
        FAILED_DELIVERY = "FAILED_DELIVERY", "Delivery Attempt Failed"
        RETURNED = "RETURNED", "Returned to Sender"

    class CarrierCode(models.TextChoices):
        DHL = "DHL", "DHL Zambia"
        FEDEX = "FEDEX", "FedEx"
        ZAMPOST = "ZAMPOST", "Zampost"
        GENERIC = "GENERIC", "Generic / Manual Carrier"
        INTERNAL = "INTERNAL", "Internal Warehouse Transfer"

    class ShippingMethod(models.TextChoices):
        AIR = "AIR", "Air Freight (5-10 days)"
        SEA = "SEA", "Sea Freight (35-45 days)"
        EXPRESS = "EXPRESS", "Express Courier"
        ROAD = "ROAD", "Road Freight (SADC)"

    # Identity
    tracking_token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
        help_text="Public token for unauthenticated tracking page. Never expose the PK.",
    )

    # Relationships
    order = models.OneToOneField(
        "orders.Order",
        on_delete=models.PROTECT,
        related_name="logistics_shipment",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_shipments",
        help_text="Vendor or admin who created this shipment record.",
    )

    # Carrier information
    carrier = models.CharField(
        max_length=20,
        choices=CarrierCode.choices,
        default=CarrierCode.GENERIC,
        db_index=True,
    )
    carrier_tracking_number = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="Carrier-assigned tracking reference (e.g. DHL waybill number).",
    )
    shipping_method = models.CharField(
        max_length=20,
        choices=ShippingMethod.choices,
        default=ShippingMethod.AIR,
    )

    # Status
    status = models.CharField(
        max_length=25,
        choices=Status.choices,
        default=Status.CREATED,
        db_index=True,
    )

    # Origin & Destination
    origin_country = models.CharField(
        max_length=2,
        default="CN",
        help_text="ISO 3166-1 alpha-2 country code (e.g. CN, ZM, ZA).",
    )
    origin_address = models.TextField(blank=True)
    destination_country = models.CharField(max_length=2, default="ZM")
    destination_address = models.TextField(blank=True)

    # Logistics partners
    freight_forwarder = models.CharField(
        max_length=120,
        blank=True,
        help_text="Freight forwarder company name handling international leg.",
    )
    customs_agent = models.CharField(
        max_length=120,
        blank=True,
        help_text="ZRA-licensed clearing agent handling ASYCUDA submission.",
    )
    last_mile_courier = models.CharField(
        max_length=120,
        blank=True,
        help_text="Lusaka last-mile courier (e.g. DHL Zambia, Zampost).",
    )

    # Warehouse
    warehouse_received_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when goods arrived at Lusaka bonded warehouse.",
    )
    warehouse_dispatched_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when goods left Lusaka warehouse for last-mile.",
    )

    # Dimensions & customs
    weight_kg = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        null=True,
        blank=True,
    )
    volume_cbm = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Cubic metres — used for freight cost calculation.",
    )
    declared_value_usd = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Declared customs value in USD for ZRA duty calculation.",
    )
    duty_paid_zmw = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Actual import duty paid in ZMW.",
    )

    # Shipping documents (S3 keys)
    commercial_invoice_key = models.CharField(max_length=500, blank=True)
    packing_list_key = models.CharField(max_length=500, blank=True)
    bill_of_lading_key = models.CharField(max_length=500, blank=True)

    # Delivery
    estimated_delivery_date = models.DateField(null=True, blank=True)
    delivered_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Actual delivery timestamp. Set when status moves to DELIVERED.",
    )
    delivery_confirmed_by = models.CharField(
        max_length=20,
        choices=[
            ("BUYER", "Buyer Confirmed"),
            ("CARRIER", "Carrier Confirmed"),
            ("AUTO", "Auto-Confirmed (Timeout)"),
            ("ADMIN", "Admin Confirmed"),
        ],
        blank=True,
    )

    # Carrier API metadata
    last_carrier_poll_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time Celery polled the carrier API for status updates.",
    )
    carrier_api_error = models.TextField(
        blank=True,
        help_text="Last error response from carrier API — for debugging.",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["carrier", "carrier_tracking_number"]),
            models.Index(fields=["tracking_token"]),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Shipment #{self.pk} | Order {self.order_id} | {self.status}"

    @property
    def is_delivered(self) -> bool:
        """True when status is DELIVERED — triggers escrow auto-confirm."""
        return self.status == self.Status.DELIVERED

    @property
    def public_tracking_url(self) -> str:
        """Public URL for unauthenticated tracking — uses token, not PK."""
        return f"/track/{self.tracking_token}/"


class TrackingEvent(models.Model):
    """
    Immutable tracking event log — one row per status update.

    Events are append-only. They are never updated or deleted.
    The most recent event reflects the current shipment status.

    Emitted by:
    - Carrier webhook receivers (push)
    - Celery polling tasks (pull)
    - Manual vendor/admin updates
    """

    class Source(models.TextChoices):
        CARRIER_WEBHOOK = "CARRIER_WEBHOOK", "Carrier Webhook (Push)"
        CARRIER_POLL = "CARRIER_POLL", "Carrier API Poll (Pull)"
        VENDOR_MANUAL = "VENDOR_MANUAL", "Vendor Manual Update"
        ADMIN_MANUAL = "ADMIN_MANUAL", "Admin Manual Update"
        SYSTEM = "SYSTEM", "System (Auto-Confirm / Timeout)"

    shipment = models.ForeignKey(
        Shipment,
        on_delete=models.CASCADE,
        related_name="events",
    )

    # Status snapshot at time of event
    status = models.CharField(
        max_length=25,
        choices=Shipment.Status.choices,
    )

    # Event detail
    location = models.CharField(
        max_length=200,
        blank=True,
        help_text="Physical location description (e.g. 'Kenneth Kaunda Int. Airport, Lusaka').",
    )
    description = models.TextField(
        help_text="Human-readable event description — shown on buyer tracking page.",
    )
    source = models.CharField(
        max_length=25,
        choices=Source.choices,
        default=Source.SYSTEM,
    )

    # Raw payload from carrier (stored for debugging and audit)
    raw_payload = models.JSONField(
        null=True,
        blank=True,
        help_text="Raw JSON response from carrier API or webhook — never displayed publicly.",
    )

    # Carrier-reported timestamp (may differ from created_at if delayed push)
    event_timestamp = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text="Timestamp as reported by carrier. Use this for display, not created_at.",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-event_timestamp"]
        indexes = [
            models.Index(fields=["shipment", "event_timestamp"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return (
            f"TrackingEvent [{self.status}] "
            f"Shipment #{self.shipment_id} @ {self.event_timestamp:%Y-%m-%d %H:%M}"
        )
