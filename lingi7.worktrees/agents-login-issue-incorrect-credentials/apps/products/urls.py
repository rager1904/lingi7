"""
apps/products/urls.py
=====================
URL configuration for the products app.

Public:
    /api/categories/          — category browsing
    /api/products/            — product catalogue
    /api/products/{slug}/     — product detail

Vendor:
    /api/vendor/store/register/   — store registration
    /api/vendor/store/me/         — own store detail
    /api/vendor/store/update/     — update store profile
    /api/vendor/products/         — manage own listings
    /api/vendor/products/{pk}/images/    — upload image
    /api/vendor/products/{pk}/submit/    — submit for review
    /api/vendor/products/{pk}/archive/   — archive
    /api/vendor/dashboard/        — store KPI dashboard

Admin:
    /api/admin/stores/            — store review queue
    /api/admin/stores/{pk}/approve|reject|suspend/
    /api/admin/products/          — listing review queue
    /api/admin/products/{pk}/approve|reject/
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.products.views import (
    AdminProductViewSet,
    AdminStoreViewSet,
    CategoryViewSet,
    PublicProductViewSet,
    VendorDashboardView,
    VendorProductViewSet,
    VendorStoreViewSet,
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

public_router = DefaultRouter()
public_router.register("categories", CategoryViewSet, basename="category")
public_router.register("products", PublicProductViewSet, basename="product")

vendor_router = DefaultRouter()
vendor_router.register("store", VendorStoreViewSet, basename="vendor-store")
vendor_router.register("products", VendorProductViewSet, basename="vendor-product")

admin_router = DefaultRouter()
admin_router.register("stores", AdminStoreViewSet, basename="admin-store")
admin_router.register("products", AdminProductViewSet, basename="admin-product")

# ---------------------------------------------------------------------------
# URL patterns
# ---------------------------------------------------------------------------

urlpatterns = [
    # Public
    path("api/", include(public_router.urls)),

    # Vendor portal
    path("api/vendor/", include(vendor_router.urls)),
    path("api/vendor/dashboard/", VendorDashboardView.as_view(), name="vendor-dashboard"),

    # Admin
    path("api/admin/", include(admin_router.urls)),
]
