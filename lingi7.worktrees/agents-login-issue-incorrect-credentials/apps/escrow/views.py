"""
apps/escrow/views.py

Staff-only read-only ViewSets for escrow account inspection.

Escrow state cannot be mutated via API endpoints — all transitions
go through EscrowService, triggered by:
  - Payment webhooks (apps/payments/)
  - Logistics events (apps/logistics/)
  - Admin actions (admin.py in this app)
  - Celery tasks (tasks.py in this app)
  - Dispute resolution (apps/disputes/)
"""
from __future__ import annotations

from rest_framework import filters, mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser
from rest_framework.request import Request
from rest_framework.response import Response

from apps.escrow.models import EscrowAccount, ReconciliationLog
from apps.escrow.serializers import (
    EscrowAccountListSerializer,
    EscrowAccountSerializer,
    ReconciliationLogSerializer,
)
from apps.escrow.state_machine import EscrowState


class EscrowAccountViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """
    Read-only admin ViewSet for EscrowAccount inspection.

    Filtering:
        ?state=FROZEN         — accounts in a specific state
        ?order_ref=<uuid>     — look up by order reference

    Actions:
        GET /escrow/accounts/               — paginated list
        GET /escrow/accounts/{id}/          — detail with ledger entries
        GET /escrow/accounts/frozen/        — shortcut: all FROZEN accounts
    """

    permission_classes = [IsAdminUser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["order_ref", "buyer_ref", "vendor_ref"]
    ordering_fields = ["created_at", "updated_at", "balance", "state"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = EscrowAccount.objects.select_related("hold").prefetch_related(
            "ledger_entries", "fraud_gate_logs"
        )
        state = self.request.query_params.get("state")
        if state and state in EscrowState.ALL:
            qs = qs.filter(state=state)
        order_ref = self.request.query_params.get("order_ref")
        if order_ref:
            qs = qs.filter(order_ref=order_ref)
        return qs

    def get_serializer_class(self):
        if self.action == "retrieve":
            return EscrowAccountSerializer
        return EscrowAccountListSerializer

    @action(detail=False, methods=["get"], url_path="frozen")
    def frozen(self, request: Request) -> Response:
        """Return all accounts currently in FROZEN state (manual review queue)."""
        qs = EscrowAccount.objects.filter(state=EscrowState.FROZEN).order_by("frozen_at")
        serializer = EscrowAccountListSerializer(qs, many=True)
        return Response({"count": qs.count(), "results": serializer.data})


class ReconciliationLogViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """
    Read-only admin ViewSet for nightly reconciliation run history.

    GET /escrow/reconciliation/         — paginated list, latest first
    GET /escrow/reconciliation/{id}/    — detail for a specific run
    """

    permission_classes = [IsAdminUser]
    serializer_class = ReconciliationLogSerializer
    queryset = ReconciliationLog.objects.all().order_by("-run_at")
    ordering_fields = ["run_at", "status"]
