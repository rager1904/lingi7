"""
Lingi7 - Development Settings
Override base settings for local development only.
"""

from .base import *  # noqa: F401, F403

DEBUG = True

# Relax security for local development
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

# Console email - see all emails in terminal without SMTP server
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Storage - local filesystem in dev, not S3
DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

# Relaxed password validation in dev
AUTH_PASSWORD_VALIDATORS = []

# Logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "dev": {
            "format": "[{asctime}] {levelname} {name} - {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "dev",
        },
    },
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "apps":   {"handlers": ["console"], "level": "DEBUG", "propagate": False},
        "celery": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
    },
    "root": {"handlers": ["console"], "level": "DEBUG"},
}
# CACHES inherited from base.py — uses Redis if available, falls back to LocMemCache
