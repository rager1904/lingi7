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

    # Check Redis
    try:
        cache.set("health_check", "ok", timeout=5)
        result = cache.get("health_check")
        if result == "ok":
            checks["cache"] = "ok"
        else:
            checks["cache"] = "error"
            healthy = False
    except Exception as exc:
        logger.error("Health check: Redis unreachable — %s", exc)
        checks["cache"] = "error"
        healthy = False

    checks["api"] = "ok"

    status_code = 200 if healthy else 503
    return JsonResponse(
        {"status": "healthy" if healthy else "unhealthy", "checks": checks},
        status=status_code,
    )
