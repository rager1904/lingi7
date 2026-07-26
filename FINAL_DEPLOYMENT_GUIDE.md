Copyright © 2026 Francis Banda.
All Rights Reserved.

This software and all associated intellectual property are proprietary and owned exclusively by Francis Banda.

Unauthorized copying, modification, distribution, sublicensing, resale, reverse engineering, or commercial use is prohibited without explicit written permission from Francis Banda.

# Final Deployment Guide

## Environment Targets

Supported:

- CPU-only local development
- Docker deployment
- Ubuntu VPS deployment
- Nginx reverse proxy
- Intel i7 / 16GB RAM low-resource profile

## Required Secrets

Set these before `docker compose up`:

- `API_KEY`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `SECRET_KEY`
- `MINIO_ROOT_USER`
- `MINIO_ROOT_PASSWORD`

Optional:

- `HF_TOKEN` for private/gated Hugging Face downloads
- Payment provider credentials
- Email provider credentials
- Sentry DSN

## Validate Configuration

```powershell
docker compose config --quiet
```

## Start Core Platform

```powershell
docker compose up -d db redis milvus etcd minio
docker compose up -d lingi7-web lingi7-celery lingi7-beat nginx
```

## Start CPU AI Services

```powershell
docker compose up -d llm llm-small vlm llama-guard embeddings image-embeddings
docker exec lingi7-llm ollama pull llama3.2:3b
docker exec lingi7-llm-small ollama pull qwen2.5:3b
docker exec lingi7-vlm ollama pull llava:7b
docker exec lingi7-llama-guard ollama pull llama3.2:3b
```

## Start Application Services

```powershell
docker compose up -d enrichment-backend enrichment-frontend
docker compose up -d catalog-retriever memory-retriever rails chain-server shopping-frontend
```

## Verify

- `GET /health/`
- `GET /api/v1/platform/status/`
- `GET /api/enrichment/health`
- `GET /api/assistant/health`
- Open `/dashboard` after login.

## Production Hardening

- Put real TLS in front of Nginx.
- Enforce service-to-service authentication for AI services.
- Restrict CORS to production domains.
- Configure centralized logs and metrics.
- Run Django migrations before release.
- Run frontend build and backend tests in CI.
- Back up PostgreSQL and object storage before migrations.
