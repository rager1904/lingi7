"""
apps/escrow/urls.py

URL patterns for the escrow API.
All endpoints are staff-only (IsAdminUser permission enforced in views).
"""
from __future__ import annotations

from rest_framework.routers import DefaultRouter

from apps.escrow.views import EscrowAccountViewSet, ReconciliationLogViewSet

router = DefaultRouter()
router.register(r"accounts", EscrowAccountViewSet, basename="escrow-account")
router.register(r"reconciliation", ReconciliationLogViewSet, basename="reconciliation-log")

urlpatterns = router.urls
