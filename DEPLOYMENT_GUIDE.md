Copyright © 2026 Francis Banda.
All Rights Reserved.

This software and all associated intellectual property are proprietary and owned exclusively by Francis Banda.

Unauthorized copying, modification, distribution, sublicensing, resale, reverse engineering, or commercial use is prohibited without explicit written permission from Francis Banda.

# Deployment Guide

## Required Environment Variables

Create a real `.env` file from `.env.example` and set:

| Variable | Required | Purpose |
| --- | --- | --- |
| `API_KEY` | Yes | Internal AI service API key |
| `HF_TOKEN` | Yes | Hugging Face token for gated model downloads |
| `POSTGRES_DB` | Yes | PostgreSQL database name |
| `POSTGRES_USER` | Yes | PostgreSQL username |
| `POSTGRES_PASSWORD` | Yes | PostgreSQL password |
| `SECRET_KEY` | Yes | Django cryptographic secret |
| `MINIO_ROOT_USER` | Yes | MinIO root username |
| `MINIO_ROOT_PASSWORD` | Yes | MinIO root password |

Production also needs domain, storage, email, payment provider, Sentry, and CORS variables from `lingi7/config/settings/prod.py`.

## Local Validation

```powershell
docker compose config --quiet
```

The command should fail if required secrets are missing. That is intentional.

## Development Startup

```powershell
docker compose up -d db redis
docker compose up -d lingi7-web lingi7-celery lingi7-beat nginx
```

Start AI/model services only on machines with appropriate GPU capacity and valid model credentials.

## Production Startup

1. Provision PostgreSQL, Redis, object storage, and GPU capacity.
2. Set all required environment variables in a secret manager.
3. Build images from a clean repository state.
4. Run database migrations.
5. Collect static assets.
6. Start model services and wait for health checks.
7. Start Django, Celery, AI services, frontends, and Nginx.
8. Verify:
   - `/health/`
   - `/api/v1/`
   - `/api/enrichment/health`
   - `/api/assistant/health`

## Health Checks

- Django: `/health/`
- Enrichment: `/api/enrichment/health`
- Assistant: `/api/assistant/health`
- PostgreSQL: `pg_isready`
- Redis: `redis-cli ping`
- Milvus: `/healthz`

## Logging and Monitoring

Minimum production setup:

- Central structured logs for Nginx, Django, Celery, and FastAPI services.
- Request ID propagated from Nginx to every backend.
- Sentry or equivalent for Django and FastAPI exceptions.
- Metrics dashboards for DB, Redis, Celery, Milvus, and GPU model services.

## Rollback

- Keep database migrations reversible where possible.
- Back up PostgreSQL and object storage before releases.
- Do not delete old model artifacts until new model endpoints are verified.
- Use image tags, not `latest`, for production releases.
# eCommerce Deployment Update

Copyright © 2026 Francis Banda.  
All Rights Reserved.

This platform, source code, architecture, workflows, models, databases, documentation, and all associated intellectual property are proprietary and exclusively owned by Francis Banda.

## CPU-Only Deployment

The root Docker Compose deployment is now CPU-first and uses local open-source model services. Required services:

- Django web
- PostgreSQL
- Redis
- Celery worker and beat
- Enrichment backend
- Catalog retriever
- Assistant chain server
- Milvus
- Ollama LLM/VLM services
- Nginx reverse proxy

## Required Environment

Set these before production deployment:

- `SECRET_KEY`
- `DATABASE_URL`
- `POSTGRES_PASSWORD`
- `REDIS_URL`
- `API_KEY` or `LLM_API_KEY` for local OpenAI-compatible services
- `MINIO_ROOT_USER`
- `MINIO_ROOT_PASSWORD`
- `CATALOG_ENRICHMENT_SERVICE_URL`
- `CATALOG_RETRIEVER_URL`
- `ASSISTANT_CHAIN_URL`

## Verification Commands

```powershell
$env:SECRET_KEY='replace-me'
$env:POSTGRES_PASSWORD='replace-me'
$env:MINIO_ROOT_USER='replace-me'
$env:MINIO_ROOT_PASSWORD='replace-me'
$env:API_KEY='ollama'
docker compose config --quiet
```

For Ubuntu/Nginx production, expose public traffic to Nginx and route platform traffic through Django `/api/v1`. Keep model services on the private Docker network.
