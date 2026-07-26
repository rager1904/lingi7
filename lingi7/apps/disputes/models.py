"""
Dispute Resolution Models — apps/disputes/models.py

Provides the data layer for the full dispute lifecycle:
Dispute (parent), Evidence (uploaded files/text), DisputeEvent (audit trail).

Design rules:
- Dispute atomically moves EscrowAccount to DISPUTED on creation.
- Evidence is immutable once submitted (no update/delete in service layer).
- DisputeEvent is append-only — mirrors the AdminAuditLog pattern.
- Resolution ALWAYS goes through DisputeService — never direct field writes.
"""

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class Dispute(models.Model):
    """
    A buyer-initiated dispute against an order where funds are in escrow.

    Lifecycle:
        OPEN → UNDER_REVIEW → RESOLVED_BUYER | RESOLVED_VENDOR | RESOLVED_SPLIT

    On creation: EscrowAccount transitions to DISPUTED (atomic).
    On resolution: Escrow is either REFUNDED (buyer wins) or RELEASED (vendor wins).
    """

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open — Awaiting Review"
        UNDER_REVIEW = "UNDER_REVIEW", "Under Review"
        RESOLVED_BUYER = "RESOLVED_BUYER", "Resolved — Buyer Favour"
        RESOLVED_VENDOR = "RESOLVED_VENDOR", "Resolved — Vendor Favour"
        RESOLVED_SPLIT = "RESOLVED_SPLIT", "Resolved — Split Decision"
        WITHDRAWN = "WITHDRAWN", "Withdrawn by Buyer"

    class Reason(models.TextChoices):
        ITEM_NOT_RECEIVED = "ITEM_NOT_RECEIVED", "Item Not Received"
        ITEM_NOT_AS_DESCRIBED = "ITEM_NOT_AS_DESCRIBED", "Item Not as Described"
        ITEM_DAMAGED = "ITEM_DAMAGED", "Item Arrived Damaged"
        WRONG_ITEM = "WRONG_ITEM", "Wrong Item Sent"
        PARTIAL_DELIVERY = "PARTIAL_DELIVERY", "Partial Delivery"
        SELLER_UNRESPONSIVE = "SELLER_UNRESPONSIVE", "Seller Unresponsive"
        OTHER = "OTHER", "Other — See Description"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Relational links
    order = models.OneToOneField(
        "orders.Order",
        on_delete=models.PROTECT,
        related_name="dispute",
    )
    escrow_account = models.OneToOneField(
        "escrow.EscrowAccount",
        on_delete=models.PROTECT,
        related_name="dispute",
    )
    raised_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="disputes_raised",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="disputes_assigned",
        help_text="Support agent assigned to review this dispute.",
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="disputes_resolved",
    )

    # Dispute detail
    reason = models.CharField(max_length=30, choices=Reason.choices)
    description = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
        db_index=True,
    )

    # Resolution
    resolution_notes = models.TextField(blank=True)
    refund_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="ZMW amount refunded to buyer. Null until resolved.",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    # SLA tracking
    sla_deadline = models.DateTimeField(
        help_text="Admin must resolve by this datetime (72h default).",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["assigned_to", "status"]),
        ]

    def __str__(self) -> str:
        return f"Dispute {self.id} — {self.order_id} [{self.status}]"

    @property
    def is_open(self) -> bool:
        """True if the dispute has not yet been resolved or withdrawn."""
        return self.status in (self.Status.OPEN, self.Status.UNDER_REVIEW)

    @property
    def is_sla_breached(self) -> bool:
        """True if the SLA deadline has passed and dispute is still open."""
        return self.is_open and timezone.now() > self.sla_deadline


class Evidence(models.Model):
    """
    Evidence submitted in support of or against a dispute.

    Immutable after creation — no updates or deletes permitted in the service
    layer. Both the buyer (claimant) and vendor (respondent) may submit evidence
    while the dispute is OPEN or UNDER_REVIEW.
    """

    class SubmittedBy(models.TextChoices):
        BUYER = "BUYER", "Buyer"
        VENDOR = "VENDOR", "Vendor"
        ADMIN = "ADMIN", "Admin"

    class EvidenceType(models.TextChoices):
        IMAGE = "IMAGE", "Image"
        VIDEO = "VIDEO", "Video"
        DOCUMENT = "DOCUMENT", "Document (PDF/Word)"
        TEXT = "TEXT", "Written Statement"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    dispute = models.ForeignKey(
        Dispute,
        on_delete=models.PROTECT,
        related_name="evidence",
    )
    submitted_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="dispute_evidence",
    )
    submitted_by_role = models.CharField(max_length=10, choices=SubmittedBy.choices)
    evidence_type = models.CharField(max_length=10, choices=EvidenceType.choices)

    # Content — either file or text, enforced in service layer
    file = models.FileField(
        upload_to="disputes/evidence/%Y/%m/",
        null=True,
        blank=True,
        help_text="Stored in S3/R2. Null for TEXT type.",
    )
    description = models.TextField(
        help_text="Written statement or caption for file evidence.",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"Evidence {self.id} [{self.evidence_type}] — {self.dispute_id}"


class DisputeEvent(models.Model):
    """
    Immutable append-only audit trail for every dispute state change.

    Mirrors the AdminAuditLog pattern. Written by DisputeService only.
    Never updated or deleted.
    """

    dispute = models.ForeignKey(
        Dispute,
        on_delete=models.PROTECT,
        related_name="events",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="dispute_events",
    )
    action = models.CharField(max_length=50)
    before_status = models.CharField(max_length=20, blank=True)
    after_status = models.CharField(max_length=20, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"DisputeEvent {self.action} on {self.dispute_id} by {self.actor_id}"
