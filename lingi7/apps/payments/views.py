"""
apps/payments/views.py

Authenticated payment initiation and status polling for the buyer checkout flow.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import ValidationError
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
    """MoMo APIs expect 9-digit national number without +260."""
    from apps.users.phone_utils import normalize_zambian_phone

    e164 = normalize_zambian_phone(phone)
    if e164.startswith("+260"):
        return e164[4:]
    return phone.strip().replace(" ", "").replace("-", "").lstrip("0")


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


def _public_status(attempt_status: str) -> str:
    if attempt_status in (PaymentAttempt.Status.INITIATED, PaymentAttempt.Status.PENDING):
        return "PENDING"
    if attempt_status == PaymentAttempt.Status.SUCCESS:
        return "SUCCESS"
    if attempt_status == PaymentAttempt.Status.CANCELLED:
        return "CANCELLED"
    return "FAILED"
