"""
Logistics URL patterns for Lingi7.

Reference: LG7-BE-009 | apps/logistics/urls.py
"""

from django.urls import path

from apps.logistics.views import (
    AdminShipmentViewSet,
    CarrierWebhookViewSet,
    PublicTrackingView,
    VendorShipmentViewSet,
)

# Public unauthenticated tracking
public_tracking = PublicTrackingView.as_view({"get": "retrieve"})

# Vendor shipment management
vendor_list_create = VendorShipmentViewSet.as_view({"post": "create"})
vendor_detail = VendorShipmentViewSet.as_view({"get": "retrieve"})
vendor_dispatch = VendorShipmentViewSet.as_view({"post": "dispatch"})
vendor_confirm_delivery = VendorShipmentViewSet.as_view({"post": "confirm_delivery"})

# Carrier webhooks
carrier_webhook = CarrierWebhookViewSet.as_view({"post": "create"})

# Admin management
admin_list = AdminShipmentViewSet.as_view({"get": "list"})
admin_detail = AdminShipmentViewSet.as_view({"get": "retrieve", "patch": "partial_update"})
admin_transition = AdminShipmentViewSet.as_view({"post": "transition"})

urlpatterns = [
    # Public tracking — no auth
    path("track/<uuid:token>/", public_tracking, name="public-tracking"),

    # Vendor endpoints
    path("shipments/", vendor_list_create, name="vendor-shipment-create"),
    path("shipments/<int:pk>/", vendor_detail, name="vendor-shipment-detail"),
    path("shipments/<int:pk>/dispatch/", vendor_dispatch, name="vendor-shipment-dispatch"),
    path(
        "shipments/<int:pk>/confirm-delivery/",
        vendor_confirm_delivery,
        name="vendor-shipment-confirm-delivery",
    ),

    # Carrier webhooks
    path("webhooks/carrier/", carrier_webhook, name="carrier-webhook"),

    # Admin endpoints
    path("admin/shipments/", admin_list, name="admin-shipment-list"),
    path("admin/shipments/<int:pk>/", admin_detail, name="admin-shipment-detail"),
    path(
        "admin/shipments/<int:pk>/transition/",
        admin_transition,
        name="admin-shipment-transition",
    ),
]
