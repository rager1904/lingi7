"""
Dispute URL routing — apps/disputes/urls.py
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AdminDisputeViewSet, DisputeViewSet, VendorDisputeViewSet

router = DefaultRouter()
router.register(r"disputes", DisputeViewSet, basename="dispute")
router.register(r"admin/disputes", AdminDisputeViewSet, basename="admin-dispute")
router.register(r"vendor/disputes", VendorDisputeViewSet, basename="vendor-dispute")

urlpatterns = [
    path("api/", include(router.urls)),
]
