"""
Logistics views for Lingi7.

Thin ViewSets — all logic lives in LogisticsService.

Endpoints:
- Public unauthenticated tracking by token
- Vendor shipment management (create, dispatch, update)
- Generic carrier webhook receiver
- Admin shipment management

Reference: LG7-BE-009 | apps/logistics/views.py
"""

from __future__ import annotations

import logging

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.logistics.exceptions import (
    DeliveryAlreadyConfirmedError,
    InvalidShipmentTransitionError,
    LogisticsError,
    ShipmentAlreadyExistsError,
    TrackingNumberRequiredError,
)
from apps.logistics.models import Shipment, TrackingEvent
from apps.logistics.serializers import (
    CarrierWebhookEventSerializer,
    CreateShipmentSerializer,
    DispatchShipmentSerializer,
    PublicShipmentTrackingSerializer,
    ShipmentDetailSerializer,
)
from apps.logistics.services import LogisticsService

logger = logging.getLogger(__name__)


class PublicTrackingView(viewsets.ViewSet):
    """
    Public unauthenticated shipment tracking.

    Accessed via /track/{token}/ — no auth required.
    Uses tracking_token UUID, not the internal PK.
    """

    permission_classes = [AllowAny]

    def retrieve(self, request: Request, token: str) -> Response:
        """
        GET /api/logistics/track/{token}/

        Returns public tracking data for the given token.
        """
        try:
            shipment = (
                Shipment.objects
                .prefetch_related("events")
                .get(tracking_token=token)
            )
        except Shipment.DoesNotExist:
            raise NotFound("Tracking information not found for this reference.")

        serializer = PublicShipmentTrackingSerializer(shipment)
        return Response(serializer.data)


class VendorShipmentViewSet(viewsets.ViewSet):
    """
    Vendor shipment management.

    Vendors create shipment records when they dispatch goods and
    update them with carrier tracking numbers.
    """

    permission_classes = [IsAuthenticated]

    def _get_vendor_order(self, request: Request, order_id: int):
        """Retrieve order belonging to the authenticated vendor."""
        from apps.orders.models import Order  # avoid circular import
        try:
            return Order.objects.get(pk=order_id, seller=request.user)
        except Order.DoesNotExist:
            raise NotFound("Order not found.")

    def create(self, request: Request) -> Response:
        """
        POST /api/logistics/shipments/

        Create a new shipment for an order.
        """
        order_id = request.data.get("order_id")
        if not order_id:
            raise ValidationError({"order_id": "This field is required."})

        order = self._get_vendor_order(request, order_id)

        serializer = CreateShipmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            shipment = LogisticsService.create_shipment(
                order=order,
                created_by=request.user,
                **serializer.validated_data,
            )
        except ShipmentAlreadyExistsError as exc:
            raise ValidationError({"detail": str(exc)})

        return Response(
            ShipmentDetailSerializer(shipment).data,
            status=status.HTTP_201_CREATED,
        )

    def retrieve(self, request: Request, pk: int) -> Response:
        """GET /api/logistics/shipments/{pk}/"""
        try:
            shipment = (
                Shipment.objects
                .prefetch_related("events")
                .get(pk=pk, order__seller=request.user)
            )
        except Shipment.DoesNotExist:
            raise NotFound("Shipment not found.")

        return Response(ShipmentDetailSerializer(shipment).data)

    @action(detail=True, methods=["post"], url_path="dispatch")
    def dispatch(self, request: Request, pk: int) -> Response:
        """
        POST /api/logistics/shipments/{pk}/dispatch/

        Mark shipment as dispatched with carrier tracking number.
        """
        try:
            shipment = Shipment.objects.get(pk=pk, order__seller=request.user)
        except Shipment.DoesNotExist:
            raise NotFound("Shipment not found.")

        serializer = DispatchShipmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            shipment = LogisticsService.mark_dispatched(
                shipment=shipment,
                actor=request.user,
                **serializer.validated_data,
            )
        except (InvalidShipmentTransitionError, TrackingNumberRequiredError) as exc:
            raise ValidationError({"detail": str(exc)})

        return Response(ShipmentDetailSerializer(shipment).data)

    @action(detail=True, methods=["post"], url_path="confirm-delivery")
    def confirm_delivery(self, request: Request, pk: int) -> Response:
        """
        POST /api/logistics/shipments/{pk}/confirm-delivery/

        Buyer confirms receipt of goods. Starts escrow auto-confirm timer.
        """
        # Buyer confirms — check they own the order
        try:
            shipment = Shipment.objects.get(pk=pk, order__buyer=request.user)
        except Shipment.DoesNotExist:
            raise NotFound("Shipment not found.")

        try:
            shipment = LogisticsService.confirm_delivery(
                shipment=shipment,
                actor=request.user,
                confirmed_by="BUYER",
                location="Lusaka, Zambia",
            )
        except (DeliveryAlreadyConfirmedError, InvalidShipmentTransitionError) as exc:
            raise ValidationError({"detail": str(exc)})

        return Response(
            {
                "detail": "Delivery confirmed. Escrow release window has started.",
                "shipment": ShipmentDetailSerializer(shipment).data,
            }
        )


class CarrierWebhookViewSet(viewsets.ViewSet):
    """
    Generic carrier webhook receiver.

    Receives push tracking updates from carriers.
    Signature validation is carrier-specific and handled by middleware
    or within each action.
    """

    permission_classes = [AllowAny]  # Auth via header signature, not session

    def create(self, request: Request) -> Response:
        """
        POST /api/logistics/webhooks/carrier/

        Generic webhook receiver for carriers without dedicated endpoints.
        """
        serializer = CarrierWebhookEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        tracking_number = data["tracking_number"]

        try:
            shipment = Shipment.objects.get(
                carrier_tracking_number=tracking_number,
                carrier=data["carrier"],
            )
        except Shipment.DoesNotExist:
            logger.warning(
                "Carrier webhook: no shipment found for tracking %s carrier %s.",
                tracking_number,
                data["carrier"],
            )
            # Return 200 to prevent carrier retrying endlessly
            return Response({"detail": "Acknowledged."}, status=status.HTTP_200_OK)

        try:
            LogisticsService.ingest_tracking_event(
                shipment=shipment,
                to_status=data["status"],
                description=data["description"],
                location=data.get("location", ""),
                source=TrackingEvent.Source.CARRIER_WEBHOOK,
                raw_payload=data.get("raw_payload"),
                event_timestamp=data.get("event_timestamp"),
            )
        except LogisticsError as exc:
            logger.error(
                "Carrier webhook processing error for Shipment #%s: %s",
                shipment.pk,
                exc,
            )
            # Still return 200 — we've logged the event
            return Response(
                {"detail": "Event logged with errors."},
                status=status.HTTP_200_OK,
            )

        return Response({"detail": "Accepted."}, status=status.HTTP_200_OK)


class AdminShipmentViewSet(viewsets.ModelViewSet):
    """
    Admin full-access shipment management.

    Admin can view all shipments, manually transition status,
    and confirm deliveries.
    """

    permission_classes = [IsAdminUser]
    serializer_class = ShipmentDetailSerializer
    http_method_names = ["get", "post", "put", "patch"]

    def get_queryset(self):
        return (
            Shipment.objects
            .prefetch_related("events")
            .select_related("order", "created_by")
            .order_by("-created_at")
        )

    @action(detail=True, methods=["post"], url_path="transition")
    def transition(self, request: Request, pk=None) -> Response:
        """
        POST /api/admin/logistics/shipments/{pk}/transition/

        Admin manually transitions a shipment to a new status.
        """
        shipment = self.get_object()
        to_status = request.data.get("status")
        description = request.data.get("description", "")
        location = request.data.get("location", "")

        if not to_status:
            raise ValidationError({"status": "This field is required."})

        try:
            shipment = LogisticsService.transition_status(
                shipment=shipment,
                to_status=to_status,
                actor=request.user,
                description=description,
                location=location,
                source=TrackingEvent.Source.ADMIN_MANUAL,
            )
        except (InvalidShipmentTransitionError, TrackingNumberRequiredError) as exc:
            raise ValidationError({"detail": str(exc)})

        return Response(ShipmentDetailSerializer(shipment).data)
