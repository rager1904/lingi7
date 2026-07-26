"""
apps/payments/models.py

Payment audit models for Lingi7's mobile money integration.
Captures every API call, webhook receipt, and disbursement for
full financial audit trail and idempotency enforcement.

Doc Ref: LG7-BE-005 v1.0
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class Provider(models.TextChoices):
    """Supported mobile money providers."""

    MTN_MOMO = "MTN_MOMO", "MTN Mobile Money"
    AIRTEL = "AIRTEL", "Airtel Money"


class PaymentAttempt(models.Model):
    """
    Immutable log of every outbound payment API call made by the platform.

    One row per API call. Never updated after creation — corrections use
    new rows. Supports idempotency via idempotency_key uniqueness constraint.

    Linked to an EscrowAccount via escrow_account_id (loose FK to avoid
    circular imports between payments and escrow apps).
    """

    class Direction(models.TextChoices):
        COLLECTION = "COLLECTION", "Collection (buyer pays)"
        DISBURSEMENT = "DISBURSEMENT", "Disbursement (vendor payout)"

    class Status(models.TextChoices):
        INITIATED = "INITIATED", "Initiated — API call sent"
        PENDING = "PENDING", "Pending — awaiting provider confirmation"
        SUCCESS = "SUCCESS", "Success — confirmed by provider"
        FAILED = "FAILED", "Failed — provider rejected"
        TIMEOUT = "TIMEOUT", "Timeout — no response within SLA"
        CANCELLED = "CANCELLED", "Cancelled — voided before completion"

    # Identity
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    idempotency_key = models.CharField(
        max_length=128,
        unique=True,
        db_index=True,
        help_text=(
            "Unique key per payment attempt. Prevents duplicate API calls "
            "on retries. Format: {direction}-{escrow_account_id}-{attempt_number}"
        ),
    )

    # Relationships
    order_id = models.UUIDField(
        db_index=True,
        help_text="FK to orders.Order — stored as UUID to avoid circular app dependency.",
    )
    escrow_account_id = models.UUIDField(
        db_index=True,
        help_text="FK to escrow.EscrowAccount — loose coupling by design.",
    )
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payment_attempts",
        help_text="User who triggered the payment (null for system-initiated).",
    )

    # Payment details
    provider = models.CharField(max_length=20, choices=Provider.choices, db_index=True)
    direction = models.CharField(max_length=20, choices=Direction.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="ZMW")

    # Provider interaction
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.INITIATED,
        db_index=True,
    )
    provider_reference = models.CharField(
        max_length=255,
        blank=True,
        help_text="Provider-assigned transaction reference (e.g. MTN financialTransactionId).",
    )
    provider_response_code = models.CharField(
        max_length=50,
        blank=True,
        help_text="Raw provider response/error code for debugging.",
    )
    provider_response_body = models.JSONField(
        default=dict,
        blank=True,
        help_text="Full provider API response stored for audit and debugging.",
    )

    # Phone numbers
    payer_phone = models.CharField(
        max_length=20,
        blank=True,
        help_text="MSISDN of the payer (collection) or recipient (disbursement).",
    )

    # Retry tracking
    attempt_number = models.PositiveSmallIntegerField(
        default=1,
        help_text="1-indexed retry count. Max 3 per business rules.",
    )

    # Timestamps — immutable
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    confirmed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When provider confirmed final SUCCESS or FAILED status.",
    )

    class Meta:
        db_table = "payments_payment_attempt"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["order_id", "direction"]),
            models.Index(fields=["provider", "status"]),
            models.Index(fields=["provider_reference"]),
        ]
        verbose_name = "Payment Attempt"
        verbose_name_plural = "Payment Attempts"

    def __str__(self) -> str:
        return (
            f"{self.get_provider_display()} {self.get_direction_display()} "
            f"{self.amount} ZMW [{self.status}]"
        )

    @property
    def is_terminal(self) -> bool:
        """True if this attempt has reached a final state (no further transitions)."""
        return self.status in {
            self.Status.SUCCESS,
            self.Status.FAILED,
            self.Status.CANCELLED,
        }


class WebhookEvent(models.Model):
    """
    Idempotent receipt log for all inbound mobile money webhook events.

    Every webhook POST to the platform creates one row here BEFORE any
    business logic runs. The processed flag prevents duplicate processing
    if the provider fires the same event twice.

    NEVER delete rows from this table — it is part of the financial audit trail.
    """

    class Status(models.TextChoices):
        RECEIVED = "RECEIVED", "Received — queued for processing"
        PROCESSED = "PROCESSED", "Processed — escrow updated"
        DUPLICATE = "DUPLICATE", "Duplicate — already processed"
        INVALID = "INVALID", "Invalid — signature or payload validation failed"
        ERROR = "ERROR", "Error — processing raised an exception"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Provider identification
    provider = models.CharField(max_length=20, choices=Provider.choices, db_index=True)
    event_type = models.CharField(
        max_length=100,
        help_text="Provider event type (e.g. 'SUCCESSFUL', 'FAILED').",
    )

    # Deduplication key — provider's own reference for this event
    provider_reference = models.CharField(
        max_length=255,
        db_index=True,
        help_text=(
            "The provider's unique identifier for this event. "
            "Used as idempotency key — duplicate references are rejected."
        ),
    )

    # Raw payload
    headers = models.JSONField(
        default=dict,
        help_text="Sanitised request headers (Authorization stripped).",
    )
    payload = models.JSONField(
        default=dict,
        help_text="Full raw webhook payload as received.",
    )

    # Signature validation
    signature_valid = models.BooleanField(
        default=False,
        help_text="True if X-Callback-Token or equivalent header validated.",
    )

    # Processing state
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.RECEIVED,
        db_index=True,
    )
    processing_error = models.TextField(
        blank=True,
        help_text="Exception message if status=ERROR.",
    )
    payment_attempt = models.ForeignKey(
        PaymentAttempt,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="webhook_events",
        help_text="Resolved after matching provider_reference to a PaymentAttempt.",
    )

    # Timestamps
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "payments_webhook_event"
        ordering = ["-received_at"]
        # Enforce one-processing-per-provider-reference at DB level
        unique_together = [("provider", "provider_reference")]
        indexes = [
            models.Index(fields=["provider", "status"]),
            models.Index(fields=["received_at"]),
        ]
        verbose_name = "Webhook Event"
        verbose_name_plural = "Webhook Events"

    def __str__(self) -> str:
        return (
            f"{self.get_provider_display()} {self.event_type} "
            f"[{self.status}] @ {self.received_at:%Y-%m-%d %H:%M:%S}"
        )

    def mark_processed(self, payment_attempt: PaymentAttempt | None = None) -> None:
        """Mark this event as successfully processed. Idempotent."""
        self.status = self.Status.PROCESSED
        self.processed_at = timezone.now()
        if payment_attempt:
            self.payment_attempt = payment_attempt
        self.save(update_fields=["status", "processed_at", "payment_attempt"])

    def mark_duplicate(self) -> None:
        """Mark this event as a duplicate — already processed by an earlier event."""
        self.status = self.Status.DUPLICATE
        self.processed_at = timezone.now()
        self.save(update_fields=["status", "processed_at"])

    def mark_error(self, error_message: str) -> None:
        """Record processing failure."""
        self.status = self.Status.ERROR
        self.processing_error = error_message
        self.processed_at = timezone.now()
        self.save(update_fields=["status", "processing_error", "processed_at"])


class WebhookDeadLetter(models.Model):
    """
    Stores webhook events that failed processing, for manual retry.

    When PaymentService.process_webhook() raises an exception, the
    view still returns 200 to the provider (preventing retry storms).
    The failed payload is saved here so ops can investigate and reprocess.

    Retention: 30 days — older entries are cleaned by a periodic task.
    """

    class RetryStatus(models.TextChoices):
        PENDING = "PENDING", "Pending retry"
        RETRIED = "RETRIED", "Successfully retried"
        FAILED_PERMANENTLY = "FAILED_PERMANENTLY", "Failed after max retries"
        EXPIRED = "EXPIRED", "Expired — older than retention window"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    webhook_event = models.ForeignKey(
        WebhookEvent,
        on_delete=models.CASCADE,
        related_name="dead_letters",
        help_text="The original webhook event that failed processing.",
    )
    provider = models.CharField(max_length=20, choices=Provider.choices)
    provider_reference = models.CharField(max_length=255, db_index=True)
    payload = models.JSONField(default=dict)
    headers = models.JSONField(default=dict)
    error_message = models.TextField()
    retry_count = models.PositiveIntegerField(default=0)
    max_retries = models.PositiveIntegerField(default=3)
    retry_status = models.CharField(
        max_length=20,
        choices=RetryStatus.choices,
        default=RetryStatus.PENDING,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    next_retry_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_retry_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "payments_webhook_dead_letter"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["retry_status", "next_retry_at"]),
        ]
        verbose_name = "Webhook Dead Letter"
        verbose_name_plural = "Webhook Dead Letters"

    def __str__(self) -> str:
        return (
            f"DeadLetter {self.provider} ref={self.provider_reference} "
            f"[{self.retry_status}] retries={self.retry_count}"
        )
