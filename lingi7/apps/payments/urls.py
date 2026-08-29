"""
apps/payments/urls.py

URL patterns for the payments app.

Webhook endpoints are unauthenticated (providers call from external IPs).
All other payment endpoints require JWT authentication.

Doc Ref: LG7-BE-005 v1.0
"""
from django.urls import path

from .views import PaymentInitiateView, PaymentSimulateView, PaymentStatusView
from .webhooks import AirtelMoneyWebhookView, MTNMoMoWebhookView

app_name = "payments"

urlpatterns = [
    path("initiate/", PaymentInitiateView.as_view(), name="payment-initiate"),
    path(
        "<uuid:payment_id>/status/",
        PaymentStatusView.as_view(),
        name="payment-status",
    ),
    # Sandbox-only helper — simulates USSD approve/decline (DEBUG-gated)
    path(
        "<uuid:payment_id>/simulate/",
        PaymentSimulateView.as_view(),
        name="payment-simulate",
    ),
    # Webhook receivers — no authentication, signature-validated internally
    path(
        "webhooks/momo/",
        MTNMoMoWebhookView.as_view(),
        name="mtn-momo-webhook",
    ),
    path(
        "webhooks/airtel/",
        AirtelMoneyWebhookView.as_view(),
        name="airtel-webhook",
    ),
]
