"""
config/urls.py
==============
Root URL configuration for Lingi7.

API versioning strategy: /api/v1/ prefix on all endpoints.
Admin panel: /admin/ — protected by 2FA middleware.
API docs:    /api/schema/ — OpenAPI spec (disabled in production).
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from apps.core.views import health_check, platform_status

# ── Admin panel customisation ─────────────────────────────────────────────────
admin.site.site_header = "Lingi7 Administration"
admin.site.site_title = "Lingi7 Admin"
admin.site.index_title = "Platform Management"

# ── URL patterns ──────────────────────────────────────────────────────────────
urlpatterns = [
    # Admin
    path("admin/", admin.site.urls),

    # Health check (used by Docker, load balancers, and uptime monitoring)
    path("health/", include("apps.core.urls")),

    # API v1
    path("api/v1/auth/",          include("apps.users.urls")),
    path("api/v1/escrow/",        include("apps.escrow.urls")),
    path("api/v1/payments/",      include("apps.payments.urls")),
    path("api/v1/orders/",        include("apps.orders.urls")),
    path("api/v1/fraud/",         include("apps.fraud.urls")),
    path("api/v1/logistics/",     include("apps.logistics.urls")),
    path("api/v1/disputes/",      include("apps.disputes.urls")),
    path("api/v1/products/",      include("apps.products.urls")),
    path("api/v1/ai/",            include("apps.core.ai_urls")),
    path("api/v1/notifications/", include("apps.notifications.urls")),
    path("api/v1/recommendations/", include("apps.recommendations.urls")),
    path("api/v1/admin/",         include("apps.admin_audit.urls")),
    path("api/v1/platform/",      platform_status, name="platform-status"),
]

# ── OpenAPI docs — only available in non-production ───────────────────────────
if settings.DEBUG:
    urlpatterns += [
        path("api/schema/",          SpectacularAPIView.as_view(),         name="schema"),
        path("api/schema/swagger/",  SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
        path("api/schema/redoc/",    SpectacularRedocView.as_view(url_name="schema"),   name="redoc"),
    ]

# ── Debug toolbar (dev only) ──────────────────────────────────────────────────
if settings.DEBUG:
    try:
        import debug_toolbar
        urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns
    except ImportError:
        pass

# ── Serve media in dev ────────────────────────────────────────────────────────
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
