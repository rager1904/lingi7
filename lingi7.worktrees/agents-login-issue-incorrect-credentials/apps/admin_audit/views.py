"""
apps/admin_audit/views.py
=========================
Thin DRF views for the AdminAuditLog API.

Access is restricted to staff users only (IsAdminUser permission class).
Buyer and vendor roles have no access to this API.

All views are read-only — no POST / PUT / PATCH / DELETE endpoints are
provided.  The audit log is written exclusively via signals + AuditService.
"""

from __future__ import annotations

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, mixins, viewsets
from rest_framework.permissions import IsAdminUser

from .models import AdminAuditLog
from .serializers import AdminAuditLogListSerializer, AdminAuditLogSerializer


class AdminAuditLogViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Read-only ViewSet for the immutable admin audit trail.

    Endpoints:
        GET /api/v1/admin/audit-logs/          — paginated list
        GET /api/v1/admin/audit-logs/<id>/     — single entry detail

    Permissions:
        Staff users only (is_staff=True).

    Filters:
        ?action_type=DELETE
        ?target_content_type=users.user
        ?actor_email=admin@lingi7.com
        ?ordering=-timestamp

    Pagination:
        Default page size 50, max 200.
    """

    queryset = (
        AdminAuditLog.objects.select_related("actor").order_by("-timestamp")
    )
    permission_classes = [IsAdminUser]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = [
        "action_type",
        "target_content_type",
        "actor_email",
    ]
    search_fields = [
        "actor_email",
        "target_object_id",
        "target_repr",
        "ip_address",
    ]
    ordering_fields = ["timestamp", "actor_email", "action_type"]
    ordering = ["-timestamp"]

    def get_serializer_class(self) -> type:
        """Use lightweight serializer for list; full serializer for detail."""
        if self.action == "list":
            return AdminAuditLogListSerializer
        return AdminAuditLogSerializer
