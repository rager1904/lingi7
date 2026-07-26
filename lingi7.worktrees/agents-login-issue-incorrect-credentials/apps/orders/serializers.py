"""
apps/orders/serializers.py

DRF serializers for the orders app.
All write operations go through OrderService — serializers are read/validate only.
"""
from decimal import Decimal

from rest_framework import serializers

from apps.orders.constants import (
    DisputeReason,
    DisputeResolution,
    FulfilmentType,
    OrderStatus,
)
from apps.orders.models import (
    Order,
    OrderDispute,
    OrderEvent,
    OrderLine,
    OrderShipment,
)


class OrderLineSerializer(serializers.ModelSerializer):
    line_total = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )

    class Meta:
        model = OrderLine
        fields = [
            "id", "product_id", "product_name", "product_sku",
            "unit_price", "quantity", "currency", "line_total",
        ]
        read_only_fields = fields


class OrderLineCreateSerializer(serializers.Serializer):
    product_name = serializers.CharField(max_length=255)
    product_id   = serializers.CharField(max_length=100, required=False, default="")
    product_sku  = serializers.CharField(max_length=100, required=False, default="")
    unit_price   = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    quantity     = serializers.IntegerField(min_value=1, default=1)


class OrderEventSerializer(serializers.ModelSerializer):
    triggered_by_id = serializers.UUIDField(source="triggered_by.id", read_only=True)

    class Meta:
        model = OrderEvent
        fields = [
            "id", "from_status", "to_status",
            "triggered_by_id", "note", "created_at", "metadata",
        ]
        read_only_fields = fields


class OrderShipmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderShipment
        fields = [
            "id", "carrier", "tracking_number", "tracking_url",
            "estimated_delivery", "shipped_at", "notes",
        ]
        read_only_fields = fields


class OrderDisputeSerializer(serializers.ModelSerializer):
    raised_by_id  = serializers.UUIDField(source="raised_by.id", read_only=True)
    resolved_by_id = serializers.UUIDField(source="resolved_by.id", read_only=True, allow_null=True)

    class Meta:
        model = OrderDispute
        fields = [
            "id", "reason", "description", "evidence_urls",
            "raised_by_id", "resolved_by_id", "resolution",
            "resolution_notes", "refund_amount", "resolved_at",
            "created_at", "is_open",
        ]
        read_only_fields = fields


class OrderSerializer(serializers.ModelSerializer):
    lines     = OrderLineSerializer(many=True, read_only=True)
    events    = OrderEventSerializer(many=True, read_only=True)
    shipment  = OrderShipmentSerializer(read_only=True)
    disputes  = OrderDisputeSerializer(many=True, read_only=True)
    buyer_id  = serializers.UUIDField(source="buyer.id", read_only=True)
    seller_id = serializers.UUIDField(source="seller.id", read_only=True)

    class Meta:
        model = Order
        fields = [
            "id", "reference", "status",
            "buyer_id", "seller_id",
            "subtotal", "platform_fee", "total_amount", "currency",
            "fulfilment_type", "delivery_address", "buyer_notes",
            "created_at", "submitted_at", "paid_at", "completed_at", "cancelled_at",
            "lines", "events", "shipment", "disputes",
        ]
        read_only_fields = fields


class OrderCreateSerializer(serializers.Serializer):
    seller_id        = serializers.UUIDField()
    lines            = OrderLineCreateSerializer(many=True, min_length=1)
    fulfilment_type  = serializers.ChoiceField(
        choices=FulfilmentType.CHOICES,
        default=FulfilmentType.STANDARD_DELIVERY,
    )
    delivery_address = serializers.CharField(required=False, default="", allow_blank=True)
    buyer_notes      = serializers.CharField(required=False, default="", allow_blank=True)


class OrderShipInputSerializer(serializers.Serializer):
    carrier            = serializers.CharField(max_length=100)
    tracking_number    = serializers.CharField(max_length=200, required=False, default="", allow_blank=True)
    tracking_url       = serializers.URLField(required=False, default="", allow_blank=True)
    estimated_delivery = serializers.DateField(required=False, allow_null=True)
    notes              = serializers.CharField(required=False, default="", allow_blank=True)


class DisputeRaiseSerializer(serializers.Serializer):
    reason        = serializers.ChoiceField(choices=DisputeReason.CHOICES)
    description   = serializers.CharField(min_length=20)
    evidence_urls = serializers.ListField(
        child=serializers.URLField(), required=False, default=list
    )


class DisputeResolveSerializer(serializers.Serializer):
    resolution       = serializers.ChoiceField(choices=DisputeResolution.CHOICES)
    resolution_notes = serializers.CharField(required=False, default="", allow_blank=True)
    refund_amount    = serializers.DecimalField(
        max_digits=14, decimal_places=2,
        required=False, allow_null=True, min_value=Decimal("0.01"),
    )
