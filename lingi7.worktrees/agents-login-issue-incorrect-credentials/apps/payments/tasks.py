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
    Trigger EscrowService.hold_funds() after a successful payment confirmation.

    This task is dispatched by PaymentService._handle_webhook_event() when
    a SUCCESS webhook is received. It runs outside the webhook HTTP request
    cycle to prevent timeout issues.

    Args:
        escrow_account_id: UUID string of the EscrowAccount to hold.
        payment_attempt_id: UUID string of the confirming PaymentAttempt.
    """
    from apps.escrow.services import EscrowService
    from .models import PaymentAttempt

    logger.info(
        "Triggering escrow hold: escrow=%s payment=%s",
        escrow_account_id,
        payment_attempt_id,
    )

    try:
        attempt = PaymentAttempt.objects.get(pk=uuid.UUID(payment_attempt_id))
        EscrowService.hold_funds(
            escrow_account_id=uuid.UUID(escrow_account_id),
            payment_attempt=attempt,
        )
        logger.info(
            "Escrow hold successful: escrow=%s",
            escrow_account_id,
        )
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
                signature_valid=True,  # Internal poll — no external signature
            )

    except Exception as exc:
        logger.exception(
            "Payment status poll failed: attempt=%s error=%s",
            payment_attempt_id,
            exc,
        )
        raise self.retry(exc=exc)
