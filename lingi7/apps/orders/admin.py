from django.contrib import admin
from django import forms
from django.template.response import TemplateResponse
from django.urls import path
from django.shortcuts import redirect
from django.contrib import messages

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
    actions = ["action_confirm_delivery", "action_complete_order", "action_cancel_order"]

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("cancel/", self.admin_site.admin_view(self.cancel_view), name="orders_order_cancel"),
        ]
        return custom_urls + urls

    class CancelForm(forms.Form):
        _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)
        reason = forms.CharField(widget=forms.Textarea, required=True, max_length=500)

    def action_cancel_order_with_reason(self, request, queryset):
        selected = queryset.values_list("id", flat=True)
        return redirect(f"../cancel/?ids={','.join(str(x) for x in selected)}")

    action_cancel_order_with_reason.short_description = "Cancel selected orders (provide reason)"

    def cancel_view(self, request):
        ids = request.GET.get("ids", "")
        id_list = [s for s in ids.split(",") if s]
        if request.method == "POST":
            form = self.CancelForm(request.POST)
            if form.is_valid():
                reason = form.cleaned_data["reason"]
                cancelled = 0
                from apps.orders.services import OrderService
                for oid in id_list:
                    try:
                        order = Order.objects.get(pk=oid)
                        OrderService.cancel_order(order=order, actor=request.user, reason=reason)
                        cancelled += 1
                    except Exception as exc:
                        self.message_user(request, f"Order {oid}: {exc}", level=messages.ERROR)
                self.message_user(request, f"{cancelled} order(s) cancelled.")
                return redirect("../")
        else:
            form = self.CancelForm(initial={"_selected_action": id_list})
        context = dict(self.admin_site.each_context(request), form=form, ids=ids, title="Cancel orders")
        return TemplateResponse(request, "admin/orders/cancel.html", context)

    @admin.action(description="Confirm delivery for selected orders")
    def action_confirm_delivery(self, request, queryset):
        confirmed = 0
        skipped = 0
        from apps.orders.services import OrderService

        for order in queryset:
            try:
                OrderService.confirm_delivery(order=order, actor=request.user)
                confirmed += 1
            except Exception as exc:
                skipped += 1
                self.message_user(request, f"Order {order.reference}: {exc}")
        self.message_user(request, f"{confirmed} order(s) marked as delivered. {skipped} skipped.")

    @admin.action(description="Complete selected orders (release escrow)")
    def action_complete_order(self, request, queryset):
        completed = 0
        skipped = 0
        from apps.orders.services import OrderService

        for order in queryset:
            try:
                OrderService.complete_order(order=order, actor=request.user)
                completed += 1
            except Exception as exc:
                skipped += 1
                self.message_user(request, f"Order {order.reference}: {exc}")
        self.message_user(request, f"{completed} order(s) completed. {skipped} skipped.")

    @admin.action(description="Cancel selected orders")
    def action_cancel_order(self, request, queryset):
        cancelled = 0
        skipped = 0
        from apps.orders.services import OrderService

        for order in queryset:
            try:
                OrderService.cancel_order(order=order, actor=request.user, reason="Cancelled via admin panel")
                cancelled += 1
            except Exception as exc:
                skipped += 1
                self.message_user(request, f"Order {order.reference}: {exc}")
        self.message_user(request, f"{cancelled} order(s) cancelled. {skipped} skipped.")


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
