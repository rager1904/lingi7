"""
Logistics serializers for Lingi7.

Public tracking serializers are intentionally minimal — they expose
only what a buyer needs to see without leaking internal references.

Reference: LG7-BE-009 | apps/logistics/serializers.py
"""

from __future__ import annotations

from rest_framework import serializers

from apps.logistics.models import Shipment, TrackingEvent


class TrackingEventSerializer(serializers.ModelSerializer):
    """Read-only serializer for a single tracking event."""

    class Meta:
        model = TrackingEvent
        fields = [
            "status",
            "description",
            "location",
            "event_timestamp",
        ]
        # raw_payload and source are internal — never expose publicly


class PublicShipmentTrackingSerializer(serializers.ModelSerializer):
    """
    Public-facing tracking serializer.

    Accessed via /track/{tracking_token}/ — no authentication required.
    Deliberately excludes internal references (order ID, actor data).
    """

    events = TrackingEventSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    shipping_method_display = serializers.CharField(
        source="get_shipping_method_display", read_only=True
    )

    class Meta:
        model = Shipment
        fields = [
            "tracking_token",
            "carrier",
            "carrier_tracking_number",
            "shipping_method",
            "shipping_method_display",
            "status",
            "status_display",
            "origin_country",
            "destination_country",
            "estimated_delivery_date",
            "delivered_at",
            "events",
        ]


class ShipmentDetailSerializer(serializers.ModelSerializer):
    """
    Full shipment detail for authenticated vendor/admin use.

    Includes internal fields hidden from the public tracking page.
    """

    events = TrackingEventSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Shipment
        fields = [
            "id",
            "tracking_token",
            "order",
            "carrier",
            "carrier_tracking_number",
            "shipping_method",
            "status",
            "status_display",
            "origin_country",
            "origin_address",
            "destination_country",
            "destination_address",
            "freight_forwarder",
            "customs_agent",
            "last_mile_courier",
            "weight_kg",
            "volume_cbm",
            "declared_value_usd",
            "duty_paid_zmw",
            "estimated_delivery_date",
            "delivered_at",
            "delivery_confirmed_by",
            "warehouse_received_at",
            "warehouse_dispatched_at",
            "last_carrier_poll_at",
            "created_at",
            "updated_at",
            "events",
        ]
        read_only_fields = [
            "id",
            "tracking_token",
            "status",
            "delivered_at",
            "delivery_confirmed_by",
            "last_carrier_poll_at",
            "created_at",
            "updated_at",
        ]


class CreateShipmentSerializer(serializers.Serializer):
    """
    Input serializer for creating a new shipment.

    Vendor submits this when they mark an order as shipped.
    """

    carrier = serializers.ChoiceField(
        choices=Shipment.CarrierCode.choices,
        default=Shipment.CarrierCode.GENERIC,
    )
    carrier_tracking_number = serializers.CharField(
        max_length=100, required=False, allow_blank=True, default=""
    )
    shipping_method = serializers.ChoiceField(
        choices=Shipment.ShippingMethod.choices,
        default=Shipment.ShippingMethod.AIR,
    )
    origin_address = serializers.CharField(max_length=500, required=False, allow_blank=True)
    destination_address = serializers.CharField(max_length=500, required=False, allow_blank=True)
    freight_forwarder = serializers.CharField(max_length=120, required=False, allow_blank=True)
    customs_agent = serializers.CharField(max_length=120, required=False, allow_blank=True)
    estimated_delivery_date = serializers.DateField(required=False, allow_null=True)
    declared_value_usd = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    weight_kg = serializers.DecimalField(
        max_digits=8, decimal_places=3, required=False, allow_null=True
    )
    volume_cbm = serializers.DecimalField(
        max_digits=8, decimal_places=4, required=False, allow_null=True
    )


class DispatchShipmentSerializer(serializers.Serializer):
    """Input for marking a shipment as dispatched with tracking number."""

    carrier_tracking_number = serializers.CharField(max_length=100)
    carrier = serializers.ChoiceField(
        choices=Shipment.CarrierCode.choices, required=False, allow_blank=True
    )
    freight_forwarder = serializers.CharField(
        max_length=120, required=False, allow_blank=True
    )
    location = serializers.CharField(max_length=200, required=False, allow_blank=True)


class CarrierWebhookEventSerializer(serializers.Serializer):
    """
    Generic carrier webhook event payload.

    Used by the generic webhook receiver. Carrier-specific receivers
    use their own serializers and normalise to this shape.
    """

    carrier = serializers.ChoiceField(choices=Shipment.CarrierCode.choices)
    tracking_number = serializers.CharField(max_length=100)
    status = serializers.ChoiceField(choices=Shipment.Status.choices)
    description = serializers.CharField(max_length=500)
    location = serializers.CharField(max_length=200, required=False, allow_blank=True)
    event_timestamp = serializers.DateTimeField(required=False)
    raw_payload = serializers.JSONField(required=False, allow_null=True)
