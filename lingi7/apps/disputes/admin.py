"""
Dispute Admin — apps/disputes/admin.py

Read-heavy interface. All state changes go through admin actions that
call DisputeService — never direct field edits.
"""

from django.contrib import admin
from django.utils.html import format_html

from .models import Dispute, DisputeEvent, Evidence
from .services import DisputeService


class EvidenceInline(admin.TabularInline):
    model = Evidence
    extra = 0
    readonly_fields = [
        "id",
        "submitted_by_user",
        "submitted_by_role",
        "evidence_type",
        "description",
        "file",
        "created_at",
    ]
    can_delete = False

    def has_add_permission(self, request, obj=None) -> bool:
        return False


class DisputeEventInline(admin.TabularInline):
    model = DisputeEvent
    extra = 0
    readonly_fields = [
        "actor",
        "action",
        "before_status",
        "after_status",
        "notes",
        "created_at",
    ]
    can_delete = False

    def has_add_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Dispute)
class DisputeAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "order",
        "raised_by",
        "reason",
        "status_badge",
        "sla_status",
        "assigned_to",
        "created_at",
    ]
    list_filter = ["status", "reason"]
    search_fields = [
        "id",
        "order__reference",
        "raised_by__email",
        "raised_by__phone_number",
    ]
    readonly_fields = [
        "id",
        "order",
        "escrow_account",
        "raised_by",
        "reason",
        "description",
        "status",
        "sla_deadline",
        "resolved_by",
        "resolved_at",
        "refund_amount",
        "created_at",
        "updated_at",
    ]
    inlines = [EvidenceInline, DisputeEventInline]
    actions = ["action_resolve_buyer", "action_resolve_vendor"]

    @admin.action(description="Assign selected disputes to me and mark UNDER_REVIEW")
    def action_assign_to_me(self, request, queryset):
        assigned = 0
        skipped = 0
        for dispute in queryset.filter(status=Dispute.Status.OPEN):
            try:
                DisputeService.assign_dispute(
                    dispute=dispute, assigned_to=request.user, assigned_by=request.user
                )
                assigned += 1
            except Exception as exc:
                self.message_user(request, f"Dispute {dispute.pk}: {exc}")
                skipped += 1
        self.message_user(request, f"{assigned} dispute(s) assigned. {skipped} skipped.")

    # expose assign action in actions list
    actions += ["action_assign_to_me"]

    def status_badge(self, obj: Dispute) -> str:
        colour_map = {
            Dispute.Status.OPEN: "#f59e0b",
            Dispute.Status.UNDER_REVIEW: "#3b82f6",
            Dispute.Status.RESOLVED_BUYER: "#10b981",
            Dispute.Status.RESOLVED_VENDOR: "#6366f1",
            Dispute.Status.WITHDRAWN: "#9ca3af",
        }
        colour = colour_map.get(obj.status, "#9ca3af")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px">{}</span>',
            colour,
            obj.get_status_display(),
        )

    status_badge.short_description = "Status"  # type: ignore[attr-defined]

    def sla_status(self, obj: Dispute) -> str:
        if not obj.is_open:
            return "—"
        if obj.is_sla_breached:
            return format_html('<span style="color:red;font-weight:bold">BREACHED</span>')
        return format_html('<span style="color:green">On Time</span>')

    sla_status.short_description = "SLA"  # type: ignore[attr-defined]

    def action_resolve_buyer(self, request, queryset):
        resolved = 0
        for dispute in queryset.filter(
            status__in=[Dispute.Status.OPEN, Dispute.Status.UNDER_REVIEW]
        ):
            try:
                DisputeService.resolve_buyer_favour(
                    dispute=dispute,
                    resolved_by=request.user,
                    resolution_notes="Resolved via bulk admin action — buyer favour.",
                )
                resolved += 1
            except Exception as exc:
                self.message_user(
                    request, f"Dispute {dispute.pk}: {exc}", level="ERROR"
                )
        self.message_user(request, f"{resolved} dispute(s) resolved in buyer favour.")

    action_resolve_buyer.short_description = "Resolve selected → Buyer Favour"  # type: ignore[attr-defined]

    def action_resolve_vendor(self, request, queryset):
        resolved = 0
        for dispute in queryset.filter(
            status__in=[Dispute.Status.OPEN, Dispute.Status.UNDER_REVIEW]
        ):
            try:
                DisputeService.resolve_vendor_favour(
                    dispute=dispute,
                    resolved_by=request.user,
                    resolution_notes="Resolved via bulk admin action — vendor favour.",
                )
                resolved += 1
            except Exception as exc:
                self.message_user(
                    request, f"Dispute {dispute.pk}: {exc}", level="ERROR"
                )
        self.message_user(request, f"{resolved} dispute(s) resolved in vendor favour.")

    action_resolve_vendor.short_description = "Resolve selected → Vendor Favour"  # type: ignore[attr-defined]

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Evidence)
class EvidenceAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "dispute",
        "submitted_by_user",
        "submitted_by_role",
        "evidence_type",
        "created_at",
    ]
    readonly_fields = [f.name for f in Evidence._meta.fields]

    def has_add_permission(self, request) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
