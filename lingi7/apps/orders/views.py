"""
apps/orders/views.py

Thin DRF views. All mutations delegate to OrderService.
"""
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.access import assert_order_party
from apps.orders.models import Order, OrderDispute, OrderServiceError
from apps.orders.serializers import (
    DisputeRaiseSerializer,
    DisputeResolveSerializer,
    OrderCreateSerializer,
    OrderDisputeSerializer,
    OrderSerializer,
    OrderShipInputSerializer,
)
from apps.orders.services import OrderService
from apps.users.permissions import CanTransact, IsAdmin


class OrderListCreateView(APIView):
    permission_classes = [IsAuthenticated, CanTransact]

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsAuthenticated()]
        return super().get_permissions()

    def get(self, request):
        """List orders for the authenticated user (buyer, seller, or both)."""
        role = request.query_params.get("role", "").lower()
        if role == "seller":
            qs = Order.objects.filter(seller=request.user)
        elif role == "buyer":
            qs = Order.objects.filter(buyer=request.user)
        else:
            qs = Order.objects.filter(buyer=request.user) | Order.objects.filter(
                seller=request.user
            )
        qs = qs.select_related("buyer", "seller", "escrow_account", "shipment")
        qs = qs.prefetch_related("lines", "events", "disputes")
        return Response(OrderSerializer(qs.distinct().order_by("-created_at"), many=True).data)

    def post(self, request):
        """Create a DRAFT order."""
        ser = OrderCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        from apps.users.models import User
        try:
            seller = User.objects.get(id=d["seller_id"])
        except User.DoesNotExist:
            raise ValidationError({"seller_id": "Seller not found."})

        try:
            order = OrderService.create_order(
                buyer=request.user,
                seller=seller,
                lines=d["lines"],
                fulfilment_type=d["fulfilment_type"],
                delivery_address=d.get("delivery_address", ""),
                buyer_notes=d.get("buyer_notes", ""),
            )
        except OrderServiceError as exc:
            raise ValidationError({"detail": str(exc)})

        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


class OrderDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_order(self, pk, user):
        order = get_object_or_404(Order, pk=pk)
        if user not in (order.buyer, order.seller) and not user.is_staff:
            raise PermissionDenied()
        return order

    def get(self, request, pk):
        order = self._get_order(pk, request.user)
        return Response(OrderSerializer(order).data)


class OrderSubmitView(APIView):
    permission_classes = [IsAuthenticated, CanTransact]

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk, buyer=request.user)
        try:
            order = OrderService.submit_order(order=order, actor=request.user)
        except OrderServiceError as exc:
            raise ValidationError({"detail": str(exc)})
        return Response(OrderSerializer(order).data)


class OrderAcknowledgeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        try:
            order = OrderService.acknowledge_order(order=order, actor=request.user)
        except OrderServiceError as exc:
            raise ValidationError({"detail": str(exc)})
        return Response(OrderSerializer(order).data)


class OrderShipView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        ser = OrderShipInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        try:
            order = OrderService.ship_order(
                order=order,
                actor=request.user,
                carrier=d["carrier"],
                tracking_number=d.get("tracking_number", ""),
                tracking_url=d.get("tracking_url", ""),
                estimated_delivery=d.get("estimated_delivery"),
                notes=d.get("notes", ""),
            )
        except OrderServiceError as exc:
            raise ValidationError({"detail": str(exc)})
        return Response(OrderSerializer(order).data)


class OrderConfirmDeliveryView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        try:
            order = OrderService.confirm_delivery(order=order, actor=request.user)
        except OrderServiceError as exc:
            raise ValidationError({"detail": str(exc)})
        return Response(OrderSerializer(order).data)


class OrderCompleteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        try:
            order = OrderService.complete_order(order=order, actor=request.user)
        except OrderServiceError as exc:
            raise ValidationError({"detail": str(exc)})
        return Response(OrderSerializer(order).data)


class OrderCancelView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        try:
            assert_order_party(order, request.user)
            order = OrderService.cancel_order(
                order=order, actor=request.user, reason=request.data.get("reason", "")
            )
        except OrderServiceError as exc:
            raise ValidationError({"detail": str(exc)})
        return Response(OrderSerializer(order).data)


class OrderDisputeView(APIView):
    permission_classes = [IsAuthenticated, CanTransact]

    def post(self, request, pk):
        """Raise a dispute on an order."""
        order = get_object_or_404(Order, pk=pk)
        try:
            assert_order_party(order, request.user)
            ser = DisputeRaiseSerializer(data=request.data)
            ser.is_valid(raise_exception=True)
            d = ser.validated_data
            dispute = OrderService.raise_dispute(
                order=order,
                raised_by=request.user,
                reason=d["reason"],
                description=d["description"],
                evidence_urls=d.get("evidence_urls", []),
            )
        except OrderServiceError as exc:
            raise ValidationError({"detail": str(exc)})
        return Response(OrderDisputeSerializer(dispute).data, status=status.HTTP_201_CREATED)


class DisputeResolveView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, dispute_pk):
        """Admin-only: resolve a dispute."""
        dispute = get_object_or_404(OrderDispute, pk=dispute_pk)
        ser = DisputeResolveSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        try:
            dispute = OrderService.resolve_dispute(
                dispute=dispute,
                resolved_by=request.user,
                resolution=d["resolution"],
                resolution_notes=d.get("resolution_notes", ""),
                refund_amount=d.get("refund_amount"),
            )
        except OrderServiceError as exc:
            raise ValidationError({"detail": str(exc)})
        return Response(OrderDisputeSerializer(dispute).data)
