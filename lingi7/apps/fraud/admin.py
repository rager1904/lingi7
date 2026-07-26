"""
apps/fraud/admin.py

Django admin for fraud system — manual review queue for FROZEN orders.
Admin can APPROVE (release) or REJECT (refund) frozen orders.
All actions route through EscrowService — no direct model manipulation.

Document Ref: LG7-BE-008
"""

from __future__ import annotations

from django.contrib import admin, messages
from django.utils.html import format_html

from apps.fraud.models import FraudEvent, FraudRule, IPBlacklist


@admin.register(FraudRule)
class FraudRuleAdmin(admin.ModelAdmin):
    list_display = ["code", "is_active", "order_value_threshold_zmw", "account_age_days_threshold", "updated_at"]
    list_filter = ["is_active"]
    search_fields = ["code", "description"]
    readonly_fields = ["created_at", "updated_at"]

    fieldsets = (
        ("Rule Identity", {"fields": ("code", "description", "is_active")}),
        ("Thresholds", {
            "fields": (
                "account_age_days_threshold",
                "order_value_threshold_zmw",
                "payment_attempts_window_minutes",
                "payment_attempts_count_threshold",
                "order_velocity_window_minutes",
                "order_velocity_count_threshold",
                "payment_method_age_hours_threshold",
                "address_mismatch_account_age_days",
            )
        }),
        ("Audit", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(IPBlacklist)
class IPBlacklistAdmin(admin.ModelAdmin):
    list_display = ["ip_address", "reason", "is_active", "cloudflare_synced", "added_by", "created_at"]
    list_filter = ["is_active", "cloudflare_synced"]
    search_fields = ["ip_address", "reason"]
    readonly_fields = ["created_at", "cloudflare_synced", "synced_at"]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.added_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(FraudEvent)
class FraudEventAdmin(admin.ModelAdmin):
    """
    Manual review queue for FROZEN orders.

    Admins see fraud events with ML scores and SHAP values.
    APPROVE and REJECT actions route through EscrowService.
    FraudEvent records are read-only — no edit, no delete.
    """

    list_display = [
        "order_link",
        "verdict_badge",
        "rule_triggered",
        "ml_risk_score_display",
        "evaluated_at",
        "outcome_confirmed_fraud",
    ]
    list_filter = ["verdict", "rule_triggered", "outcome_confirmed_fraud"]
    search_fields = ["order__id", "rule_triggered", "notes"]
    readonly_fields = [
        "id", "order", "rule_triggered", "verdict", "ml_risk_score",
        "ml_freeze_threshold", "feature_snapshot", "shap_values",
        "notes", "evaluated_at", "outcome_confirmed_fraud", "outcome_updated_at",
    ]
    ordering = ["-evaluated_at"]
    actions = ["approve_frozen_orders", "reject_frozen_orders", "mark_false_positive"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("order", "order__buyer")

    def order_link(self, obj):
        return format_html(
            '<a href="/admin/orders/order/{}/change/">Order #{}</a>',
            obj.order_id,
            obj.order_id,
        )
    order_link.short_description = "Order"

    def verdict_badge(self, obj):
        colours = {
            "FLAGGED": "orange",
            "CLEARED": "green",
            "FROZEN": "red",
        }
        colour = colours.get(obj.verdict, "grey")
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colour,
            obj.verdict,
        )
    verdict_badge.short_description = "Verdict"

    def ml_risk_score_display(self, obj):
        if obj.ml_risk_score is None:
            return "—"
        score = float(obj.ml_risk_score)
        colour = "red" if score >= 0.65 else "orange" if score >= 0.40 else "green"
        return format_html(
            '<span style="color: {};">{:.4f}</span>', colour, score
        )
    ml_risk_score_display.short_description = "ML Score"

    def approve_frozen_orders(self, request, queryset):
        """Release FROZEN escrow accounts — fraud cleared by admin."""
        from apps.escrow.services import EscrowService
        from apps.escrow.models import EscrowAccount

        released = 0
        for event in queryset.filter(verdict=FraudEvent.Verdict.FROZEN):
            try:
                escrow = EscrowAccount.objects.get(order=event.order)
                EscrowService.admin_unfreeze_and_release(
                    escrow_account=escrow,
                    admin_user=request.user,
                    fraud_event=event,
                )
                released += 1
            except Exception as exc:
                self.message_user(
                    request,
                    f"Failed to release order #{event.order_id}: {exc}",
                    level=messages.ERROR,
                )
        if released:
            self.message_user(request, f"{released} order(s) approved and released.")
    approve_frozen_orders.short_description = "Approve: clear fraud flag and release escrow"

    def reject_frozen_orders(self, request, queryset):
        """Refund FROZEN escrow accounts — fraud confirmed by admin."""
        from apps.escrow.services import EscrowService
        from apps.escrow.models import EscrowAccount

        refunded = 0
        for event in queryset.filter(verdict=FraudEvent.Verdict.FROZEN):
            try:
                escrow = EscrowAccount.objects.get(order=event.order)
                EscrowService.admin_freeze_and_refund(
                    escrow_account=escrow,
                    admin_user=request.user,
                    fraud_event=event,
                )
                refunded += 1
            except Exception as exc:
                self.message_user(
                    request,
                    f"Failed to refund order #{event.order_id}: {exc}",
                    level=messages.ERROR,
                )
        if refunded:
            self.message_user(request, f"{refunded} order(s) rejected and refunded.")
    reject_frozen_orders.short_description = "Reject: confirm fraud and initiate refund"

    def mark_false_positive(self, request, queryset):
        """Mark fraud events as false positives for ML retraining feedback."""
        from django.utils import timezone

        updated = queryset.update(
            outcome_confirmed_fraud=False,
            outcome_updated_at=timezone.now(),
        )
        self.message_user(request, f"{updated} event(s) marked as false positive.")
    mark_false_positive.short_description = "Mark as false positive (retraining feedback)"

    def has_add_permission(self, request) -> bool:
        return False  # Fraud events are system-generated only

    def has_delete_permission(self, request, obj=None) -> bool:
        return False  # Immutable audit records

    def has_change_permission(self, request, obj=None) -> bool:
        return False  # Read-only + action-only
