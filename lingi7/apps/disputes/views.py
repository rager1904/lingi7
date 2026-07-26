"""
Dispute Views — apps/disputes/views.py

Thin ViewSets. All business logic lives in DisputeService.
"""

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from .exceptions import DisputeError, DisputeNotOpenError, EvidenceSubmissionClosedError
from .models import Dispute, Evidence
from .serializers import (
    DisputeCreateSerializer,
    DisputeDetailSerializer,
    DisputeListSerializer,
    DisputeResolveSerializer,
    EvidenceCreateSerializer,
    EvidenceSerializer,
)
from apps.users.permissions import IsAdmin

from .services import DisputeService


class DisputeViewSet(viewsets.GenericViewSet):
    """
    Buyer-facing dispute endpoints.

    POST /api/disputes/             — raise_dispute
    GET  /api/disputes/{id}/        — retrieve detail (buyer can only see own)
    GET  /api/disputes/             — list buyer's disputes
    POST /api/disputes/{id}/evidence/ — submit evidence
    POST /api/disputes/{id}/withdraw/ — withdraw dispute
    """

    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            Dispute.objects.filter(raised_by=self.request.user)
            .select_related("order", "raised_by", "assigned_to", "resolved_by")
            .prefetch_related("evidence", "events")
        )

    def list(self, request: Request) -> Response:
        qs = self.get_queryset()
        serializer = DisputeListSerializer(qs, many=True)
        return Response(serializer.data)

    def retrieve(self, request: Request, pk=None) -> Response:
        dispute = self.get_queryset().get(pk=pk)
        serializer = DisputeDetailSerializer(dispute)
        return Response(serializer.data)

    def create(self, request: Request) -> Response:
        serializer = DisputeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from apps.orders.models import Order

        try:
            order = Order.objects.get(
                pk=serializer.validated_data["order"].pk,
                buyer=request.user,
            )
        except Order.DoesNotExist:
            return Response(
                {"detail": "Order not found."}, status=status.HTTP_404_NOT_FOUND
            )

        try:
            dispute = DisputeService.raise_dispute(
                order=order,
                raised_by=request.user,
                reason=serializer.validated_data["reason"],
                description=serializer.validated_data["description"],
            )
        except DisputeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            DisputeDetailSerializer(dispute).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="evidence")
    def submit_evidence(self, request: Request, pk=None) -> Response:
        dispute = self.get_queryset().get(pk=pk)
        serializer = EvidenceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Determine role
        submitted_by_role = Evidence.SubmittedBy.BUYER

        try:
            evidence = DisputeService.submit_evidence(
                dispute=dispute,
                submitted_by=request.user,
                submitted_by_role=submitted_by_role,
                evidence_type=serializer.validated_data["evidence_type"],
                description=serializer.validated_data["description"],
                file=serializer.validated_data.get("file"),
            )
        except EvidenceSubmissionClosedError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except DisputeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(EvidenceSerializer(evidence).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="withdraw")
    def withdraw(self, request: Request, pk=None) -> Response:
        dispute = self.get_queryset().get(pk=pk)
        reason = request.data.get("reason", "")

        try:
            dispute = DisputeService.withdraw_dispute(
                dispute=dispute,
                withdrawn_by=request.user,
                reason=reason,
            )
        except (DisputeError, DisputeNotOpenError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(DisputeDetailSerializer(dispute).data)


class AdminDisputeViewSet(viewsets.GenericViewSet):
    """
    Admin/support agent dispute management endpoints.

    GET  /api/admin/disputes/                    — list all (filterable by status)
    GET  /api/admin/disputes/{id}/               — retrieve detail
    POST /api/admin/disputes/{id}/assign/        — assign to agent
    POST /api/admin/disputes/{id}/resolve-buyer/ — resolve in buyer favour
    POST /api/admin/disputes/{id}/resolve-vendor/ — resolve in vendor favour
    POST /api/admin/disputes/{id}/evidence/      — admin submits evidence
    """

    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def get_queryset(self):
        qs = Dispute.objects.select_related(
            "order", "raised_by", "assigned_to", "resolved_by", "escrow_account"
        ).prefetch_related("evidence", "events")

        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        return qs.order_by("sla_deadline")

    def list(self, request: Request) -> Response:
        qs = self.get_queryset()
        serializer = DisputeListSerializer(qs, many=True)
        return Response(serializer.data)

    def retrieve(self, request: Request, pk=None) -> Response:
        dispute = self.get_queryset().get(pk=pk)
        return Response(DisputeDetailSerializer(dispute).data)

    @action(detail=True, methods=["post"], url_path="assign")
    def assign(self, request: Request, pk=None) -> Response:
        dispute = self.get_queryset().get(pk=pk)
        assigned_to_id = request.data.get("assigned_to")

        from django.contrib.auth import get_user_model
        User = get_user_model()

        try:
            agent = User.objects.get(pk=assigned_to_id, is_staff=True)
        except User.DoesNotExist:
            return Response(
                {"detail": "Staff user not found."}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            dispute = DisputeService.assign_dispute(
                dispute=dispute,
                assigned_to=agent,
                assigned_by=request.user,
            )
        except DisputeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(DisputeDetailSerializer(dispute).data)

    @action(detail=True, methods=["post"], url_path="resolve-buyer")
    def resolve_buyer(self, request: Request, pk=None) -> Response:
        dispute = self.get_queryset().get(pk=pk)
        serializer = DisputeResolveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            dispute = DisputeService.resolve_buyer_favour(
                dispute=dispute,
                resolved_by=request.user,
                resolution_notes=serializer.validated_data["resolution_notes"],
                refund_amount=serializer.validated_data.get("refund_amount"),
            )
        except (DisputeError, DisputeNotOpenError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(DisputeDetailSerializer(dispute).data)

    @action(detail=True, methods=["post"], url_path="resolve-vendor")
    def resolve_vendor(self, request: Request, pk=None) -> Response:
        dispute = self.get_queryset().get(pk=pk)
        serializer = DisputeResolveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            dispute = DisputeService.resolve_vendor_favour(
                dispute=dispute,
                resolved_by=request.user,
                resolution_notes=serializer.validated_data["resolution_notes"],
            )
        except (DisputeError, DisputeNotOpenError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(DisputeDetailSerializer(dispute).data)

    @action(detail=True, methods=["post"], url_path="evidence")
    def submit_evidence(self, request: Request, pk=None) -> Response:
        dispute = self.get_queryset().get(pk=pk)
        serializer = EvidenceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            evidence = DisputeService.submit_evidence(
                dispute=dispute,
                submitted_by=request.user,
                submitted_by_role=Evidence.SubmittedBy.ADMIN,
                evidence_type=serializer.validated_data["evidence_type"],
                description=serializer.validated_data["description"],
                file=serializer.validated_data.get("file"),
            )
        except (EvidenceSubmissionClosedError, DisputeError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(EvidenceSerializer(evidence).data, status=status.HTTP_201_CREATED)


class VendorDisputeViewSet(viewsets.GenericViewSet):
    """
    Vendor-facing dispute endpoints.

    Vendors can view disputes against their orders and submit evidence.
    GET  /api/v1/vendor/disputes/              — list disputes for vendor's orders
    GET  /api/v1/vendor/disputes/{id}/         — retrieve dispute detail
    POST /api/v1/vendor/disputes/{id}/evidence/ — submit vendor evidence
    """

    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            Dispute.objects.filter(order__seller=self.request.user)
            .select_related("order", "raised_by", "assigned_to", "resolved_by")
            .prefetch_related("evidence", "events")
        )

    def list(self, request: Request) -> Response:
        qs = self.get_queryset()
        serializer = DisputeListSerializer(qs, many=True)
        return Response(serializer.data)

    def retrieve(self, request: Request, pk=None) -> Response:
        dispute = self.get_queryset().get(pk=pk)
        serializer = DisputeDetailSerializer(dispute)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="evidence")
    def submit_evidence(self, request: Request, pk=None) -> Response:
        dispute = self.get_queryset().get(pk=pk)
        serializer = EvidenceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            evidence = DisputeService.submit_evidence(
                dispute=dispute,
                submitted_by=request.user,
                submitted_by_role=Evidence.SubmittedBy.VENDOR,
                evidence_type=serializer.validated_data["evidence_type"],
                description=serializer.validated_data["description"],
                file=serializer.validated_data.get("file"),
            )
        except EvidenceSubmissionClosedError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except DisputeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(EvidenceSerializer(evidence).data, status=status.HTTP_201_CREATED)
