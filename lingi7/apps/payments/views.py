"""
apps/payments/views.py

Authenticated payment initiation and status polling for the buyer checkout flow.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated

from apps.users.permissions import CanTransact
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.models import Order, OrderStatus
from apps.payments.models import PaymentAttempt, Provider
from apps.payments.services import MaxAttemptsExceededError, PaymentError, PaymentService


def _map_provider(provider: str) -> str:
    mapping = {
        "MTN": Provider.MTN_MOMO,
        "MTN_MOMO": Provider.MTN_MOMO,
        "AIRTEL": Provider.AIRTEL,
    }
    key = provider.upper().replace(" ", "_")
    if key not in mapping:
        raise ValidationError({"provider": "Provider must be MTN or AIRTEL."})
    return mapping[key]


def _normalize_phone(phone: str) -> str:
    """MoMo APIs expect MSISDN (international without +), e.g. 260962431937."""
    from apps.users.phone_utils import normalize_zambian_phone

    e164 = normalize_zambian_phone(phone)
    if e164.startswith("+"):
        return e164[1:]
    return e164


class PaymentInitiateView(APIView):
    """POST /api/v1/payments/initiate/"""

    permission_classes = [IsAuthenticated, CanTransact]
    throttle_classes = []  # Disable throttling for payments in dev mode

    def post(self, request: Request) -> Response:
        order_id = request.data.get("order_id")
        provider = request.data.get("provider")
        phone_number = request.data.get("phone_number")

        if not order_id or not provider or not phone_number:
            raise ValidationError(
                {"detail": "order_id, provider, and phone_number are required."}
            )

        order = get_object_or_404(Order, pk=order_id, buyer=request.user)

        if order.status not in (OrderStatus.PENDING_PAYMENT, OrderStatus.DRAFT):
            raise ValidationError(
                {"detail": f"Order cannot be paid while in status {order.status}."}
            )

        if not order.escrow_account_id:
            raise ValidationError(
                {"detail": "Order has no escrow account. Submit the order first."}
            )

        provider_code = _map_provider(str(provider))
        payer_phone = _normalize_phone(str(phone_number))

        try:
            attempt = PaymentService.initiate_collection(
                order_id=uuid.UUID(str(order.id)),
                escrow_account_id=uuid.UUID(str(order.escrow_account_id)),
                provider=provider_code,
                amount=order.total_amount,
                payer_phone=payer_phone,
                reference=order.reference,
                initiated_by_id=request.user.pk,
            )
        except MaxAttemptsExceededError as exc:
            raise ValidationError({"detail": str(exc)})
        except PaymentError as exc:
            raise ValidationError({"detail": str(exc)})

        return Response(
            {
                "payment_id": str(attempt.id),
                "external_reference": attempt.provider_reference or "",
                "status": _public_status(attempt.status),
                "message": "Payment request sent. Approve the prompt on your phone.",
            },
            status=status.HTTP_201_CREATED,
        )


class PaymentStatusView(APIView):
    """GET /api/v1/payments/{payment_id}/status/"""

    permission_classes = [IsAuthenticated]
    throttle_classes = []  # Disable throttling for payment status polling

    def get(self, request: Request, payment_id: str) -> Response:
        attempt = get_object_or_404(
            PaymentAttempt,
            pk=payment_id,
            initiated_by=request.user,
        )
        return Response(
            {
                "id": str(attempt.id),
                "provider": attempt.provider,
                "status": _public_status(attempt.status),
                "amount_zmw": str(attempt.amount),
                "external_reference": attempt.provider_reference or None,
                "created_at": attempt.created_at.isoformat(),
            }
        )


class PaymentSimulateView(APIView):
    """POST /api/v1/payments/<uuid:payment_id>/simulate/

    Sandbox-only helper: simulates the buyer approving or declining the
    USSD payment prompt so the full checkout flow can be tested without
    a real phone. Disabled whenever DEBUG is False (production).

    The result is applied through PaymentService.process_webhook() so the
    simulate path exercises the exact same state transitions, idempotency,
    audit trail, and escrow-hold dispatch as a real provider webhook.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = []  # Disable throttling for sandbox simulation

    def post(self, request: Request, payment_id: str) -> Response:
        if not settings.DEBUG:
            raise PermissionDenied(
                {"detail": "Payment simulation is only available in sandbox mode."}
            )

        action = str(request.data.get("action", "")).upper()
        if action not in ("APPROVE", "DECLINE"):
            raise ValidationError({"action": "action must be APPROVE or DECLINE."})

        attempt = get_object_or_404(
            PaymentAttempt,
            pk=payment_id,
            initiated_by=request.user,
        )

        if attempt.status != PaymentAttempt.Status.PENDING:
            raise ValidationError(
                {
                    "detail": (
                        "Payment is not awaiting approval "
                        f"(current status: {_public_status(attempt.status)})."
                    )
                }
            )

        if not attempt.provider_reference:
            raise ValidationError(
                {"detail": "Payment attempt has no provider reference to simulate."}
            )

        event_type = "SUCCESSFUL" if action == "APPROVE" else "FAILED"

        PaymentService.process_webhook(
            provider=attempt.provider,
            provider_reference=attempt.provider_reference,
            event_type=event_type,
            payload={
                "status": event_type,
                "externalId": attempt.provider_reference,
                "simulated": True,
            },
            headers={},
            signature_valid=True,
        )

        attempt.refresh_from_db()

        return Response(
            {
                "payment_id": str(attempt.id),
                "status": _public_status(attempt.status),
                "message": (
                    "Payment approved. Funds will be held in escrow."
                    if action == "APPROVE"
                    else "Payment was declined."
                ),
            }
        )


def _public_status(attempt_status: str) -> str:
    if attempt_status in (PaymentAttempt.Status.INITIATED, PaymentAttempt.Status.PENDING):
        return "PENDING"
    if attempt_status == PaymentAttempt.Status.SUCCESS:
        return "SUCCESS"
    if attempt_status == PaymentAttempt.Status.CANCELLED:
        return "CANCELLED"
    return "FAILED"
