"""
apps/orders/signals.py

Django signals for the orders app.
Integrates with AdminAuditLog (Step 3) for immutable audit trail.
"""
import logging

from django.db import connection
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.orders.models import Order, OrderEvent

logger = logging.getLogger(__name__)


def _table_exists(table_name: str) -> bool:
    """Check if a database table exists without raising an exception.

    This is used to skip audit operations during migrations before tables
    are created.

    Args:
        table_name: Name of the table to check.

    Returns:
        True if the table exists in the current database; False otherwise.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_name = %s
                )
                """,
                [table_name],
            )
            return cursor.fetchone()[0]
    except Exception:
        # If we can't check, assume table doesn't exist (during migrations)
        return False


@receiver(post_save, sender=Order)
def log_order_status_change(sender, instance: Order, created: bool, **kwargs):
    """
    Mirror order status changes into AdminAuditLog.

    OrderEvent already captures the transition — this pushes to the
    platform-level immutable audit trail for cross-domain visibility.
    """
    # Skip if audit log table doesn't exist yet (during migrations)
    if not _table_exists("admin_audit_adminauditlog"):
        return

    try:
        from apps.admin_audit.models import AdminAuditLog
        AdminAuditLog.objects.create(
            action="ORDER_CREATED" if created else "ORDER_UPDATED",
            entity_type="Order",
            entity_id=str(instance.id),
            metadata={
                "reference": instance.reference,
                "status": instance.status,
                "buyer_id": str(instance.buyer_id),
                "seller_id": str(instance.seller_id),
                "total_amount": str(instance.total_amount),
            },
        )
    except Exception as exc:
        # Skip errors during migrations (table may not exist yet)
        if "does not exist" in str(exc).lower():
            return
        # Audit logging must never break the main flow
        logger.error("Failed to write OrderAuditLog: %s", exc)


@receiver(post_save, sender=OrderEvent)
def log_order_event(sender, instance: OrderEvent, created: bool, **kwargs):
    """Log each OrderEvent to the audit trail."""
    if not created:
        return

    # Skip if audit log table doesn't exist yet (during migrations)
    if not _table_exists("admin_audit_adminauditlog"):
        return

    try:
        from apps.admin_audit.models import AdminAuditLog
        AdminAuditLog.objects.create(
            action="ORDER_TRANSITION",
            entity_type="OrderEvent",
            entity_id=str(instance.id),
            metadata={
                "order_reference": instance.order.reference,
                "from_status": instance.from_status,
                "to_status": instance.to_status,
                "note": instance.note,
            },
        )
    except Exception as exc:
        # Skip errors during migrations (table may not exist yet)
        if "does not exist" in str(exc).lower():
            return
        logger.error("Failed to write OrderEventAuditLog: %s", exc)
