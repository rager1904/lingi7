"""
apps/escrow/admin.py

Django admin configuration for the escrow system.

Key rules enforced here:
- LedgerEntry: NO edit, NO delete buttons — the ledger is immutable.
- EscrowAccount: Read-only core fields; state changes only via admin actions.
- Admin actions call EscrowService methods — never direct .save() on state.
"""
from __future__ import annotations

import uuid

from django.contrib import admin, messages
from django.utils.html import format_html

from apps.escrow.exceptions import EscrowError
from apps.escrow.models import (
    EscrowAccount,
    EscrowHold,
    FraudGateLog,
    LedgerEntry,
    ReconciliationLog,
)
from apps.escrow.services import EscrowService
from apps.escrow.state_machine import EscrowState


class LedgerEntryInline(admin.TabularInline):
    """Read-only inline ledger entries on the EscrowAccount detail page."""

    model = LedgerEntry
    extra = 0
    max_num = 0  # prevents adding new entries via admin
    can_delete = False
    fields = ["entry_type", "amount", "description", "operation_ref", "balance_after", "created_at"]
    readonly_fields = fields

    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False


class FraudGateLogInline(admin.TabularInline):
    """Read-only inline fraud gate evaluations on the EscrowAccount detail page."""

    model = FraudGateLog
    extra = 0
    max_num = 0
    can_delete = False
    fields = ["verdict", "ml_risk_score", "rule_flags", "freeze_reason", "created_at", "reviewed_by_ref"]
    readonly_fields = fields

    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False


@admin.register(EscrowAccount)
class EscrowAccountAdmin(admin.ModelAdmin):
    list_display = [
        "id_short",
        "order_ref",
        "state_badge",
        "balance_display",
        "currency",
        "created_at",
        "updated_at",
    ]
    list_filter = ["state", "currency"]
    search_fields = ["id", "order_ref", "buyer_ref", "vendor_ref"]
    readonly_fields = [
        "id",
        "order_ref",
        "buyer_ref",
        "vendor_ref",
        "state",
        "balance",
        "currency",
        "created_at",
        "updated_at",
        "released_at",
        "frozen_at",
    ]
    inlines = [LedgerEntryInline, FraudGateLogInline]
    actions = ["action_release", "action_freeze", "action_refund"]

    def has_delete_permission(self, request, obj=None) -> bool:
        return False

    def id_short(self, obj: EscrowAccount) -> str:
        return str(obj.id)[:8] + "…"
    id_short.short_description = "ID"

    def state_badge(self, obj: EscrowAccount) -> str:
        colour_map = {
            EscrowState.PENDING: "#9E9E9E",
            EscrowState.HELD: "#2196F3",
            EscrowState.IN_TRANSIT: "#FF9800",
            EscrowState.DELIVERED: "#8BC34A",
            EscrowState.RELEASED: "#4CAF50",
            EscrowState.DISPUTED: "#F44336",
            EscrowState.REFUNDED: "#9C27B0",
            EscrowState.FROZEN: "#F44336",
        }
        colour = colour_map.get(obj.state, "#9E9E9E")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;">{}</span>',
            colour,
            obj.state,
        )
    state_badge.short_description = "State"

    def balance_display(self, obj: EscrowAccount) -> str:
        return f"ZMW {obj.balance:,.2f}"
    balance_display.short_description = "Balance"

    def action_release(self, request, queryset):
        """Admin action: release DELIVERED accounts (passes fraud gate)."""
        actor_ref = uuid.UUID(str(request.user.pk)) if request.user.pk else None
        released, skipped = 0, 0
        for account in queryset.filter(state=EscrowState.DELIVERED):
            try:
                EscrowService.release_funds(
                    account_id=account.id,
                    actor_ref=actor_ref,
                )
                released += 1
            except EscrowError as exc:
                self.message_user(request, f"Account {account.id}: {exc}", messages.WARNING)
                skipped += 1
        self.message_user(request, f"{released} account(s) released. {skipped} skipped.")
    action_release.short_description = "Release selected DELIVERED accounts"

    def action_freeze(self, request, queryset):
        """Admin action: manually freeze accounts."""
        actor_ref = uuid.UUID(str(request.user.pk)) if request.user.pk else None
        frozen = 0
        for account in queryset.exclude(state__in=[EscrowState.RELEASED, EscrowState.REFUNDED, EscrowState.FROZEN]):
            try:
                EscrowService.freeze(
                    account_id=account.id,
                    actor_ref=actor_ref,
                    reason="Manual freeze by admin",
                )
                frozen += 1
            except EscrowError as exc:
                self.message_user(request, f"Account {account.id}: {exc}", messages.WARNING)
        self.message_user(request, f"{frozen} account(s) frozen.")
    action_freeze.short_description = "Manually freeze selected accounts"

    def action_refund(self, request, queryset):
        """Admin action: refund disputed or held accounts."""
        actor_ref = uuid.UUID(str(request.user.pk)) if request.user.pk else None
        refunded = 0
        for account in queryset.filter(state__in=[EscrowState.DISPUTED, EscrowState.HELD, EscrowState.FROZEN]):
            try:
                EscrowService.refund(
                    account_id=account.id,
                    actor_ref=actor_ref,
                    reason="Admin-initiated refund",
                )
                refunded += 1
            except EscrowError as exc:
                self.message_user(request, f"Account {account.id}: {exc}", messages.WARNING)
        self.message_user(request, f"{refunded} account(s) refunded.")
    action_refund.short_description = "Refund selected DISPUTED/HELD accounts"


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    """
    Read-only ledger entry admin.
    No add, change, or delete permissions.
    """

    list_display = ["id", "account", "entry_type", "amount", "description", "created_at"]
    list_filter = ["entry_type"]
    search_fields = ["id", "account__id", "operation_ref", "description"]
    readonly_fields = [
        "id", "account", "entry_type", "amount", "description",
        "operation_ref", "balance_after", "created_at", "created_by_ref",
    ]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(FraudGateLog)
class FraudGateLogAdmin(admin.ModelAdmin):
    list_display = ["id", "account", "verdict", "ml_risk_score", "created_at"]
    list_filter = ["verdict"]
    search_fields = ["account__id"]
    readonly_fields = [
        "id", "account", "rule_flags", "ml_risk_score", "verdict",
        "freeze_reason", "created_at", "reviewed_by_ref", "reviewed_at",
    ]

    def has_add_permission(self, request) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(ReconciliationLog)
class ReconciliationLogAdmin(admin.ModelAdmin):
    list_display = ["id", "run_at", "status", "discrepancy_detected", "total_accounts_checked"]
    list_filter = ["status", "discrepancy_detected"]
    readonly_fields = [
        "id", "run_at", "total_accounts_checked",
        "ledger_debit_total", "ledger_credit_total", "account_balance_total",
        "discrepancy_amount", "discrepancy_detected", "discrepancy_details",
        "status", "error_message",
    ]

    def has_add_permission(self, request) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
