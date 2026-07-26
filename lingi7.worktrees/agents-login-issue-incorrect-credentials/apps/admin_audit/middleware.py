"""
apps/admin_audit/middleware.py
==============================
AuditMiddleware — attaches the current Django request to a thread-local
so that signal handlers in signals.py can access the request context
(IP address, authenticated user, session key) without requiring the
request to be passed explicitly through the ORM call chain.

Placement
---------
This middleware MUST be placed early in ``MIDDLEWARE`` in settings.py —
before ``AuthenticationMiddleware`` is fine, but it must precede any
middleware that performs database writes (e.g. session middleware).

Recommended order::

    MIDDLEWARE = [
        "django.middleware.security.SecurityMiddleware",
        "apps.admin_audit.middleware.AuditMiddleware",   # ← here
        "django.contrib.sessions.middleware.SessionMiddleware",
        ...
    ]

Thread safety
-------------
``set_current_request`` writes to a threading.local(), which is
per-thread and therefore safe under WSGI (Gunicorn sync/gevent workers)
and ASGI (Uvicorn).  The request reference is cleared in the ``finally``
block even if the view raises an exception.
"""

from __future__ import annotations

from typing import Callable

from django.http import HttpRequest, HttpResponse

from .signals import set_current_request


class AuditMiddleware:
    """WSGI-compatible middleware that stashes the request on a thread-local.

    This enables signal handlers to access request metadata (actor, IP,
    session) without any change to the view layer.

    Args:
        get_response: The next middleware or view in the chain.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Process a single HTTP request.

        Stashes *request* on the thread-local before calling downstream
        handlers, and clears it afterwards — even if an exception is raised.

        Args:
            request: The incoming Django HttpRequest.

        Returns:
            The HttpResponse from downstream middleware / view.
        """
        set_current_request(request)
        try:
            response = self.get_response(request)
        finally:
            # Always clear — prevents stale request leaking to the next
            # request on a recycled thread in a threaded WSGI server.
            set_current_request(None)
        return response
