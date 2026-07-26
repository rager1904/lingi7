"""
Notifications Models — apps/notifications/models.py

Defines the NotificationLog model: one row per notification dispatched,
tracking channel, status, recipient, and retry state.

Document Ref: LG7-BE-012
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class NotificationChannel(models.TextChoices):
    """Supported notification delivery channels."""

    EMAIL = "EMAIL", "Email"
    SMS = "SMS", "SMS"
    PUSH = "PUSH", "Push Notification"


class NotificationStatus(models.TextChoices):
    """Lifecycle states for a notification attempt."""

    PENDING = "PENDING", "Pending"
    SENT = "SENT", "Sent"
    DELIVERED = "DELIVERED", "Delivered"
    FAILED = "FAILED", "Failed"
    RETRYING = "RETRYING", "Retrying"


class NotificationEventType(models.TextChoices):
    """
    All platform events that can trigger a notification.

    Naming convention: <DOMAIN>_<EVENT>
    """

    # Order lifecycle
    ORDER_PLACED = "ORDER_PLACED", "Order Placed"
    ORDER_CONFIRMED = "ORDER_CONFIRMED", "Order Confirmed"
    ORDER_CANCELLED = "ORDER_CANCELLED", "Order Cancelled"

    # Payment
    PAYMENT_SUCCESS = "PAYMENT_SUCCESS", "Payment Successful"
    PAYMENT_FAILED = "PAYMENT_FAILED", "Payment Failed"
    PAYMENT_RECEIPT = "PAYMENT_RECEIPT", "Payment Receipt"

    # Escrow
    ESCROW_HELD = "ESCROW_HELD", "Escrow Held"
    ESCROW_RELEASED = "ESCROW_RELEASED", "Escrow Released — Payout Sent"
    ESCROW_DISPUTED = "ESCROW_DISPUTED", "Escrow Disputed"
    ESCROW_REFUNDED = "ESCROW_REFUNDED", "Escrow Refunded"
    ESCROW_FROZEN = "ESCROW_FROZEN", "Escrow Frozen — Review Required"

    # Shipping
    ORDER_SHIPPED = "ORDER_SHIPPED", "Order Shipped"
    ORDER_DELIVERED = "ORDER_DELIVERED", "Order Delivered"
    ORDER_AUTO_CONFIRMED = "ORDER_AUTO_CONFIRMED", "Order Auto-Confirmed"

    # Dispute
    DISPUTE_OPENED = "DISPUTE_OPENED", "Dispute Opened"
    DISPUTE_RESOLVED = "DISPUTE_RESOLVED", "Dispute Resolved"
    DISPUTE_EVIDENCE_REQUESTED = "DISPUTE_EVIDENCE_REQUESTED", "Evidence Requested"

    # Vendor / Store
    STORE_APPROVED = "STORE_APPROVED", "Store Approved"
    STORE_REJECTED = "STORE_REJECTED", "Store Rejected"
    STORE_SUSPENDED = "STORE_SUSPENDED", "Store Suspended"
    LISTING_APPROVED = "LISTING_APPROVED", "Product Listing Approved"
    LISTING_REJECTED = "LISTING_REJECTED", "Product Listing Rejected"

    # KYC
    KYC_APPROVED = "KYC_APPROVED", "KYC Approved"
    KYC_REJECTED = "KYC_REJECTED", "KYC Rejected"
    KYC_REMINDER = "KYC_REMINDER", "KYC Submission Reminder"

    # Account
    WELCOME = "WELCOME", "Welcome to Lingi7"
    PASSWORD_RESET = "PASSWORD_RESET", "Password Reset"
    LOGIN_OTP = "LOGIN_OTP", "Login OTP"


class NotificationLog(models.Model):
    """
    Immutable log of every notification dispatch attempt.

    One row is created per notification send. On failure, the retry
    Celery task creates a new row rather than mutating the original.

    Fields:
        id:              UUID PK — safe to expose in client-facing APIs.
        recipient:       FK to User — nullable for pre-registration events.
        channel:         EMAIL | SMS | PUSH.
        event_type:      Domain event that triggered this notification.
        recipient_address: Resolved at dispatch time (email or phone).
                          Stored here so changes to user profile do not
                          affect historical records.
        subject:         Email subject line. Empty for SMS/Push.
        body_plain:      Plain-text body. Always populated.
        body_html:       HTML body for email. May be empty for SMS.
        status:          PENDING → SENT → DELIVERED | FAILED.
        provider_ref:    Provider message ID (e.g. AWS SES message-id,
                         Africa's Talking message ID).
        error_message:   Last error string if status is FAILED.
        attempt_count:   Number of send attempts (incremented on retry).
        context_data:    JSON snapshot of template variables at dispatch.
        related_object_id:  Optional PK of the triggering domain object
                            (Order ID, EscrowAccount ID, etc.).
        related_object_type: Content-type label for the above.
        created_at:      Immutable creation timestamp.
        sent_at:         Timestamp of successful provider acceptance.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
        db_index=True,
    )

    channel = models.CharField(
        max_length=10,
        choices=NotificationChannel.choices,
        db_index=True,
    )

    event_type = models.CharField(
        max_length=40,
        choices=NotificationEventType.choices,
        db_index=True,
    )

    recipient_address = models.CharField(
        max_length=320,
        help_text="Resolved email or phone at dispatch time. Immutable after creation.",
    )

    subject = models.CharField(max_length=255, blank=True)
    body_plain = models.TextField()
    body_html = models.TextField(blank=True)

    status = models.CharField(
        max_length=10,
        choices=NotificationStatus.choices,
        default=NotificationStatus.PENDING,
        db_index=True,
    )

    provider_ref = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)
    attempt_count = models.PositiveSmallIntegerField(default=1)

    context_data = models.JSONField(
        default=dict,
        help_text="Snapshot of template context variables at time of dispatch.",
    )

    related_object_id = models.CharField(max_length=255, blank=True, db_index=True)
    related_object_type = models.CharField(max_length=100, blank=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "event_type", "status"]),
            models.Index(fields=["channel", "status", "created_at"]),
            models.Index(fields=["related_object_type", "related_object_id"]),
        ]

    def __str__(self) -> str:
        return (
            f"[{self.channel}] {self.event_type} → {self.recipient_address} "
            f"({self.status})"
        )

    def mark_sent(self, provider_ref: str = "") -> None:
        """Mark this log entry as successfully sent by the provider.

        Args:
            provider_ref: Provider-assigned message identifier.
        """
        self.status = NotificationStatus.SENT
        self.provider_ref = provider_ref
        self.sent_at = timezone.now()
        self.save(update_fields=["status", "provider_ref", "sent_at"])

    def mark_failed(self, error: str) -> None:
        """Mark this log entry as failed.

        Args:
            error: Human-readable error description for debugging.
        """
        self.status = NotificationStatus.FAILED
        self.error_message = error
        self.save(update_fields=["status", "error_message"])
