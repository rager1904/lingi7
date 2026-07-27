import re
from urllib.parse import urlparse

from django.conf import settings


class TunnelCsrfMiddleware:
    """Dynamically trusts Cloudflare Tunnel / ngrok style rotating domains.

    Runs BEFORE Django's CsrfViewMiddleware and injects the request's origin
    into CSRF_TRUSTED_ORIGINS so the standard CSRF check passes.
    """

    TRUSTED_PATTERNS = [
        re.compile(r"^https://[a-z0-9-]+\.trycloudflare\.com$", re.IGNORECASE),
        re.compile(r"^https://[a-z0-9-]+\.ngrok-free\.app$", re.IGNORECASE),
        re.compile(r"^https://[a-z0-9-]+\.loca\.lt$", re.IGNORECASE),
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        for header in ("HTTP_ORIGIN", "HTTP_REFERER"):
            raw = request.META.get(header, "")
            if not raw:
                continue
            if header == "HTTP_REFERER":
                parsed = urlparse(raw)
                raw = f"{parsed.scheme}://{parsed.netloc}"
            if any(p.match(raw) for p in self.TRUSTED_PATTERNS):
                if raw not in settings.CSRF_TRUSTED_ORIGINS:
                    settings.CSRF_TRUSTED_ORIGINS.append(raw)
        return self.get_response(request)
