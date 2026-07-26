"""
apps/payments/urls.py

URL patterns for the payments app.

Webhook endpoints are unauthenticated (providers call from external IPs).
All other payment endpoints require JWT authentication.

Doc Ref: LG7-BE-005 v1.0
"""
from django.urls import path

from .webhooks import AirtelMoneyWebhookView, MTNMoMoWebhookView

app_name = "payments"

urlpatterns = [
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
