"""
apps/payments/webhooks.py

Inbound webhook receivers for MTN MoMo and Airtel Money.

Both receivers follow the same pattern:
    1. Validate signature / callback token
    2. Delegate to PaymentService.process_webhook()
    3. Always return 200 to the provider to prevent retry storms

Security: Reject payloads exceeding 64KB. Log suspicious activity.
CSRF: @csrf_exempt required — providers send from external IPs.

Doc Ref: LG7-BE-005 v1.0
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from .models import Provider
from .services import PaymentService

logger = logging.getLogger(__name__)

# Maximum acceptable webhook payload size (64KB)
_MAX_PAYLOAD_BYTES = 65_536


def _sanitize_headers(request: HttpRequest) -> dict[str, str]:
    """
    Extract and sanitize HTTP headers for audit logging.
    Strips Authorization values but keeps header names.
    """
    sensitive = {"HTTP_AUTHORIZATION", "HTTP_X_CALLBACK_TOKEN"}
    sanitized = {}
    for key, value in request.META.items():
        if not key.startswith("HTTP_"):
            continue
        header_name = key[5:].replace("_", "-").title()
        sanitized[header_name] = "***REDACTED***" if key in sensitive else value
    return sanitized


def _validate_mtn_signature(request: HttpRequest) -> bool:
    """
    Validate MTN MoMo webhook X-Callback-Token header.

    MTN sends a static callback token set during API user provisioning.
    Compare using constant-time comparison to prevent timing attacks.
    """
    expected_token = getattr(settings, "MTN_MOMO_CALLBACK_TOKEN", "")
    if not expected_token:
        logger.warning(
            "MTN_MOMO_CALLBACK_TOKEN not configured — webhook signature validation skipped"
        )
        return True  # Allow in development/sandbox without token

    received_token = request.META.get("HTTP_X_CALLBACK_TOKEN", "")
    return hmac.compare_digest(expected_token.encode(), received_token.encode())


def _validate_airtel_signature(request: HttpRequest, raw_body: bytes) -> bool:
    """
    Validate Airtel Money webhook HMAC-SHA256 signature.

    Airtel signs the request body with the client_secret using HMAC-SHA256.
    Header: X-Signature
    """
    client_secret = getattr(settings, "AIRTEL_MONEY_CLIENT_SECRET", "")
    received_sig = request.META.get("HTTP_X_SIGNATURE", "")

    if not client_secret or not received_sig:
        # In sandbox, Airtel may not send signatures
        sandbox = getattr(settings, "AIRTEL_MONEY_ENVIRONMENT", "sandbox") == "sandbox"
        if sandbox:
            logger.debug("Airtel sandbox — skipping signature validation")
            return True
        logger.warning("Missing Airtel signature or client_secret")
        return False

    expected_sig = hmac.new(
        client_secret.encode(),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_sig, received_sig)


@method_decorator(csrf_exempt, name="dispatch")
class MTNMoMoWebhookView(View):
    """
    Receives MTN MoMo payment status callbacks.

    MTN sends a POST when the buyer approves or declines the USSD prompt.
    Payload includes the X-Reference-Id (our idempotency key) and status.

    MTN expects a 200 response within 5 seconds — delegate processing
    to Celery (via PaymentService) and return immediately.
    """

    http_method_names = ["post"]

    def post(self, request: HttpRequest) -> HttpResponse:
        """Handle MTN MoMo webhook POST."""
        # Size guard
        content_length = int(request.META.get("CONTENT_LENGTH", 0) or 0)
        if content_length > _MAX_PAYLOAD_BYTES:
            logger.warning(
                "MTN webhook payload too large: %d bytes from %s",
                content_length,
                request.META.get("REMOTE_ADDR"),
            )
            return HttpResponse(status=413)

        raw_body = request.body
        signature_valid = _validate_mtn_signature(request)

        # Parse payload
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            logger.error(
                "MTN webhook non-JSON payload from %s",
                request.META.get("REMOTE_ADDR"),
            )
            # Return 200 to prevent MTN retrying a malformed payload
            return HttpResponse(status=200)

        # MTN webhook payload shape:
        # {
        #   "financialTransactionId": "363440463",
        #   "externalId": "947354",
        #   "amount": "500",
        #   "currency": "ZMW",
        #   "payer": {"partyIdType": "MSISDN", "partyId": "260971234567"},
        #   "payerMessage": "...",
        #   "payeeNote": "...",
        #   "status": "SUCCESSFUL"
        # }
        provider_reference = payload.get("financialTransactionId") or payload.get(
            "externalId", ""
        )
        event_type = payload.get("status", "UNKNOWN")

        logger.info(
            "MTN webhook received: ref=%s status=%s valid_sig=%s",
            provider_reference,
            event_type,
            signature_valid,
        )

        PaymentService.process_webhook(
            provider=Provider.MTN_MOMO,
            provider_reference=provider_reference,
            event_type=event_type,
            payload=payload,
            headers=_sanitize_headers(request),
            signature_valid=signature_valid,
        )

        # Always return 200 — if we return 4xx/5xx, MTN will retry
        return HttpResponse(status=200)


@method_decorator(csrf_exempt, name="dispatch")
class AirtelMoneyWebhookView(View):
    """
    Receives Airtel Money payment status callbacks.

    Airtel sends a POST when the payment is completed or failed.
    Status codes: TS (success), TF (failed).
    """

    http_method_names = ["post"]

    def post(self, request: HttpRequest) -> HttpResponse:
        """Handle Airtel Money webhook POST."""
        content_length = int(request.META.get("CONTENT_LENGTH", 0) or 0)
        if content_length > _MAX_PAYLOAD_BYTES:
            logger.warning(
                "Airtel webhook payload too large: %d bytes", content_length
            )
            return HttpResponse(status=200)  # Still return 200

        raw_body = request.body
        signature_valid = _validate_airtel_signature(request, raw_body)

        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            logger.error("Airtel webhook non-JSON payload")
            return HttpResponse(status=200)

        # Airtel webhook payload shape:
        # {
        #   "transaction": {
        #     "id": "LINGI-20240101-001",
        #     "message": "Airtel Money Payment",
        #     "status_code": "TS",
        #     "airtel_money_id": "CI240101.1234.A12345"
        #   }
        # }
        transaction_data = payload.get("transaction", {})
        provider_reference = (
            transaction_data.get("id")
            or transaction_data.get("airtel_money_id", "")
        )
        event_type = transaction_data.get("status_code", "UNKNOWN")

        logger.info(
            "Airtel webhook received: ref=%s status=%s valid_sig=%s",
            provider_reference,
            event_type,
            signature_valid,
        )

        PaymentService.process_webhook(
            provider=Provider.AIRTEL,
            provider_reference=provider_reference,
            event_type=event_type,
            payload=payload,
            headers=_sanitize_headers(request),
            signature_valid=signature_valid,
        )

        return HttpResponse(status=200)
