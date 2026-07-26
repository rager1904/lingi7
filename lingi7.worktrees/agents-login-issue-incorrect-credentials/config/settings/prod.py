"""
Lingi7 — Production Settings
All security headers, HTTPS enforcement, and hardened configuration.
"""

import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.redis import RedisIntegration

from decouple import config as env

from .base import *  # noqa: F401, F403

DEBUG = False

# ── HTTPS & Security Headers ──────────────────────────────────────────────────
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")  # Nginx sets this
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
SECURE_HSTS_SECONDS = 31536000           # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"

# ── Storage — S3 / Cloudflare R2 ─────────────────────────────────────────────
DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY")
AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME")
AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default="af-south-1")
AWS_DEFAULT_ACL = None                   # Bucket policy controls access
AWS_S3_FILE_OVERWRITE = False
AWS_QUERYSTRING_AUTH = True              # Signed URLs for private files (KYC docs)
AWS_QUERYSTRING_EXPIRE = 3600           # 1 hour for signed URLs

# Cloudflare R2 override (uncomment if using R2 instead of S3)
# AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL")

# ── Email ─────────────────────────────────────────────────────────────────────
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST")
EMAIL_PORT = env("EMAIL_PORT", default=587, cast=int)
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = env("EMAIL_USE_TLS", default=True, cast=bool)

# ── Sentry ─────────────────────────────────────────────────────────────────────
SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(transaction_style="url"),
            CeleryIntegration(),
            RedisIntegration(),
        ],
        traces_sample_rate=0.1,      # 10% of requests traced — adjust per volume
        send_default_pii=False,      # Never send PII to Sentry
        environment="production",
    )

# ── Whitenoise (static files) ─────────────────────────────────────────────────
MIDDLEWARE = ["whitenoise.middleware.WhiteNoiseMiddleware"] + MIDDLEWARE  # noqa: F405

# ── Rate Limiting (tighten from base) ────────────────────────────────────────
REST_FRAMEWORK = {  # noqa: F405
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_RATES": {
        "anon": "30/hour",
        "user": "500/hour",
        "auth": "5/minute",         # Login attempts — matches our WAF rule
    },
}

# ── Logging — structured for log aggregation (Loki / ELK) ─────────────────────
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
        "django": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "apps":   {"handlers": ["console"], "level": "INFO",    "propagate": False},
        "celery": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
}
