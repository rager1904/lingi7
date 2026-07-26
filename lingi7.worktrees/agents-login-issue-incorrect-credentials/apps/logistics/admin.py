"""
Django admin for logistics models.

TrackingEvent is read-only — no edit or delete. Shipment admin
exposes manual transition actions for operations staff.

Reference: LG7-BE-009 | apps/logistics/admin.py
"""

from django.contrib import admin
from django.utils.html import format_html

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
