"""
apps/payments/tasks.py

Celery tasks for asynchronous payment processing.

Tasks deliberately contain minimal logic — they resolve objects and
delegate to service classes. This keeps tasks testable and prevents
business logic from living in task code.

Doc Ref: LG7-BE-005 v1.0
"""
from __future__ import annotations

import logging
import uuid

from celery import shared_task
from django.db import transaction

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    autoretry_for=(Exception,),
    retry_backoff=True,
    name="payments.trigger_escrow_hold_on_payment_success",
)
def trigger_escrow_hold_on_payment_success(
    self,
    escrow_account_id: str,
    payment_attempt_id: str,
) -> None:
    """
    Hold escrow funds and transition the order to PAYMENT_RECEIVED.

    Dispatched after a verified SUCCESS webhook for a collection attempt.
    """
    from apps.orders.models import Order, OrderStatus
    from apps.orders.services import OrderService
    from .models import PaymentAttempt

    logger.info(
        "Triggering escrow hold: escrow=%s payment=%s",
        escrow_account_id,
        payment_attempt_id,
    )

    try:
        attempt = PaymentAttempt.objects.get(pk=uuid.UUID(payment_attempt_id))
        account_id = uuid.UUID(escrow_account_id)

        order = Order.objects.select_related("buyer").get(
            escrow_account_id=account_id
        )
        if order.status == OrderStatus.PAYMENT_RECEIVED:
            logger.info("Order %s already paid — skipping duplicate hold", order.reference)
            return

        if attempt.amount != order.total_amount:
            raise ValueError(
                f"Payment amount {attempt.amount} != order total {order.total_amount}"
            )

        with transaction.atomic():
            OrderService.confirm_payment(
                order=order,
                payment_attempt=attempt,
                actor=order.buyer,
            )

        logger.info("Escrow hold + order confirm successful: escrow=%s", escrow_account_id)
    except Exception as exc:
        logger.exception(
            "Escrow hold failed: escrow=%s error=%s",
            escrow_account_id,
            exc,
        )
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    name="payments.poll_pending_payment_status",
)
def poll_pending_payment_status(self, payment_attempt_id: str) -> None:
    """
    Poll a provider for status of a PENDING payment attempt.

    Used as a fallback when webhooks are delayed or missed. Scheduled
    by the beat scheduler for PENDING attempts older than 5 minutes.

    Args:
        payment_attempt_id: UUID string of the PaymentAttempt to check.
    """
    from django.conf import settings

    from .models import PaymentAttempt
    from .services import PaymentService

    try:
        attempt = PaymentAttempt.objects.get(pk=uuid.UUID(payment_attempt_id))

        if attempt.status != PaymentAttempt.Status.PENDING:
            logger.debug(
                "Skipping poll — attempt %s already in terminal state %s",
                payment_attempt_id,
                attempt.status,
            )
            return

        if not attempt.provider_reference:
            logger.warning(
                "Cannot poll — no provider_reference on attempt %s",
                payment_attempt_id,
            )
            return

        logger.info(
            "Polling payment status: attempt=%s provider=%s ref=%s",
            payment_attempt_id,
            attempt.provider,
            attempt.provider_reference,
        )

        # Poll the appropriate provider
        from .models import Provider
        if attempt.provider == Provider.MTN_MOMO:
            from .providers.mtn_momo import MTNMoMoClient
            client = MTNMoMoClient.from_settings()
            result = client.get_payment_status(attempt.provider_reference)
            event_type = result.status  # "SUCCESSFUL", "FAILED", "PENDING"
        else:
            from .providers.airtel import AirtelMoneyClient
            client = AirtelMoneyClient.from_settings()
            result = client.get_payment_status(attempt.provider_reference)
            event_type = result.status  # "TS", "TF", "TP"

        # Process via webhook handler for consistent handling
        if event_type not in ("PENDING", "TP"):
            PaymentService.process_webhook(
                provider=attempt.provider,
                provider_reference=attempt.provider_reference,
                event_type=event_type,
                payload=result.raw_response,
                headers={},
                signature_valid=settings.DEBUG,
            )

    except Exception as exc:
        logger.exception(
            "Payment status poll failed: attempt=%s error=%s",
            payment_attempt_id,
            exc,
        )
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    max_retries=1,
    default_retry_delay=5,
    name="payments.auto_complete_mock_payment",
)
def auto_complete_mock_payment(self, payment_attempt_id: str) -> None:
    """
    Auto-complete a mock payment after a short delay.

    Simulates user approving the USSD prompt in mock/development mode.
    This allows testing the full payment flow without real credentials.

    Called automatically 3 seconds after a mock payment is created.
    """
    from .models import PaymentAttempt
    from .services import PaymentService

    try:
        attempt = PaymentAttempt.objects.get(pk=uuid.UUID(payment_attempt_id))

        if attempt.status != PaymentAttempt.Status.PENDING:
            logger.debug(
                "Mock payment already processed: attempt=%s status=%s",
                payment_attempt_id,
                attempt.status,
            )
            return

        logger.info(
            "Auto-completing mock payment (simulating USSD approval): attempt=%s amount=%s",
            payment_attempt_id,
            attempt.amount,
        )

        # Simulate successful payment approval by calling webhook handler
        PaymentService.process_webhook(
            provider=attempt.provider,
            provider_reference=attempt.provider_reference,
            event_type="SUCCESSFUL",  # MTN uses "SUCCESSFUL", mock uses this too
            payload={"status": "SUCCESSFUL", "externalId": attempt.provider_reference},
            headers={},
            signature_valid=True,  # Trust our own mock
        )

        logger.info(
            "Mock payment auto-completed: attempt=%s reference=%s",
            payment_attempt_id,
            attempt.provider_reference,
        )

    except Exception as exc:
        logger.exception(
            "Mock payment auto-complete failed: attempt=%s error=%s",
            payment_attempt_id,
            exc,
        )
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    name="payments.retry_dead_letters",
    max_retries=1,
)
def retry_dead_letters(self) -> dict:
    """
    Retry dead-lettered webhooks that are eligible for reprocessing.

    Picks up PENDING dead letters whose next_retry_at is in the past.
    After 3 failures the letter is marked FAILED_PERMANENTLY.

    Runs every 5 minutes via Celery Beat.
    """
    from django.utils import timezone

    from .models import WebhookDeadLetter
    from .services import PaymentService

    now = timezone.now()
    letters = WebhookDeadLetter.objects.filter(
        retry_status=WebhookDeadLetter.RetryStatus.PENDING,
        next_retry_at__lte=now,
    ).order_by("created_at")[:20]

    retried = 0
    failed = 0

    for letter in letters:
        if letter.retry_count >= letter.max_retries:
            letter.retry_status = WebhookDeadLetter.RetryStatus.FAILED_PERMANENTLY
            letter.save(update_fields=["retry_status"])
            failed += 1
            logger.warning(
                "Dead letter permanently failed: ref=%s retries=%d",
                letter.provider_reference, letter.retry_count,
            )
            continue

        try:
            PaymentService.process_webhook(
                provider=letter.provider,
                provider_reference=letter.provider_reference,
                event_type=letter.payload.get("status", "UNKNOWN"),
                payload=letter.payload,
                headers=letter.headers,
                signature_valid=True,
            )
            letter.retry_status = WebhookDeadLetter.RetryStatus.RETRIED
            letter.last_retry_at = now
            letter.save(update_fields=["retry_status", "last_retry_at"])
            retried += 1
            logger.info(
                "Dead letter retried successfully: ref=%s",
                letter.provider_reference,
            )
        except Exception as exc:  # noqa: BLE001
            letter.retry_count += 1
            letter.last_retry_at = now
            letter.error_message = str(exc)
            backoff_minutes = 5 * (3 ** letter.retry_count)
            letter.next_retry_at = now + timezone.timedelta(minutes=backoff_minutes)
            letter.save(
                update_fields=["retry_count", "last_retry_at", "error_message", "next_retry_at"]
            )
            logger.warning(
                "Dead letter retry failed: ref=%s retries=%d next_retry=%s",
                letter.provider_reference, letter.retry_count, letter.next_retry_at,
            )

    return {"retried": retried, "failed": failed}
