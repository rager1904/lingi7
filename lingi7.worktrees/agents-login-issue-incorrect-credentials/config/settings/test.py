"""
Lingi7 — Test Settings
Optimised for fast test execution. Never used in any deployed environment.
"""

from .base import *  # noqa: F401, F403

DEBUG = False

# ── Fast password hashing ─────────────────────────────────────────────────────
# MD5 is insecure but bcrypt is slow — use MD5 in tests to save time
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# ── In-memory cache ───────────────────────────────────────────────────────────
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# ── Celery — run tasks synchronously in tests (no worker needed) ──────────────
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True    # Propagate exceptions from eager tasks

# ── Email — capture in memory, don't send ────────────────────────────────────
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# ── Storage — local filesystem, not S3 ───────────────────────────────────────
DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

# ── No rate limiting in tests ─────────────────────────────────────────────────
REST_FRAMEWORK = {  # noqa: F405
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_CLASSES": [],
    "DEFAULT_THROTTLE_RATES": {},
}

# ── Minimal logging in tests ──────────────────────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "handlers": {"null": {"class": "logging.NullHandler"}},
    "root": {"handlers": ["null"]},
}
