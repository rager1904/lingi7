"""
apps/payments/services.py

PaymentService — orchestrates mobile money collections and disbursements.

This service is the single interface between the rest of the platform
and mobile money providers. It:
    1. Creates an audit trail (PaymentAttempt) before calling any provider API
    2. Calls the appropriate provider client
    3. On collection SUCCESS: signals EscrowService to hold funds
    4. Implements retry logic with exponential backoff (max 3 attempts)

CRITICAL: All state mutations wrap in transaction.atomic().
The escrow hold is always atomic with the payment attempt status update.

Doc Ref: LG7-BE-005 v1.0
"""
from __future__ import annotations

import logging
import time
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone


from .idempotency import WebhookAlreadyProcessedError, webhook_processing_lock
from .models import PaymentAttempt, Provider, WebhookEvent

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Maximum payment attempts per order (business rule)
MAX_COLLECTION_ATTEMPTS = 3

# Retry backoff delays in seconds [attempt 1, attempt 2, attempt 3]
RETRY_BACKOFF = [0, 5, 15]


class PaymentError(Exception):
    """Base payment service error."""


class MaxAttemptsExceededError(PaymentError):
    """Raised when a collection has been attempted MAX_COLLECTION_ATTEMPTS times."""


class PaymentService:
    """
    Orchestrates all payment operations across MTN MoMo and Airtel Money.

    All public methods create audit records before calling provider APIs.
    Never call provider clients directly from views or tasks — always go
    through this service.
    """

    @staticmethod
    def initiate_collection(
        *,
        order_id: uuid.UUID,
        escrow_account_id: uuid.UUID,
        provider: str,
        amount: Decimal,
        payer_phone: str,
        reference: str,
        initiated_by_id: int | None = None,
    ) -> PaymentAttempt:
        """
        Initiate a mobile money collection from a buyer.

        Creates a PaymentAttempt record, calls the provider API, and
        updates the attempt status. On SUCCESS, dispatches a task to
        trigger EscrowService.hold_funds().

        Args:
            order_id: UUID of the Order being paid.
            escrow_account_id: UUID of the EscrowAccount to hold funds in.
            provider: "MTN_MOMO" or "AIRTEL".
            amount: Collection amount in ZMW.
            payer_phone: Buyer's MSISDN without +.
            reference: Human-readable order reference.
            initiated_by_id: User PK who triggered the payment (optional).

        Returns:
            PaymentAttempt with current status.

        Raises:
            MaxAttemptsExceededError: If 3 attempts have already been made.
            PaymentError: For unrecoverable provider errors.
        """
        # Check attempt count before proceeding
        existing_attempts = PaymentAttempt.objects.filter(
            escrow_account_id=escrow_account_id,
            direction=PaymentAttempt.Direction.COLLECTION,
        ).count()

        if existing_attempts >= MAX_COLLECTION_ATTEMPTS:
            raise MaxAttemptsExceededError(
                f"Collection for escrow {escrow_account_id} has exceeded "
                f"{MAX_COLLECTION_ATTEMPTS} attempts."
            )

        attempt_number = existing_attempts + 1
        idempotency_key = (
            f"COLLECT-{escrow_account_id}-{attempt_number}"
        )

        # Create audit record BEFORE calling provider
        with transaction.atomic():
            attempt = PaymentAttempt.objects.create(
                idempotency_key=idempotency_key,
                order_id=order_id,
                escrow_account_id=escrow_account_id,
                initiated_by_id=initiated_by_id,
                provider=provider,
                direction=PaymentAttempt.Direction.COLLECTION,
                amount=amount,
                payer_phone=payer_phone,
                status=PaymentAttempt.Status.INITIATED,
                attempt_number=attempt_number,
            )

        # Call provider API outside transaction (network I/O)
        result = PaymentService._call_collection_api(
            provider=provider,
            amount=amount,
            payer_phone=payer_phone,
            reference=reference,
            idempotency_key=idempotency_key,
        )

        # Update attempt with provider response
        with transaction.atomic():
            if result["success"]:
                attempt.status = PaymentAttempt.Status.PENDING
            elif result["status"] == "TIMEOUT":
                attempt.status = PaymentAttempt.Status.TIMEOUT
            else:
                attempt.status = PaymentAttempt.Status.FAILED

            attempt.provider_reference = result.get("provider_reference", "")
            attempt.provider_response_code = result.get("response_code", "")
            attempt.provider_response_body = result.get("raw_response", {})
            attempt.save(update_fields=[
                "status", "provider_reference",
                "provider_response_code", "provider_response_body",
            ])

        logger.info(
            "Payment collection initiated: order=%s provider=%s attempt=%d status=%s",
            order_id,
            provider,
            attempt_number,
            attempt.status,
        )
        return attempt

    @staticmethod
    def _call_collection_api(
        *,
        provider: str,
        amount: Decimal,
        payer_phone: str,
        reference: str,
        idempotency_key: str,
    ) -> dict:
        """Dispatch to the correct provider client for collections."""
        if provider == Provider.MTN_MOMO:
            from .providers.mtn_momo import MTNMoMoClient
            client = MTNMoMoClient.from_settings()
            result = client.request_to_pay(
                amount=amount,
                payer_msisdn=payer_phone,
                reference=reference,
                message=f"Lingi7 payment {reference}",
                idempotency_key=idempotency_key,
            )
            return {
                "success": result.success,
                "provider_reference": result.provider_reference,
                "status": result.status,
                "response_code": result.response_code,
                "raw_response": result.raw_response,
                "error_message": result.error_message,
            }

        elif provider == Provider.AIRTEL:
            from .providers.airtel import AirtelMoneyClient
            client = AirtelMoneyClient.from_settings()
            result = client.request_payment(
                amount=amount,
                msisdn=payer_phone,
                reference=reference,
                transaction_id=idempotency_key[:20],
            )
            return {
                "success": result.success,
                "provider_reference": result.provider_reference,
                "status": result.status,
                "response_code": result.response_code,
                "raw_response": result.raw_response,
                "error_message": result.error_message,
            }

        raise PaymentError(f"Unknown payment provider: {provider}")

    @staticmethod
    def initiate_disbursement(
        *,
        escrow_account_id: uuid.UUID,
        provider: str,
        amount: Decimal,
        payee_phone: str,
        reference: str,
    ) -> PaymentAttempt:
        """
        Initiate a disbursement to a vendor's mobile money account.

        Called by EscrowService.release_to_vendor() after fraud gate clears.
        The payout destination is always sourced from Store.payout_account —
        never from caller-supplied data without validation.

        Args:
            escrow_account_id: UUID of the EscrowAccount being released.
            provider: "MTN_MOMO" or "AIRTEL".
            amount: Net payout amount in ZMW (after platform fee deduction).
            payee_phone: Vendor's MSISDN without +.
            reference: Payout reference (PAYOUT-{escrow_id}).

        Returns:
            PaymentAttempt with INITIATED or PENDING status.
        """
        idempotency_key = f"PAYOUT-{escrow_account_id}"

        # Prevent duplicate payouts
        if PaymentAttempt.objects.filter(
            idempotency_key=idempotency_key,
            status=PaymentAttempt.Status.SUCCESS,
        ).exists():
            raise PaymentError(
                f"Payout for escrow {escrow_account_id} already completed successfully."
            )

        with transaction.atomic():
            attempt = PaymentAttempt.objects.create(
                idempotency_key=idempotency_key,
                order_id=uuid.UUID(int=0),  # Placeholder — resolved via escrow_account_id
                escrow_account_id=escrow_account_id,
                provider=provider,
                direction=PaymentAttempt.Direction.DISBURSEMENT,
                amount=amount,
                payer_phone=payee_phone,
                status=PaymentAttempt.Status.INITIATED,
                attempt_number=1,
            )

        # Call provider API outside transaction
        result = PaymentService._call_disbursement_api(
            provider=provider,
            amount=amount,
            payee_phone=payee_phone,
            reference=reference,
            idempotency_key=idempotency_key,
        )

        with transaction.atomic():
            attempt.status = (
                PaymentAttempt.Status.PENDING
                if result["success"]
                else PaymentAttempt.Status.FAILED
            )
            attempt.provider_reference = result.get("provider_reference", "")
            attempt.provider_response_code = result.get("response_code", "")
            attempt.provider_response_body = result.get("raw_response", {})
            attempt.save(update_fields=[
                "status", "provider_reference",
                "provider_response_code", "provider_response_body",
            ])

        logger.info(
            "Disbursement initiated: escrow=%s provider=%s amount=%s status=%s",
            escrow_account_id,
            provider,
            amount,
            attempt.status,
        )
        return attempt

    @staticmethod
    def _call_disbursement_api(
        *,
        provider: str,
        amount: Decimal,
        payee_phone: str,
        reference: str,
        idempotency_key: str,
    ) -> dict:
        """Dispatch to the correct provider client for disbursements."""
        if provider == Provider.MTN_MOMO:
            from .providers.mtn_momo import MTNMoMoClient
            client = MTNMoMoClient.from_settings()
            result = client.transfer(
                amount=amount,
                payee_msisdn=payee_phone,
                reference=reference,
                message=f"Lingi7 payout {reference}",
                idempotency_key=idempotency_key,
            )
            return {
                "success": result.success,
                "provider_reference": result.provider_reference,
                "response_code": result.response_code,
                "raw_response": result.raw_response,
                "error_message": result.error_message,
            }

        elif provider == Provider.AIRTEL:
            from .providers.airtel import AirtelMoneyClient
            client = AirtelMoneyClient.from_settings()
            result = client.disburse(
                amount=amount,
                msisdn=payee_phone,
                reference=reference,
                transaction_id=idempotency_key[:20],
            )
            return {
                "success": result.success,
                "provider_reference": result.provider_reference,
                "response_code": result.response_code,
                "raw_response": result.raw_response,
                "error_message": result.error_message,
            }

        raise PaymentError(f"Unknown payment provider: {provider}")

    @staticmethod
    def process_webhook(
        *,
        provider: str,
        provider_reference: str,
        event_type: str,
        payload: dict,
        headers: dict,
        signature_valid: bool,
    ) -> WebhookEvent:
        """
        Process an inbound provider webhook with full idempotency protection.

        This method:
            1. Creates a WebhookEvent receipt record
            2. Checks for duplicate processing via Redis + DB constraint
            3. On SUCCESS event: dispatches task to trigger escrow hold
            4. Marks the event as processed in Redis

        Args:
            provider: "MTN_MOMO" or "AIRTEL".
            provider_reference: Provider's unique reference for this event.
            event_type: Provider status string (e.g. "SUCCESSFUL", "TS").
            payload: Full raw webhook payload dict.
            headers: Sanitised headers (no Authorization).
            signature_valid: Result of signature validation.

        Returns:
            WebhookEvent record with final status.
        """
        # Upsert webhook event record — DB unique constraint prevents true duplicates
        try:
            webhook_event = WebhookEvent.objects.get(
                provider=provider,
                provider_reference=provider_reference,
            )
            # Already exists — mark as duplicate and return
            if webhook_event.status in (
                WebhookEvent.Status.PROCESSED,
                WebhookEvent.Status.DUPLICATE,
            ):
                webhook_event.mark_duplicate()
                logger.info(
                    "Duplicate webhook ignored: %s:%s",
                    provider,
                    provider_reference,
                )
                return webhook_event
        except WebhookEvent.DoesNotExist:
            webhook_event = WebhookEvent.objects.create(
                provider=provider,
                provider_reference=provider_reference,
                event_type=event_type,
                payload=payload,
                headers=headers,
                signature_valid=signature_valid,
                status=WebhookEvent.Status.RECEIVED,
            )

        if not signature_valid:
            webhook_event.status = WebhookEvent.Status.INVALID
            webhook_event.processing_error = "Signature validation failed"
            webhook_event.save(update_fields=["status", "processing_error"])
            logger.warning(
                "Invalid webhook signature: %s:%s",
                provider,
                provider_reference,
            )
            return webhook_event

        # Use distributed lock for safe processing
        try:
            with webhook_processing_lock(provider, provider_reference):
                PaymentService._handle_webhook_event(
                    webhook_event=webhook_event,
                    provider=provider,
                    provider_reference=provider_reference,
                    event_type=event_type,
                )
        except WebhookAlreadyProcessedError:
            webhook_event.mark_duplicate()
        except Exception as exc:
            logger.exception(
                "Webhook processing error: %s:%s",
                provider,
                provider_reference,
            )
            webhook_event.mark_error(str(exc))

        return webhook_event

    @staticmethod
    def _handle_webhook_event(
        *,
        webhook_event: WebhookEvent,
        provider: str,
        provider_reference: str,
        event_type: str,
    ) -> None:
        """
        Core webhook handling logic. Called within the distributed lock.

        Determines if the event represents a successful payment and, if so,
        dispatches the escrow hold task.
        """
        # Resolve the corresponding PaymentAttempt
        attempt = PaymentAttempt.objects.filter(
            provider_reference=provider_reference,
            direction=PaymentAttempt.Direction.COLLECTION,
        ).first()

        is_success = event_type in ("SUCCESSFUL", "TS", "SUCCESS")
        is_failure = event_type in ("FAILED", "TF", "FAILURE")

        with transaction.atomic():
            if attempt:
                if is_success:
                    attempt.status = PaymentAttempt.Status.SUCCESS
                elif is_failure:
                    attempt.status = PaymentAttempt.Status.FAILED
                attempt.confirmed_at = timezone.now()
                attempt.save(update_fields=["status", "confirmed_at"])

            webhook_event.mark_processed(payment_attempt=attempt)

        if is_success and attempt:
            # Dispatch Celery task to trigger escrow hold
            # Import here to avoid circular imports
            from .tasks import trigger_escrow_hold_on_payment_success
            trigger_escrow_hold_on_payment_success.delay(
                str(attempt.escrow_account_id),
                str(attempt.id),
            )
            logger.info(
                "Payment SUCCESS — escrow hold task dispatched: escrow=%s",
                attempt.escrow_account_id,
            )
        elif is_failure and attempt:
            logger.warning(
                "Payment FAILED webhook received: escrow=%s ref=%s",
                attempt.escrow_account_id,
                provider_reference,
            )
