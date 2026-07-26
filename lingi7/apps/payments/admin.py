"""
apps/payments/admin.py

Read-only Django admin for payment audit models.
No edit or delete buttons — these are financial audit records.

Doc Ref: LG7-BE-005 v1.0
"""
from django.contrib import admin

from .models import PaymentAttempt, WebhookEvent


@admin.register(PaymentAttempt)
class PaymentAttemptAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "provider",
        "direction",
        "amount",
        "status",
        "payer_phone",
        "attempt_number",
        "created_at",
    ]
    list_filter = ["provider", "direction", "status"]
    search_fields = [
        "idempotency_key",
        "provider_reference",
        "payer_phone",
        "order_id",
    ]
    readonly_fields = [
        "id",
        "idempotency_key",
        "order_id",
        "escrow_account_id",
        "initiated_by",
        "provider",
        "direction",
        "amount",
        "currency",
        "status",
        "provider_reference",
        "provider_response_code",
        "provider_response_body",
        "payer_phone",
        "attempt_number",
        "created_at",
        "confirmed_at",
    ]
    ordering = ["-created_at"]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "provider",
        "event_type",
        "status",
        "signature_valid",
        "received_at",
        "processed_at",
    ]
    list_filter = ["provider", "status", "signature_valid"]
    search_fields = ["provider_reference", "event_type"]
    readonly_fields = [
        "id",
        "provider",
        "event_type",
        "provider_reference",
        "headers",
        "payload",
        "signature_valid",
        "status",
        "processing_error",
        "payment_attempt",
        "received_at",
        "processed_at",
    ]
    ordering = ["-received_at"]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
