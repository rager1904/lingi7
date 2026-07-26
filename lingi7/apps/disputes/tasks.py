"""
Dispute Celery Tasks — apps/disputes/tasks.py

Scheduled tasks:
  - sla_breach_alert: runs hourly, flags disputes past SLA deadline
  - notify_vendor_dispute_raised: async notification to vendor on dispute creation
"""

import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name="disputes.sla_breach_alert")
def sla_breach_alert() -> dict:
    """
    Identify all open disputes that have breached their SLA deadline.

    Logs each breached dispute and emits an alert (SMS/email to admin team).
    Should be scheduled every hour via Celery Beat.

    Returns:
        dict with count of breached disputes found.
    """
    from apps.notifications.services import NotificationService

    from .models import Dispute

    breached = Dispute.objects.filter(
        status__in=[Dispute.Status.OPEN, Dispute.Status.UNDER_REVIEW],
        sla_deadline__lt=timezone.now(),
    ).select_related("order", "raised_by", "assigned_to")

    count = breached.count()

    for dispute in breached:
        logger.warning(
            "SLA breached: dispute=%s order=%s raised_by=%s sla_deadline=%s",
            dispute.pk,
            dispute.order_id,
            dispute.raised_by.email,
            dispute.sla_deadline.isoformat(),
        )

        assignee_phone = (
            dispute.assigned_to.phone_number if dispute.assigned_to else None
        )
        if assignee_phone:
            NotificationService.send_sms(
                to=assignee_phone,
                body=(
                    f"[LINGI7 ALERT] Dispute {dispute.pk} has breached its 72h SLA. "
                    f"Order: {dispute.order_id}. Immediate resolution required."
                ),
            )

    logger.info("SLA breach check complete: %d breached disputes found.", count)
    return {"breached_count": count}


@shared_task(name="disputes.notify_vendor_dispute_raised")
def notify_vendor_dispute_raised(dispute_id: str) -> None:
    """
    Notify the vendor asynchronously when a dispute is raised against their order.

    Args:
        dispute_id: UUID string of the Dispute.
    """
    from apps.notifications.services import NotificationService

    from .models import Dispute

    try:
        dispute = Dispute.objects.select_related(
            "order__store__owner"
        ).get(pk=dispute_id)
    except Dispute.DoesNotExist:
        logger.error("notify_vendor_dispute_raised: dispute %s not found", dispute_id)
        return

    vendor = dispute.order.store.owner
    NotificationService.send_sms(
        to=vendor.phone_number,
        body=(
            f"A dispute has been raised on order {dispute.order_id}. "
            f"Reason: {dispute.get_reason_display()}. "
            "Please log into your vendor portal and submit evidence within 48 hours."
        ),
    )

    logger.info(
        "Vendor notified of dispute: dispute=%s vendor=%s",
        dispute_id,
        vendor.pk,
    )
