"""
Django admin for logistics models.

TrackingEvent is read-only — no edit or delete. Shipment admin
exposes manual transition actions for operations staff.

Reference: LG7-BE-009 | apps/logistics/admin.py
"""

from django.contrib import admin
from django.utils.html import format_html
from django import forms
from django.template.response import TemplateResponse
from django.urls import path
from django.shortcuts import redirect
from django.contrib import messages

from apps.logistics.models import Shipment, TrackingEvent


class TrackingEventInline(admin.TabularInline):
    """Inline display of tracking events on Shipment admin."""

    model = TrackingEvent
    extra = 0
    fields = ["event_timestamp", "status", "location", "description", "source"]
    readonly_fields = ["event_timestamp", "status", "location", "description", "source"]
    ordering = ["-event_timestamp"]

    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "order_link",
        "status_badge",
        "carrier",
        "carrier_tracking_number",
        "shipping_method",
        "estimated_delivery_date",
        "delivered_at",
        "created_at",
    ]
    list_filter = ["status", "carrier", "shipping_method", "origin_country"]
    search_fields = [
        "carrier_tracking_number",
        "order__id",
        "freight_forwarder",
    ]
    readonly_fields = [
        "tracking_token",
        "delivered_at",
        "delivery_confirmed_by",
        "last_carrier_poll_at",
        "created_at",
        "updated_at",
    ]
    inlines = [TrackingEventInline]
    ordering = ["-created_at"]
    actions = ["action_mark_dispatched", "action_mark_delivered"]

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("dispatch/", self.admin_site.admin_view(self.dispatch_view), name="logistics_shipment_dispatch"),
        ]
        return custom_urls + urls

    class DispatchForm(forms.Form):
        _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)
        carrier_tracking_number = forms.CharField(required=True, max_length=200)
        carrier = forms.CharField(required=False, max_length=100)

    def action_dispatch_with_tracking(self, request, queryset):
        selected = queryset.values_list("id", flat=True)
        return redirect(f"../dispatch/?ids={','.join(str(x) for x in selected)}")

    action_dispatch_with_tracking.short_description = "Dispatch selected shipments (provide tracking number)"

    def dispatch_view(self, request):
        ids = request.GET.get("ids", "")
        id_list = [s for s in ids.split(",") if s]
        if request.method == "POST":
            form = self.DispatchForm(request.POST)
            if form.is_valid():
                tracking = form.cleaned_data["carrier_tracking_number"]
                carrier = form.cleaned_data.get("carrier", "")
                dispatched = 0
                for sid in id_list:
                    try:
                        shipment = Shipment.objects.get(pk=sid)
                        from apps.logistics.services import LogisticsService
                        LogisticsService.mark_dispatched(
                            shipment=shipment,
                            actor=request.user,
                            carrier_tracking_number=tracking,
                            carrier=carrier,
                        )
                        dispatched += 1
                    except Exception as exc:
                        self.message_user(request, f"Shipment {sid}: {exc}", level=messages.ERROR)
                self.message_user(request, f"{dispatched} shipment(s) dispatched.")
                return redirect("../")
        else:
            form = self.DispatchForm(initial={"_selected_action": id_list})
        context = dict(self.admin_site.each_context(request), form=form, ids=ids, title="Dispatch shipments")
        return TemplateResponse(request, "admin/logistics/dispatch.html", context)

    @admin.action(description="Mark selected shipments as dispatched (requires tracking number)")
    def action_mark_dispatched(self, request, queryset):
        from apps.logistics.services import LogisticsService

        dispatched = 0
        skipped = 0
        for shipment in queryset:
            if not shipment.carrier_tracking_number:
                skipped += 1
                continue
            try:
                LogisticsService.mark_dispatched(
                    shipment=shipment,
                    actor=request.user,
                    carrier_tracking_number=shipment.carrier_tracking_number,
                    carrier=shipment.carrier or "",
                )
                dispatched += 1
            except Exception as exc:
                self.message_user(request, f"Shipment {shipment.pk}: {exc}")
        self.message_user(request, f"{dispatched} shipment(s) dispatched. {skipped} skipped (missing tracking).")

    @admin.action(description="Mark selected shipments as delivered")
    def action_mark_delivered(self, request, queryset):
        from apps.logistics.services import LogisticsService

        delivered = 0
        skipped = 0
        for shipment in queryset:
            try:
                LogisticsService.confirm_delivery(
                    shipment=shipment, actor=request.user, confirmed_by="ADMIN"
                )
                delivered += 1
            except Exception as exc:
                skipped += 1
                self.message_user(request, f"Shipment {shipment.pk}: {exc}")
        self.message_user(request, f"{delivered} shipment(s) marked delivered. {skipped} skipped.")

    def order_link(self, obj: Shipment) -> str:
        return format_html(
            '<a href="/admin/orders/order/{}/change/">Order #{}</a>',
            obj.order_id,
            obj.order_id,
        )
    order_link.short_description = "Order"

    def status_badge(self, obj: Shipment) -> str:
        colours = {
            Shipment.Status.CREATED: "#888",
            Shipment.Status.DISPATCHED: "#1a73e8",
            Shipment.Status.IN_TRANSIT: "#f9a825",
            Shipment.Status.CUSTOMS: "#e65100",
            Shipment.Status.CLEARED: "#7b1fa2",
            Shipment.Status.OUT_FOR_DELIVERY: "#00838f",
            Shipment.Status.DELIVERED: "#2e7d32",
            Shipment.Status.FAILED_DELIVERY: "#c62828",
            Shipment.Status.RETURNED: "#4e342e",
        }
        colour = colours.get(obj.status, "#888")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:11px;">{}</span>',
            colour,
            obj.get_status_display(),
        )
    status_badge.short_description = "Status"

    def has_delete_permission(self, request, obj=None) -> bool:
        """Shipments are never deleted — they're part of the audit trail."""
        return False


@admin.register(TrackingEvent)
class TrackingEventAdmin(admin.ModelAdmin):
    """Read-only view of all tracking events. No editing or deletion."""

    list_display = [
        "id",
        "shipment",
        "status",
        "location",
        "event_timestamp",
        "source",
    ]
    list_filter = ["status", "source"]
    search_fields = ["shipment__carrier_tracking_number", "description"]
    readonly_fields = [
        "shipment",
        "status",
        "location",
        "description",
        "source",
        "raw_payload",
        "event_timestamp",
        "created_at",
    ]
    ordering = ["-event_timestamp"]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
