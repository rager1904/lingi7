"""
apps/admin_audit/urls.py
========================
URL configuration for the admin_audit app.

Mount under /api/v1/admin/ in the project root urls.py::

    path("api/v1/admin/", include("apps.admin_audit.urls")),
"""

from __future__ import annotations

from rest_framework.routers import DefaultRouter

from .views import AdminAuditLogViewSet

router = DefaultRouter()
router.register(r"audit-logs", AdminAuditLogViewSet, basename="audit-log")

urlpatterns = router.urls
