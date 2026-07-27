import re

from django.middleware.csrf import CsrfViewMiddleware


class TunnelCsrfMiddleware(CsrfViewMiddleware):
    """Extends Django CSRF to dynamically trust Cloudflare Tunnel / ngrok
    style rotating domains (*.trycloudflare.com, *.ngrok-free.app, etc.).

    No hard-coded URL needed — any subdomain of the patterns below is
    accepted as a valid origin.
    """

    TRUSTED_TUNNEL_PATTERNS = [
        re.compile(r"^https://[a-z0-9-]+\.trycloudflare\.com$", re.IGNORECASE),
        re.compile(r"^https://[a-z0-9-]+\.ngrok-free\.app$", re.IGNORECASE),
        re.compile(r"^https://[a-z0-9-]+\.loca\.lt$", re.IGNORECASE),
    ]

    def _check_origin(self, origin, request):
        for pattern in self.TRUSTED_TUNNEL_PATTERNS:
            if pattern.match(origin):
                return None  # None = origin is accepted
        return super()._check_origin(origin, request)
