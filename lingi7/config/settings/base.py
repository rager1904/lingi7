"""
Lingi7 — Base Django Settings
==============================
Shared across all environments (dev, prod, test).
Environment-specific settings override these in their own modules.

Never put secrets here. All sensitive values come from environment variables.
"""

import os
from datetime import timedelta
from pathlib import Path

from decouple import Csv, config

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ── Security ──────────────────────────────────────────────────────────────────
SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("DJANGO_ALLOWED_HOSTS", default="localhost", cast=Csv())

# ── Application Definition ────────────────────────────────────────────────────
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "django_celery_beat",
    "django_celery_results",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "drf_spectacular",
    "django_extensions",
]

LOCAL_APPS = [
    "apps.admin_audit",
    "apps.users",
    "apps.escrow",
    "apps.payments",
    "apps.orders",
    "apps.fraud",
    "apps.logistics",
    "apps.disputes",
    "apps.products",
    "apps.notifications",
    "apps.recommendations",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ── Middleware ────────────────────────────────────────────────────────────────
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.admin_audit.middleware.AuditMiddleware",
    "corsheaders.middleware.CorsMiddleware",        # Must be before CommonMiddleware
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",          # 2FA enforcement for admin
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# ── Templates ─────────────────────────────────────────────────────────────────
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ── Database ──────────────────────────────────────────────────────────────────
import dj_database_url  # noqa: E402

_database_url = os.environ.get("DATABASE_URL")
if _database_url and not _database_url.startswith("sqlite"):
    DATABASES = {
        "default": dj_database_url.config(
            env="DATABASE_URL",
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    _db_name = "/content/lingi7/lingi7/db.sqlite3" if os.path.isdir("/content/lingi7") else "db.sqlite3"
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": _db_name,
        }
    }

# Escrow ledger uses a separate PostgreSQL schema for access isolation.
# The escrow service connects as a restricted user that can ONLY write to this schema.
ESCROW_LEDGER_SCHEMA = config("ESCROW_LEDGER_SCHEMA", default="escrow_ledger")

# ── Custom User Model ─────────────────────────────────────────────────────────
AUTH_USER_MODEL = "users.User"

# ── Password Validation ───────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ── Internationalisation ──────────────────────────────────────────────────────
LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Africa/Lusaka"         # Zambia Standard Time (UTC+2, no DST)
USE_I18N = True
USE_TZ = True                       # ALWAYS True — store all datetimes as UTC

# ── Static & Media Files ──────────────────────────────────────────────────────
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SILENCED_SYSTEM_CHECKS = ["staticfiles.W004"]

# ── Django REST Framework ─────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",   # For KYC document uploads
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Throttling — tighten these in prod
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
        "registration": "20/hour",
        "auth": "10/minute",
        "ai": "60/hour",
        "assistant": "30/hour",
    },
    "EXCEPTION_HANDLER": "apps.core.exceptions.lingi7_exception_handler",
}

# ── JWT Configuration ─────────────────────────────────────────────────────────
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=config("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", default=60, cast=int)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=config("JWT_REFRESH_TOKEN_LIFETIME_DAYS", default=7, cast=int)
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,   # Requires token_blacklist app
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# ── Cache (Redis, with LocMem fallback for Colab/dev) ─────────────────────────
_redis_url = config("REDIS_URL", default="redis://localhost:6379/0")
try:
    import socket as _sock
    _host, _port = _redis_url.replace("redis://", "").split(":")[0], int(_redis_url.split(":")[-1].split("/")[0])
    _sock.create_connection((_host, _port), timeout=1)
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": _redis_url,
            "KEY_PREFIX": "lingi7",
            "TIMEOUT": 300,
        }
    }
except Exception:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "lingi7-locmem",
            "TIMEOUT": 300,
        }
    }

# ── Sessions ──────────────────────────────────────────────────────────────────
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"

# ── Celery ────────────────────────────────────────────────────────────────────
CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="redis://localhost:6379/1")
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default="redis://localhost:6379/2")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Africa/Lusaka"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 300            # Hard kill after 5 minutes
CELERY_TASK_SOFT_TIME_LIMIT = 240       # Graceful shutdown after 4 minutes
CELERY_WORKER_PREFETCH_MULTIPLIER = 1   # Prevents one worker hoarding tasks
CELERY_TASK_ACKS_LATE = True            # Task acknowledged only after completion
CELERY_TASK_REJECT_ON_WORKER_LOST = True

# Named queues — route critical financial tasks away from general queue
CELERY_TASK_ROUTES = {
    "apps.escrow.tasks.*":        {"queue": "default"},
    "apps.products.tasks.*":      {"queue": "default"},
    "apps.payments.tasks.*":      {"queue": "payments"},
    "apps.notifications.tasks.*": {"queue": "notifications"},
    "apps.fraud.tasks.*":         {"queue": "fraud"},
}

# Beat schedule — populated by django_celery_beat via admin/migrations
# Do not define static schedule here; use the DB-backed scheduler.
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# ── Email ─────────────────────────────────────────────────────────────────────
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="noreply@lingi7.co.zm")
SERVER_EMAIL = config("SERVER_EMAIL", default="noreply@lingi7.co.zm")

# ── CORS ──────────────────────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = config("CORS_ALLOWED_ORIGINS", default="http://localhost:3000", cast=Csv())
CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="http://localhost:8000", cast=Csv())

# ── OpenAPI / Spectacular ─────────────────────────────────────────────────────
SPECTACULAR_SETTINGS = {
    "TITLE": "Lingi7 API",
    "DESCRIPTION": "Fintech-grade escrow and AI-powered e-commerce platform for Zambia.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

# ── Logging ───────────────────────────────────────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} {process:d} {thread:d} — {message}",
            "style": "{",
        },
        "simple": {
            "format": "[{asctime}] {levelname} {name} — {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        # Our application namespaces — always log at DEBUG in dev
        "apps": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
        # Celery task logs
        "celery": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
}

# ── Platform-specific Settings ────────────────────────────────────────────────
# MTN MoMo
MTN_MOMO_BASE_URL = config("MTN_MOMO_BASE_URL", default="https://sandbox.momodeveloper.mtn.com")
MTN_MOMO_SUBSCRIPTION_KEY = config("MTN_MOMO_SUBSCRIPTION_KEY", default="")
MTN_MOMO_COLLECTION_USER_ID = config("MTN_MOMO_COLLECTION_USER_ID", default="")
MTN_MOMO_COLLECTION_API_KEY = config("MTN_MOMO_COLLECTION_API_KEY", default="")
MTN_MOMO_DISBURSEMENT_USER_ID = config("MTN_MOMO_DISBURSEMENT_USER_ID", default="")
MTN_MOMO_DISBURSEMENT_API_KEY = config("MTN_MOMO_DISBURSEMENT_API_KEY", default="")
MTN_MOMO_ENVIRONMENT = config("MTN_MOMO_ENVIRONMENT", default="sandbox")
MTN_MOMO_CURRENCY = config("MTN_MOMO_CURRENCY", default="ZMW")
MTN_MOMO_CALLBACK_URL = config("MTN_MOMO_CALLBACK_URL", default="")

# Airtel Money
AIRTEL_BASE_URL = config("AIRTEL_BASE_URL", default="https://openapiuat.airtel.africa")
AIRTEL_CLIENT_ID = config("AIRTEL_CLIENT_ID", default="")
AIRTEL_CLIENT_SECRET = config("AIRTEL_CLIENT_SECRET", default="")
AIRTEL_ENVIRONMENT = config("AIRTEL_ENVIRONMENT", default="staging")
AIRTEL_CURRENCY = config("AIRTEL_CURRENCY", default="ZMW")
AIRTEL_COUNTRY = config("AIRTEL_COUNTRY", default="ZM")

# Fraud engine
ML_FRAUD_MODEL_PATH = config("ML_FRAUD_MODEL_PATH", default="ml/fraud/models/fraud_model_v1.joblib")
ML_FRAUD_SCORE_THRESHOLD = config("ML_FRAUD_SCORE_THRESHOLD", default=0.65, cast=float)

# Internal service API key (for fraud scoring endpoint)
INTERNAL_API_KEY = config("INTERNAL_API_KEY", default="")

# Maximum upload size (10 MB) — enforced in serializers + upload validators
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# Catalog enrichment (Ollama-compatible LLM / VLM)
CATALOG_ENRICHMENT_ENABLED = config("CATALOG_ENRICHMENT_ENABLED", default=True, cast=bool)
CATALOG_LLM_BASE_URL = config("CATALOG_LLM_BASE_URL", default="http://localhost:11434")
CATALOG_LLM_MODEL = config("CATALOG_LLM_MODEL", default="qwen2.5:3b")
CATALOG_VLM_MODEL = config("CATALOG_VLM_MODEL", default="llava:7b")
CATALOG_AUTO_ENRICH_ON_IMAGE = config("CATALOG_AUTO_ENRICH_ON_IMAGE", default=True, cast=bool)
CATALOG_ENRICHMENT_SERVICE_URL = config(
    "CATALOG_ENRICHMENT_SERVICE_URL",
    default="http://enrichment-backend:8000",
)
CATALOG_ENRICHMENT_SERVICE_TIMEOUT = config(
    "CATALOG_ENRICHMENT_SERVICE_TIMEOUT",
    default=45,
    cast=int,
)
ASSISTANT_CATALOG_INDEXING_ENABLED = config(
    "ASSISTANT_CATALOG_INDEXING_ENABLED",
    default=True,
    cast=bool,
)
ASSISTANT_CATALOG_CSV_PATH = config(
    "ASSISTANT_CATALOG_CSV_PATH",
    default=str(BASE_DIR.parent / "assistant" / "shared" / "data" / "products_extended.csv"),
)
CATALOG_RETRIEVER_URL = config(
    "CATALOG_RETRIEVER_URL",
    default="http://catalog-retriever:8010",
)
CATALOG_RETRIEVER_TIMEOUT = config("CATALOG_RETRIEVER_TIMEOUT", default=20, cast=int)
ASSISTANT_CHAIN_URL = config("ASSISTANT_CHAIN_URL", default="http://chain-server:8009")
ASSISTANT_CHAIN_TIMEOUT = config("ASSISTANT_CHAIN_TIMEOUT", default=30, cast=int)
