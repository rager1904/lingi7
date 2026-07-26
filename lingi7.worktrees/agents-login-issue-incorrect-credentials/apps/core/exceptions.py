"""
apps/core/exceptions.py
========================
Custom DRF exception handler.

Normalises all API error responses into a consistent shape:
  {
    "error": {
      "code": "validation_error",
      "message": "Human-readable summary",
      "detail": { ... }   # field-level errors or string
    }
  }
"""

import logging
from typing import Any

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def lingi7_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """
    Custom exception handler that wraps DRF's default handler output
    into the Lingi7 standard error envelope.
    """
    response = exception_handler(exc, context)

    if response is None:
        # Unhandled exception — let Sentry capture it, return 500
        logger.exception("Unhandled exception in view: %s", context.get("view"))
        return Response(
            {
                "error": {
                    "code": "internal_server_error",
                    "message": "An unexpected error occurred. Our team has been notified.",
                    "detail": None,
                }
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # Map DRF status codes to our error codes
    code_map = {
        400: "validation_error",
        401: "authentication_required",
        403: "permission_denied",
        404: "not_found",
        405: "method_not_allowed",
        429: "rate_limit_exceeded",
    }

    error_code = code_map.get(response.status_code, "api_error")

    # Extract a human-readable message from DRF's response data
    data = response.data
    if isinstance(data, dict):
        message = data.get("detail", "Request could not be completed.")
        if hasattr(message, "code"):
            error_code = message.code
        message = str(message)
        detail = {k: v for k, v in data.items() if k != "detail"} or None
    elif isinstance(data, list):
        message = "Validation failed."
        detail = data
    else:
        message = str(data)
        detail = None

    response.data = {
        "error": {
            "code": error_code,
            "message": message,
            "detail": detail,
        }
    }

    return response
