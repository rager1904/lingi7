"""
Lingi7 — OCI / Oracle Cloud staging settings.

Production-grade security without external services (S3/Sentry/etc.) so the
full platform can be exercised on a single Oracle instance over plain HTTP.

Differs from dev.py on purpose:
  * DEBUG is always False  (dev.py forces True)
  * Same-origin CORS / trusted origins only
  * Password validators from base.py stay active (dev.py wipes them)
  * Whitenoise serves compiled static files; media is served by Nginx
  * Local filesystem storage (no AWS credentials required)
  * Email falls back to the console backend unless real credentials are set
"""

from decouple import config as env

from .base import *  # noqa: F401, F403

DEBUG = False

# ── HTTPS & Security Headers ──────────────────────────────────────────────────
# We test over plain HTTP on a public IP (no TLS during the 30-day test).
# Flip the two *_COOKIE_SECURE flags to True AND set SECURE_SSL_REDIRECT=True
# once a domain + TLS terminate in front of Nginx.
SECURE_SSL_REDIRECT = False
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")  # Nginx sets this
SESSION_COOKIE_SECURE = False          # would break login over plain HTTP
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = False
CSRF_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# Do NOT enable HSTS while there is no TLS front — a browser would cache the
# header and then refuse to ever load the plain-HTTP site.
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

# ── Storage — local filesystem, served by Nginx at /media/ ──────────────────
DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# ── Whitenoise (static files through Django/gunicorn) ─────────────────────────
MIDDLEWARE = ["whitenoise.middleware.WhiteNoiseMiddleware"] + MIDDLEWARE  # noqa: F405

# ── Email — console unless real credentials are provided ─────────────────────
EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = env("EMAIL_HOST", default="smtp-relay.brevo.com")
EMAIL_PORT = env("EMAIL_PORT", default=587, cast=int)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env("EMAIL_USE_TLS", default=True, cast=bool)

# ── Sentry (optional — leave SENTRY_DSN empty to disable) ────────────────────
SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.redis import RedisIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(transaction_style="url"),
            CeleryIntegration(),
            RedisIntegration(),
        ],
        traces_sample_rate=0.1,
        send_default_pii=False,
        environment="oci",
    )

# ── Rate Limiting ─────────────────────────────────────────────────────────────
REST_FRAMEWORK = {  # noqa: F405
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_RATES": {
        "anon": "30/hour",
        "user": "200/hour",
        "auth": "5/minute",         # login attempts
    },
}

# ── Logging — structured, WARNING in prod-style path ──────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "django.utils.log.ServerFormatter",
            "format": '[{server_time}] {levelname} {name} "{message}"',
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "apps":   {"handlers": ["console"], "level": "INFO", "propagate": False},
        "celery": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}