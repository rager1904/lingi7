"""
Logistics Celery tasks for Lingi7.

Tasks:
- poll_carrier_apis: Poll carriers every 2h for tracking updates.
- start_escrow_auto_confirm_timer: Start 7-day countdown post-delivery.
- sla_breach_check: Alert if shipment exceeds expected transit time.

Reference: LG7-BE-009 | apps/logistics/tasks.py
"""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)

# Default auto-confirm window in days (configurable via Django settings)
AUTO_CONFIRM_DAYS = 7


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=300,  # 5 minutes
    name="logistics.poll_carrier_apis",
)
def poll_carrier_apis(self) -> dict:
    """
    Poll all carrier APIs for active shipments and ingest updates.

    Runs every 2 hours via Celery Beat. Only polls shipments in
    non-terminal states with a carrier tracking number set.

    Returns:
        Dict with counts of updated/unchanged/failed shipments.
    """
    from apps.logistics.models import Shipment
    from apps.logistics.carriers.generic import GenericCarrierClient

    terminal_statuses = {Shipment.Status.DELIVERED, Shipment.Status.RETURNED}

    active_shipments = (
        Shipment.objects
        .exclude(status__in=terminal_statuses)
        .filter(carrier_tracking_number__gt="")
        .select_related("order")
    )

    stats = {"polled": 0, "updated": 0, "unchanged": 0, "failed": 0}

    for shipment in active_shipments:
        try:
            client = GenericCarrierClient.get_client(shipment.carrier)
            if client is None:
                continue

            result = client.get_tracking_status(shipment.carrier_tracking_number)

            if result:
                from apps.logistics.services import LogisticsService
                LogisticsService.ingest_tracking_event(
                    shipment=shipment,
                    to_status=result["status"],
                    description=result.get("description", ""),
                    location=result.get("location", ""),
                    source="CARRIER_POLL",
                    raw_payload=result.get("raw"),
                    event_timestamp=result.get("event_timestamp"),
                )
                stats["updated"] += 1
            else:
                stats["unchanged"] += 1

            # Update last poll timestamp
            shipment.last_carrier_poll_at = timezone.now()
            shipment.save(update_fields=["last_carrier_poll_at"])

            stats["polled"] += 1

        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Carrier poll failed for Shipment #%s: %s",
                shipment.pk,
                exc,
                exc_info=True,
            )
            stats["failed"] += 1
            continue

    logger.info("Carrier poll complete: %s", stats)
    return stats


@shared_task(
    bind=True,
    max_retries=5,
    default_retry_delay=60,
    name="logistics.start_escrow_auto_confirm_timer",
)
def start_escrow_auto_confirm_timer(self, order_id: int) -> str:
    """
    Start the escrow auto-confirm countdown for a delivered order.

    This task is dispatched immediately on DELIVERED confirmation.
    It schedules the auto_confirm_escrow_release task to run after
    AUTO_CONFIRM_DAYS days from now.

    The buyer can raise a dispute before the timer expires. If they do,
    the escrow moves to DISPUTED and the auto-confirm is effectively
    cancelled (the escrow service enforces this).

    Args:
        order_id: The Order PK whose escrow should be auto-confirmed.

    Returns:
        Status string describing what was scheduled.
    """
    from django.conf import settings

    confirm_days = getattr(settings, "ESCROW_AUTO_CONFIRM_DAYS", AUTO_CONFIRM_DAYS)
    eta = timezone.now() + timedelta(days=confirm_days)

    # Schedule the actual release task
    auto_confirm_escrow_release.apply_async(
        args=[order_id],
        eta=eta,
    )

    logger.info(
        "Escrow auto-confirm timer started for Order #%s. "
        "Release scheduled at %s (%d days).",
        order_id,
        eta.isoformat(),
        confirm_days,
    )

    return f"Auto-confirm scheduled for Order #{order_id} at {eta.isoformat()}"


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=300,
    name="logistics.auto_confirm_escrow_release",
)
def auto_confirm_escrow_release(self, order_id: int) -> str:
    """
    Auto-confirm escrow release after the buyer review window expires.

    This task runs after AUTO_CONFIRM_DAYS have elapsed post-delivery.
    Before releasing, it checks:
    1. The escrow is still in DELIVERED state (not disputed/frozen).
    2. The order is not under active dispute.

    If conditions are met, it triggers EscrowService to release funds.

    Args:
        order_id: The Order PK to auto-confirm.

    Returns:
        Status string.
    """
    from apps.escrow.models import EscrowAccount
    from apps.escrow.services import EscrowService

    try:
        escrow = (
            EscrowAccount.objects
            .select_for_update()
            .get(order_id=order_id)
        )
    except EscrowAccount.DoesNotExist:
        logger.error(
            "auto_confirm_escrow_release: EscrowAccount not found for Order #%s.",
            order_id,
        )
        return f"Error: No escrow found for Order #{order_id}"

    # Only auto-confirm if escrow is in the DELIVERED state
    if escrow.state != EscrowAccount.State.DELIVERED:
        logger.info(
            "auto_confirm_escrow_release: Order #%s escrow is in state '%s' — "
            "skipping auto-confirm (may have been disputed or already released).",
            order_id,
            escrow.state,
        )
        return (
            f"Skipped: Order #{order_id} escrow state is '{escrow.state}' — "
            f"not eligible for auto-confirm."
        )

    try:
        system_actor = _get_system_actor()
        EscrowService.auto_confirm_delivered(
            escrow_account=escrow,
            actor=system_actor,
        )
        logger.info(
            "Order #%s escrow auto-confirmed and queued for release.", order_id
        )
        return f"Auto-confirmed Order #{order_id} escrow."

    except Exception as exc:  # noqa: BLE001
        logger.error(
            "auto_confirm_escrow_release failed for Order #%s: %s",
            order_id,
            exc,
            exc_info=True,
        )
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.critical(
                "CRITICAL: auto_confirm_escrow_release exhausted retries "
                "for Order #%s. Manual intervention required.",
                order_id,
            )
            return f"FAILED after max retries for Order #{order_id}"


@shared_task(
    name="logistics.sla_breach_check",
)
def sla_breach_check() -> dict:
    """
    Check for shipments that have breached their estimated delivery SLA.

    Runs daily. Finds shipments where:
    - status is not DELIVERED or RETURNED
    - estimated_delivery_date is in the past by more than 3 days

    Emits log warnings and (future) alerts to Slack/PagerDuty.

    Returns:
        Dict with count of breached shipments.
    """
    from apps.logistics.models import Shipment

    threshold = timezone.now().date() - timedelta(days=3)
    terminal_statuses = {Shipment.Status.DELIVERED, Shipment.Status.RETURNED}

    breached = (
        Shipment.objects
        .exclude(status__in=terminal_statuses)
        .filter(
            estimated_delivery_date__isnull=False,
            estimated_delivery_date__lt=threshold,
        )
        .select_related("order")
    )

    breach_count = 0
    for shipment in breached:
        days_overdue = (timezone.now().date() - shipment.estimated_delivery_date).days
        logger.warning(
            "SLA BREACH: Shipment #%s (Order #%s) is %d days overdue. "
            "Status: %s. Carrier: %s. Tracking: %s.",
            shipment.pk,
            shipment.order_id,
            days_overdue,
            shipment.status,
            shipment.carrier,
            shipment.carrier_tracking_number or "N/A",
        )
        breach_count += 1

    logger.info("SLA breach check complete: %d breached shipments.", breach_count)
    return {"breached": breach_count}


def _get_system_actor():
    """Return the system user for automated task actions."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.filter(is_superuser=True).order_by("pk").first()
