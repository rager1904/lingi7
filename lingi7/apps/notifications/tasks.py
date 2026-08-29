"""
Notification Tasks — apps/notifications/tasks.py

All notification dispatch happens via Celery. Views and signals
must NEVER call NotificationService directly — always dispatch
via these tasks so notifications are non-blocking and retryable.

Retry policy:
  - Max 3 attempts (initial + 2 retries)
  - Exponential backoff: 60s, 120s
  - On final failure: log to NotificationLog with FAILED status
  - Dead-letter: FAILED logs are queryable for ops review

All tasks are idempotent by design — re-queueing a task that has
already sent a notification will create a new NotificationLog row
with attempt_count > 1, enabling full audit visibility.

Document Ref: LG7-BE-012
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from celery import shared_task

from .models import NotificationEventType, NotificationLog, NotificationStatus
from .services import NotificationService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Core dispatch tasks
# ---------------------------------------------------------------------------


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    name="notifications.send_sms",
    queue="notifications",
)
def send_sms_task(
    self,
    phone_number: str,
    event_type: str,
    context: Optional[dict[str, Any]] = None,
    user_pk: Optional[int] = None,
    related_object_id: str = "",
    related_object_type: str = "",
) -> Optional[str]:
    """Async Celery task: dispatch an SMS notification.

    Args:
        phone_number:        E.164 recipient.
        event_type:          NotificationEventType constant.
        context:             Template variable dict.
        user_pk:             Optional User PK for the log FK.
        related_object_id:   Triggering domain object PK.
        related_object_type: Django app.Model label.

    Returns:
        str UUID of the created NotificationLog, or None on failure.
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()
    recipient = None
    if user_pk is not None:
        try:
            recipient = User.objects.get(pk=user_pk)
        except User.DoesNotExist:
            logger.warning("send_sms_task: user pk=%s not found", user_pk)

    try:
        log = NotificationService.send_sms(
            phone_number=phone_number,
            event_type=event_type,
            context=context or {},
            recipient=recipient,
            related_object_id=related_object_id,
            related_object_type=related_object_type,
        )
    except Exception as exc:
        logger.exception("send_sms_task error | event=%s | to=%s", event_type, phone_number)
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))

    if log and log.status == NotificationStatus.FAILED:
        logger.warning(
            "SMS provider rejected | event=%s | to=%s | reason=%s",
            event_type, phone_number, log.error_message,
        )
        raise self.retry(
            exc=Exception(log.error_message),
            countdown=60 * (2 ** self.request.retries),
        )

    return str(log.id) if log else None


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    name="notifications.send_email",
    queue="notifications",
)
def send_email_task(
    self,
    to_address: str,
    event_type: str,
    context: Optional[dict[str, Any]] = None,
    user_pk: Optional[int] = None,
    related_object_id: str = "",
    related_object_type: str = "",
) -> Optional[str]:
    """Async Celery task: dispatch an email notification.

    Args:
        to_address:          Recipient email.
        event_type:          NotificationEventType constant.
        context:             Template variable dict.
        user_pk:             Optional User PK for the log FK.
        related_object_id:   Triggering domain object PK.
        related_object_type: Django app.Model label.

    Returns:
        str UUID of the created NotificationLog, or None on failure.
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()
    recipient = None
    if user_pk is not None:
        try:
            recipient = User.objects.get(pk=user_pk)
        except User.DoesNotExist:
            logger.warning("send_email_task: user pk=%s not found", user_pk)

    try:
        log = NotificationService.send_email(
            to_address=to_address,
            event_type=event_type,
            context=context or {},
            recipient=recipient,
            related_object_id=related_object_id,
            related_object_type=related_object_type,
        )
    except Exception as exc:
        logger.exception("send_email_task error | event=%s | to=%s", event_type, to_address)
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))

    if log and log.status == NotificationStatus.FAILED:
        logger.warning(
            "Email provider rejected | event=%s | to=%s | reason=%s",
            event_type, to_address, log.error_message,
        )
        raise self.retry(
            exc=Exception(log.error_message),
            countdown=60 * (2 ** self.request.retries),
        )

    return str(log.id) if log else None


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    name="notifications.notify_user",
    queue="notifications",
)
def notify_user_task(
    self,
    user_pk: int,
    event_type: str,
    context: Optional[dict[str, Any]] = None,
    channels: Optional[list[str]] = None,
    related_object_id: str = "",
    related_object_type: str = "",
) -> list[str]:
    """Async Celery task: dispatch to all preferred channels for a user.

    Args:
        user_pk:             User PK (required — resolves address from model).
        event_type:          NotificationEventType constant.
        context:             Template variable dict.
        channels:            List of NotificationChannel strings.
                             Defaults to auto-detect from user.
        related_object_id:   Triggering domain object PK.
        related_object_type: Django app.Model label.

    Returns:
        List of NotificationLog UUID strings created.
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()

    try:
        user = User.objects.get(pk=user_pk)
    except User.DoesNotExist:
        logger.error("notify_user_task: user pk=%s not found", user_pk)
        return []

    try:
        logs = NotificationService.notify_user(
            user=user,
            event_type=event_type,
            context=context or {},
            channels=channels,
            related_object_id=related_object_id,
            related_object_type=related_object_type,
        )
        return [str(log.id) for log in logs]

    except Exception as exc:
        logger.exception("notify_user_task error | user=%s | event=%s", user_pk, event_type)
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


# ---------------------------------------------------------------------------
# Convenience task dispatchers
# Used by other apps to fire notifications without importing services.
# Always use .delay() — never call directly.
# ---------------------------------------------------------------------------


def dispatch_registration(user_pk: int) -> None:
    """Fire WELCOME (SMS + email) and auto-send a phone verification OTP."""
    registration_notifications.delay(user_pk=user_pk)


@shared_task(
    bind=True,
    name="notifications.registration",
    queue="notifications",
)
def registration_notifications(self, user_pk: int) -> None:
    """Send welcome notifications and phone-verification OTP after signup.

    Runs as a Celery task so registration is never blocked on the
    notification providers (in dev this executes inline via
    CELERY_TASK_ALWAYS_EAGER).
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()
    try:
        user = User.objects.get(pk=user_pk)
    except User.DoesNotExist:
        logger.error("registration_notifications: user pk=%s not found", user_pk)
        return

    context = {"name": user.first_name or "there"}
    NotificationService.notify_user(
        user=user,
        event_type=NotificationEventType.WELCOME,
        context=context,
    )

    try:
        from apps.users.services import VerificationService

        VerificationService.send_phone_verify(user)
    except Exception:
        logger.exception("registration_notifications: phone OTP failed for %s", user_pk)


def dispatch_password_changed(user_pk: int) -> None:
    """Fire PASSWORD_CHANGED confirmation (email + SMS)."""
    notify_user_task.delay(
        user_pk=user_pk,
        event_type=NotificationEventType.PASSWORD_CHANGED,
        context={},
    )


def dispatch_order_placed(
    buyer_user_pk: int,
    order_id: str,
    amount_display: str,
) -> None:
    """Fire ORDER_PLACED notifications for buyer (SMS + email)."""
    notify_user_task.delay(
        user_pk=buyer_user_pk,
        event_type=NotificationEventType.ORDER_PLACED,
        context={"order_id": order_id, "amount": amount_display},
        related_object_id=order_id,
        related_object_type="orders.Order",
    )


def dispatch_payment_success(
    buyer_user_pk: int,
    order_id: str,
    amount_display: str,
) -> None:
    """Fire PAYMENT_SUCCESS notifications for buyer."""
    notify_user_task.delay(
        user_pk=buyer_user_pk,
        event_type=NotificationEventType.PAYMENT_SUCCESS,
        context={"order_id": order_id, "amount": amount_display},
        related_object_id=order_id,
        related_object_type="orders.Order",
    )


def dispatch_order_shipped(
    buyer_user_pk: int,
    order_id: str,
    tracking_number: str,
    carrier: str = "the seller",
) -> None:
    """Fire ORDER_SHIPPED notifications for buyer."""
    notify_user_task.delay(
        user_pk=buyer_user_pk,
        event_type=NotificationEventType.ORDER_SHIPPED,
        context={
            "order_id": order_id,
            "tracking_number": tracking_number,
            "carrier": carrier,
        },
        related_object_id=order_id,
        related_object_type="orders.Order",
    )


def dispatch_order_delivered(
    buyer_user_pk: int,
    order_id: str,
    auto_confirm_days: int = 7,
) -> None:
    """Fire ORDER_DELIVERED notifications for buyer."""
    notify_user_task.delay(
        user_pk=buyer_user_pk,
        event_type=NotificationEventType.ORDER_DELIVERED,
        context={"order_id": order_id, "auto_confirm_days": auto_confirm_days},
        related_object_id=order_id,
        related_object_type="orders.Order",
    )


def dispatch_order_cancelled(
    buyer_user_pk: int,
    order_id: str,
    amount_display: str,
    refund_status: str,
) -> None:
    """Fire ORDER_CANCELLED notifications for buyer."""
    notify_user_task.delay(
        user_pk=buyer_user_pk,
        event_type=NotificationEventType.ORDER_CANCELLED,
        context={
            "order_id": order_id,
            "amount": amount_display,
            "refund_status": refund_status,
        },
        related_object_id=order_id,
        related_object_type="orders.Order",
    )


def dispatch_escrow_released(
    vendor_user_pk: int,
    order_id: str,
    amount_display: str,
    payout_account: str,
) -> None:
    """Fire ESCROW_RELEASED notifications for vendor."""
    notify_user_task.delay(
        user_pk=vendor_user_pk,
        event_type=NotificationEventType.ESCROW_RELEASED,
        context={
            "order_id": order_id,
            "amount": amount_display,
            "payout_account": payout_account,
        },
        related_object_id=order_id,
        related_object_type="escrow.EscrowAccount",
    )


def dispatch_dispute_opened(
    buyer_user_pk: int,
    vendor_user_pk: int,
    order_id: str,
) -> None:
    """Fire DISPUTE_OPENED notifications for both buyer and vendor."""
    for user_pk in [buyer_user_pk, vendor_user_pk]:
        notify_user_task.delay(
            user_pk=user_pk,
            event_type=NotificationEventType.DISPUTE_OPENED,
            context={"order_id": order_id},
            related_object_id=order_id,
            related_object_type="disputes.Dispute",
        )


def dispatch_store_approved(vendor_user_pk: int, store_name: str) -> None:
    """Fire STORE_APPROVED notification for vendor."""
    notify_user_task.delay(
        user_pk=vendor_user_pk,
        event_type=NotificationEventType.STORE_APPROVED,
        context={"store_name": store_name},
    )


def dispatch_store_rejected(
    vendor_user_pk: int, store_name: str, reason: str
) -> None:
    """Fire STORE_REJECTED notification for vendor."""
    notify_user_task.delay(
        user_pk=vendor_user_pk,
        event_type=NotificationEventType.STORE_REJECTED,
        context={"store_name": store_name, "reason": reason},
    )


def dispatch_listing_approved(
    vendor_user_pk: int,
    product_name: str,
    product_id: str,
) -> None:
    """Fire LISTING_APPROVED notification for vendor."""
    notify_user_task.delay(
        user_pk=vendor_user_pk,
        event_type=NotificationEventType.LISTING_APPROVED,
        context={"product_name": product_name, "product_id": product_id},
        related_object_id=product_id,
        related_object_type="products.Product",
    )


def dispatch_listing_rejected(
    vendor_user_pk: int,
    product_name: str,
    product_id: str,
    reason: str,
) -> None:
    """Fire LISTING_REJECTED notification for vendor."""
    notify_user_task.delay(
        user_pk=vendor_user_pk,
        event_type=NotificationEventType.LISTING_REJECTED,
        context={
            "product_name": product_name,
            "product_id": product_id,
            "reason": reason,
        },
        related_object_id=product_id,
        related_object_type="products.Product",
    )


# ---------------------------------------------------------------------------
# Monitoring task — periodic health check
# ---------------------------------------------------------------------------


@shared_task(name="notifications.check_failed_notifications", queue="beat")
def check_failed_notifications() -> dict[str, int]:
    """Periodic task: count FAILED notifications in the last hour.

    Run via Celery Beat every 30 minutes. Logs a warning if the
    failure count exceeds threshold (ops team can wire this to
    PagerDuty via a log alert rule).

    Returns:
        Dict with failure counts per channel.
    """
    from datetime import timedelta

    from django.utils import timezone

    from .models import NotificationChannel

    one_hour_ago = timezone.now() - timedelta(hours=1)
    threshold = 10  # Alert if > 10 failures per channel per hour

    results: dict[str, int] = {}

    for channel in NotificationChannel.values:
        count = NotificationLog.objects.filter(
            channel=channel,
            status=NotificationStatus.FAILED,
            created_at__gte=one_hour_ago,
        ).count()
        results[channel] = count

        if count > threshold:
            logger.warning(
                "HIGH NOTIFICATION FAILURE RATE | channel=%s | failures=%d/hr",
                channel,
                count,
            )

    return results
