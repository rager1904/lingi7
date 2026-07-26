# ─────────────────────────────────────────────────────────────────────────────
# Lingi7 — Multi-stage Dockerfile
# Stage 1: builder  — installs Python dependencies into a virtual environment
# Stage 2: runtime  — lean image, copies only the venv and app code
#
# Never build with secrets or .env files included — all config via env vars.
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

# Prevent Python from writing .pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies required to compile Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create and activate a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies — base + prod layers only
COPY requirements/base.txt requirements/base.txt
COPY requirements/prod.txt requirements/prod.txt
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements/base.txt \
    && pip install --no-cache-dir -r requirements/prod.txt


# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE="config.settings.prod"

WORKDIR /app

# Install runtime-only system libraries (libpq for psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application source — do this last to maximise layer caching
COPY . .

# Create a non-root user for running the application
RUN groupadd --gid 1001 lingi7 \
    && useradd --uid 1001 --gid lingi7 --shell /bin/bash --create-home lingi7 \
    && chown -R lingi7:lingi7 /app

USER lingi7

# Collect static files at build time
RUN python manage.py collectstatic --noinput

EXPOSE 8000

# Gunicorn: 2-4 workers per CPU core is the standard rule of thumb for Django
# Adjust --workers based on your VPS CPU count
CMD ["gunicorn", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--worker-class", "sync", \
     "--worker-connections", "1000", \
     "--timeout", "60", \
     "--keepalive", "5", \
     "--max-requests", "1000", \
     "--max-requests-jitter", "100", \
     "--log-level", "info", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "config.wsgi:application"]
