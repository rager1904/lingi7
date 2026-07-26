"""
apps/admin_audit/models.py
==========================
Immutable, append-only admin audit log.

Every admin action (create, update, delete) on any model is captured here
via Django signals.  Rows are NEVER updated or deleted — they are the
forensic record of the platform.

Zambian regulatory context
--------------------------
* Data Protection Act 2021 (DPA): audit logs must be retained for a minimum
  of 5 years and must record who accessed or modified personal data.
* BoZ AML/CFT: financial institutions must maintain audit trails for all
  privileged user actions.
* FIC (Financial Intelligence Centre): suspicious activity audit trails
  may be requisitioned — logs must be tamper-evident.

All string columns use explicit max_length rather than TextField to prevent
accidental large-object storage and to document the expected cardinality.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone


class ActionType(models.TextChoices):
    """Discrete set of admin actions that may appear in the audit log."""

    CREATE = "CREATE", "Create"
    UPDATE = "UPDATE", "Update"
    DELETE = "DELETE", "Delete"
    # Extend here for soft-deletes, status transitions, bulk actions, etc.
    SOFT_DELETE = "SOFT_DELETE", "Soft Delete"
    RESTORE = "RESTORE", "Restore"
    # Escrow lifecycle transitions
    ESCROW_HELD = "ESCROW_HELD", "Escrow Held"
    ESCROW_IN_TRANSIT = "ESCROW_IN_TRANSIT", "Escrow In Transit"
    ESCROW_DELIVERED = "ESCROW_DELIVERED", "Escrow Delivered"
    ESCROW_RELEASED = "ESCROW_RELEASED", "Escrow Released"
    ESCROW_FROZEN = "ESCROW_FROZEN", "Escrow Frozen"
    ESCROW_DISPUTED = "ESCROW_DISPUTED", "Escrow Disputed"
    ESCROW_REFUNDED = "ESCROW_REFUNDED", "Escrow Refunded"
    ESCROW_PARTIAL_REFUND = "ESCROW_PARTIAL_REFUND", "Escrow Partial Refund"
    SHIPMENT_CREATED = "SHIPMENT_CREATED", "Shipment Created"
    SHIPMENT_STATUS = "SHIPMENT_STATUS", "Shipment Status Change"
    SHIPMENT_TRACKING_UPDATED = "SHIPMENT_TRACKING_UPDATED", "Shipment Tracking Updated"
    STORE_APPROVED = "STORE_APPROVED", "Store Approved"
    STORE_REJECTED = "STORE_REJECTED", "Store Rejected"
    STORE_SUSPENDED = "STORE_SUSPENDED", "Store Suspended"
    PRODUCT_STATUS = "PRODUCT_STATUS", "Product Status Change"
    DISPUTE_RAISED = "DISPUTE_RAISED", "Dispute Raised"
    DISPUTE_RESOLVED = "DISPUTE_RESOLVED", "Dispute Resolved"
    DISPUTE_WITHDRAWN = "DISPUTE_WITHDRAWN", "Dispute Withdrawn"


class AdminAuditLog(models.Model):
    """Immutable record of a single privileged action taken on any model.

    Design decisions:
    -----------------
    * ``id`` is a UUID so that log rows cannot be enumerated sequentially
      (prevents probing for gaps in the audit trail).
    * ``before_state`` / ``after_state`` store a full serialised snapshot of
      the affected object.  For DELETE, ``after_state`` is null.  For CREATE,
      ``before_state`` is null.
    * ``ip_address`` is GenericIPAddressField — supports both IPv4 and IPv6.
    * No ForeignKey on ``target_object_id`` — the target model may be deleted
      and we must not lose the log row.  We store the PK as a string.
    * ``actor`` is nullable (SET_NULL) so that deleting an admin user does not
      cascade-delete their audit trail.
    * The model has no ``save()`` override guard here — instead the service
      layer (AuditService) is the ONLY write path.  Views and signals must
      call the service, never write directly.

    Indexes:
    --------
    * (actor, timestamp) — "what did this admin do and when?"
    * (target_content_type, target_object_id) — "full history of this object"
    * (action_type, timestamp) — "all deletes in the last 24 h"
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    # Who performed the action ------------------------------------------------
    actor = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
        db_index=True,
        help_text="The admin user who performed the action. NULL if the user has since been deleted.",
    )
    actor_email = models.EmailField(
        max_length=254,
        db_index=True,
        blank=True,
        default="",
        help_text="Denormalised actor email — retained even if the user record is deleted.",
    )

    # What happened -----------------------------------------------------------
    action_type = models.CharField(
        max_length=50,
        choices=ActionType.choices,
        db_index=True,
    )

    # Which object was affected -----------------------------------------------
    target_content_type = models.CharField(
        max_length=200,
        db_index=True,
        help_text='e.g. "users.user", "escrow.escrowaccount"',
    )
    target_object_id = models.CharField(
        max_length=255,
        db_index=True,
        help_text="String representation of the target object PK.",
    )
    target_repr = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="str() of the target object at the time of action.",
    )

    # State snapshots ---------------------------------------------------------
    before_state: dict[str, Any] | None = models.JSONField(
        null=True,
        blank=True,
        default=None,
        help_text="Serialised object state BEFORE the action.  NULL for CREATE.",
    )
    after_state: dict[str, Any] | None = models.JSONField(
        null=True,
        blank=True,
        default=None,
        help_text="Serialised object state AFTER the action.  NULL for DELETE.",
    )

    # Context -----------------------------------------------------------------
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IPv4 or IPv6 address of the request origin.",
    )
    user_agent = models.CharField(
        max_length=512,
        blank=True,
        default="",
        help_text="HTTP User-Agent header (truncated to 512 chars).",
    )
    session_key = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text="Django session key at the time of action.",
    )

    # Timestamps --------------------------------------------------------------
    timestamp = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        editable=False,
        help_text="UTC timestamp.  Never update this field.",
    )

    class Meta:
        app_label = "admin_audit"
        verbose_name = "Admin Audit Log"
        verbose_name_plural = "Admin Audit Logs"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["actor", "timestamp"], name="audit_actor_ts_idx"),
            models.Index(
                fields=["target_content_type", "target_object_id"],
                name="audit_target_idx",
            ),
            models.Index(fields=["action_type", "timestamp"], name="audit_action_ts_idx"),
        ]
        # Prevent accidental updates via the ORM — log rows must be immutable.
        # The service layer is the only permitted write path.
        default_permissions = ("view",)  # Remove add/change/delete from default admin

    def __str__(self) -> str:
        return (
            f"[{self.action_type}] {self.actor_email} → "
            f"{self.target_content_type}:{self.target_object_id} "
            f"@ {self.timestamp.isoformat()}"
        )

    def save(self, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        """Guard: rows are immutable after initial creation.

        Raises:
            PermissionError: If an attempt is made to UPDATE an existing row.
        """
        if self.pk and AdminAuditLog.objects.filter(pk=self.pk).exists():
            raise PermissionError(
                "AdminAuditLog rows are immutable and cannot be updated. "
                "This is a tamper-evident audit trail."
            )
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:  # type: ignore[override]
        """Guard: rows are never deleted.

        Raises:
            PermissionError: Always.  Deletion of audit logs is prohibited.
        """
        raise PermissionError(
            "AdminAuditLog rows cannot be deleted. "
            "Audit logs must be retained per DPA 2021 and BoZ AML/CFT requirements."
        )
