from django.contrib import admin

from apps.orders.models import Order, OrderDispute, OrderEvent, OrderLine, OrderShipment


class OrderLineInline(admin.TabularInline):
    model = OrderLine
    extra = 0
    readonly_fields = ["id", "product_name", "product_sku", "unit_price", "quantity", "line_total"]

    def line_total(self, obj):
        return obj.line_total
    line_total.short_description = "Line Total (ZMW)"


class OrderEventInline(admin.TabularInline):
    model = OrderEvent
    extra = 0
    readonly_fields = ["id", "from_status", "to_status", "triggered_by", "note", "created_at"]

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        "reference", "status", "buyer", "seller",
        "total_amount", "currency", "created_at",
    ]
    list_filter  = ["status", "fulfilment_type", "currency", "created_at"]
    search_fields = ["reference", "buyer__phone_number", "seller__phone_number"]
    readonly_fields = [
        "id", "reference", "subtotal", "platform_fee", "total_amount",
        "created_at", "updated_at", "submitted_at", "paid_at",
        "completed_at", "cancelled_at",
    ]
    inlines = [OrderLineInline, OrderEventInline]
    ordering = ["-created_at"]


@admin.register(OrderDispute)
class OrderDisputeAdmin(admin.ModelAdmin):
    list_display  = ["id", "order", "reason", "raised_by", "is_open", "created_at"]
    list_filter   = ["reason", "resolution"]
    search_fields = ["order__reference"]
    readonly_fields = ["id", "order", "raised_by", "created_at"]


@admin.register(OrderShipment)
class OrderShipmentAdmin(admin.ModelAdmin):
    list_display = ["order", "carrier", "tracking_number", "shipped_at"]
    readonly_fields = ["id", "order", "shipped_at", "created_at"]
