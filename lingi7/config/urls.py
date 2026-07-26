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
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from apps.core.views import health_check, platform_status


def _debug_register(request):
    import json
    import traceback
    from django.test.client import Client
    try:
        c = Client()
        r = c.post('/api/v1/auth/register/', data=json.dumps({
            'phone_number': '+260971234599', 'password': 'TestPass123!',
            'password_confirm': 'TestPass123!', 'first_name': 'Test',
            'last_name': 'User', 'consent_given': True
        }), content_type='application/json')
        return JsonResponse({
            'status': r.status_code,
            'body': r.content.decode()[:2000],
        })
    except Exception:
        return JsonResponse({'error': traceback.format_exc()}, status=500)

# ── Admin panel customisation ─────────────────────────────────────────────────
admin.site.site_header = "Lingi7 Administration"
admin.site.site_title = "Lingi7 Admin"
admin.site.index_title = "Platform Management"

# ── URL patterns ──────────────────────────────────────────────────────────────
urlpatterns = [
    # Debug endpoint (temporary)
    path("_debug/register/", _debug_register, name="debug-register"),

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

# ── Colab: serve built frontends through Django ───────────────────────────────
import os
_FRONTEND_DIST = os.path.join(settings.BASE_DIR, "lingi7", "frontend", "dist")
_ENRICHMENT_OUT = os.path.join(settings.BASE_DIR, "enrichment", "src", "ui", "out")

if os.path.isdir(_FRONTEND_DIST):
    from django.http import FileResponse

    def _serve_spa(request, path=""):
        index = os.path.join(_FRONTEND_DIST, "index.html")
        if os.path.exists(index):
            return FileResponse(open(index, "rb"), content_type="text/html")
        return JsonResponse({"error": "Frontend not built"}, status=404)

    # Serve built static assets
    urlpatterns += static("/assets/", document_root=os.path.join(_FRONTEND_DIST, "assets"))
    if os.path.isdir(os.path.join(_FRONTEND_DIST, "design")):
        urlpatterns += static("/design/", document_root=os.path.join(_FRONTEND_DIST, "design"))

    from django.urls import re_path
    urlpatterns += [re_path(r"^(?:store|shop|cart|checkout|wishlist|auth|profile|products)(?:/.*)?$", _serve_spa)]
    urlpatterns += [re_path(r"^$", _serve_spa)]

if os.path.isdir(_ENRICHMENT_OUT):
    def _serve_enrichment(request, path=""):
        index = os.path.join(_ENRICHMENT_OUT, "index.html")
        if os.path.exists(index):
            return FileResponse(open(index, "rb"), content_type="text/html")
        return JsonResponse({"error": "Enrichment UI not built"}, status=404)

    urlpatterns += static("/_next/", document_root=os.path.join(_ENRICHMENT_OUT, "_next"))
    urlpatterns += [re_path(r"^workbench(?:/.*)?$", _serve_enrichment)]
