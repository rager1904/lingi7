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
    PublicStoreViewSet,
    VendorDashboardView,
    VendorProductViewSet,
    VendorStoreViewSet,
)
from apps.products.enrichment import workbench_views

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

public_router = DefaultRouter()
public_router.register("categories", CategoryViewSet, basename="category")
public_router.register("products", PublicProductViewSet, basename="product")
public_router.register("stores", PublicStoreViewSet, basename="public-store")

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
    # Public — /api/v1/products/categories/, /api/v1/products/products/
    path("", include(public_router.urls)),

    # Vendor portal
    path("vendor/", include(vendor_router.urls)),
    path("vendor/dashboard/", VendorDashboardView.as_view(), name="vendor-dashboard"),

    # Authenticated enrichment workbench proxy
    path("enrichment-workbench/analyze/", workbench_views.AnalyzeView.as_view(), name="enrichment-workbench-analyze"),
    path("enrichment-workbench/faqs/", workbench_views.FaqsView.as_view(), name="enrichment-workbench-faqs"),
    path("enrichment-workbench/manual/extract/", workbench_views.ManualExtractView.as_view(), name="enrichment-workbench-manual-extract"),
    path("enrichment-workbench/policies/", workbench_views.PoliciesView.as_view(), name="enrichment-workbench-policies"),
    path("enrichment-workbench/generate/variation/", workbench_views.VariationView.as_view(), name="enrichment-workbench-variation"),
    path("enrichment-workbench/generate/3d/", workbench_views.Generate3DView.as_view(), name="enrichment-workbench-3d"),
    path("enrichment-workbench/protocols/generate/", workbench_views.ProtocolsView.as_view(), name="enrichment-workbench-protocols"),
    path("enrichment-workbench/health/services/", workbench_views.ServicesHealthView.as_view(), name="enrichment-workbench-health"),

    # Admin
    path("admin/", include(admin_router.urls)),
]
