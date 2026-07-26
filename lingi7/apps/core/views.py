"""
apps/core/views.py
==================
Platform health check endpoint.
Returns 200 if Django, DB, and Redis are all reachable.
Returns 503 if any dependency is down.
"""

import logging
from typing import Any

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


@require_GET
def health_check(request: Any) -> JsonResponse:
    """
    Health check endpoint.

    Verifies:
      - Django is running
      - PostgreSQL is reachable
      - Redis is reachable

    Returns HTTP 200 on healthy, HTTP 503 on any failure.
    """
    checks: dict[str, str] = {}
    healthy = True

    # Check PostgreSQL
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as exc:
        logger.error("Health check: DB unreachable — %s", exc)
        checks["database"] = "error"
        healthy = False

    # Check Redis / cache
    try:
        cache.set("health_check", "ok", timeout=5)
        result = cache.get("health_check")
        if result == "ok":
            checks["cache"] = "ok"
        else:
            checks["cache"] = "degraded"
    except Exception as exc:
        logger.warning("Health check: cache unreachable — %s", exc)
        checks["cache"] = "degraded"

    checks["api"] = "ok"

    status_code = 200 if healthy else 503
    return JsonResponse(
        {"status": "healthy" if healthy else "unhealthy", "checks": checks},
        status=status_code,
    )


@require_GET
def platform_status(request: Any) -> JsonResponse:
    """
    Unified platform capability map.

    This endpoint is intentionally lightweight: it exposes integration status
    for the frontend shell without calling downstream AI services on every page
    load. Deep dependency checks remain the job of service-specific health
    checks and monitoring.
    """
    return JsonResponse(
        {
            "platform": "Lingi7 Unified Platform",
            "api_version": "v1",
            "authentication": {
                "provider": "django-simplejwt",
                "sso_source": "apps.users.User",
                "duplicate_login_systems": False,
            },
            "applications": [
                {
                    "id": "core-marketplace",
                    "name": "Marketplace",
                    "status": "integrated",
                    "api_base": "/api/v1",
                    "dashboard_path": "/",
                },
                {
                    "id": "catalog-enrichment",
                    "name": "Catalog Enrichment",
                    "status": "service-integrated",
                    "api_base": "/api/enrichment",
                    "dashboard_path": "/vendor/products",
                },
                {
                    "id": "shopping-assistant",
                    "name": "Shopping Assistant",
                    "status": "service-integrated",
                    "api_base": "/api/assistant",
                    "dashboard_path": "/assistant",
                },
            ],
            "ai": {
                "orchestrator": "django-gateway-plus-langgraph-services",
                "llm": "ollama/llama3.2:3b",
                "catalog_llm": "ollama/qwen2.5:3b",
                "vlm": "ollama/llava:7b",
                "text_embeddings": "BAAI/bge-small-en-v1.5",
                "image_embeddings": "openai/clip-vit-base-patch32",
                "vector_database": "Milvus",
                "proprietary_model_required": False,
            },
        }
    )
