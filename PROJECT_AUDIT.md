Copyright © 2026 Francis Banda.
All Rights Reserved.

This software and all associated intellectual property are proprietary and owned exclusively by Francis Banda.

Unauthorized copying, modification, distribution, sublicensing, resale, reverse engineering, or commercial use is prohibited without explicit written permission from Francis Banda.

# Project Audit

## Executive Summary

The repository contains three applications that are partially integrated by a root `docker-compose.yml` and root `nginx.conf`:

1. `lingi7/`: Django REST Framework marketplace, escrow, payments, logistics, fraud, disputes, notifications, and React/Vite frontend.
2. `enrichment/`: FastAPI catalog enrichment service with product image analysis, product manual extraction, policy RAG, image variation, 3D generation, and a Next.js frontend.
3. `assistant/`: FastAPI/LangGraph shopping assistant with chain server, catalog retriever, memory retriever, guardrails service, and React frontend.

The core integration pattern is viable: Django owns users, permissions, marketplace state, payments, and `/api/v1`; enrichment and assistant remain bounded AI services behind Nginx. The main production gaps are environment hardening, dependency/runtime validation, frontend consolidation, service-to-service authentication, and operational observability.

## Current Architecture

| Area | Current State |
| --- | --- |
| Backend frameworks | Django 4.2/DRF in `lingi7`; FastAPI in `enrichment` and `assistant` microservices |
| Frontend frameworks | Vite/React/TypeScript in `lingi7/frontend`; Next.js in `enrichment/src/ui`; CRA/React in `assistant/ui` |
| Databases | PostgreSQL for Django; Redis for cache/Celery; Milvus with etcd and MinIO for vector search |
| Authentication | Django custom user model with JWT; enrichment and assistant use API keys/config-level trust, not unified user auth |
| Background workers | Celery worker and beat for Django; AI services process requests synchronously/asynchronously inside FastAPI |
| AI services | vLLM LLM/VLM services, BGE embeddings, CLIP embeddings, FLUX image generation, TRELLIS 3D generation, Llama Guard |
| API gateway | Nginx reverse proxy; core API now aligned to `/api/v1/`; AI services exposed at `/api/enrichment/` and `/api/assistant/` |
| CI/CD | No active CI workflow discovered at root |
| Kubernetes | No Kubernetes manifests discovered at root |
| Docker | Root compose orchestrates the unified platform; app-level compose files also exist |

## Implemented During This Audit

- Re-enabled Django health route at `/health/`.
- Aligned root Nginx core API gateway from `/api/lingi7/` to `/api/v1/`.
- Added Nginx `server_tokens off`.
- Updated root API index to advertise `/api/v1/`, `/api/enrichment/`, `/api/assistant/`, and `/health/`.
- Hardened root compose required variables for `POSTGRES_PASSWORD`, `SECRET_KEY`, `API_KEY`, `HF_TOKEN`, and MinIO credentials.
- Fixed root `.env.example` mismatch from `DJANGO_SECRET_KEY` to the actual Django `SECRET_KEY`.
- Removed misleading compose TODO comments for FLUX and TRELLIS custom images.

## Missing Features

- True single frontend: enrichment and assistant still have separate frontends.
- Unified user profile claims propagated to assistant/enrichment.
- Central API gateway policy for authentication, request IDs, rate limits, and service identity.
- Shared notification bus across Django and AI services.
- Central log aggregation and metrics dashboards.
- Automated migration scripts for assistant memory into Django/PostgreSQL.
- CI/CD pipeline and release promotion workflow.

## Broken or Risky Features

- Root was not a Git repository in this workspace, so logical commits could not be created.
- Local Python environment lacks Django, blocking `manage.py check` outside containers.
- Root compose depends on GPU-heavy models and gated Hugging Face downloads; startup requires real credentials and GPU capacity.
- Several files contain mojibake/encoding corruption in comments and docs. This is low functional risk but high maintainability risk.
- The assistant chain server uses permissive CORS (`allow_origins=["*"]`) with credentials enabled.
- Enrichment image upload validation trusts content type and does not enforce image size in `_validate_image`.

## Security Issues

- Previously unsafe default secrets existed in root compose and `.env.example`; root compose now fails fast for required secrets.
- Service-to-service calls need signed internal auth, request IDs, and replay protection.
- AI services should not be public without Django-issued JWT or gateway-issued internal tokens.
- MinIO credentials must be unique per environment and rotated if defaults were ever used.
- Upload endpoints need file size, extension, MIME sniffing, and malware scanning for production.

## Performance Bottlenecks

- GPU model startup and memory requirements dominate platform cost and deploy complexity.
- FastAPI AI endpoints can hold request threads during long-running generation.
- Django product/order pages need query review for `select_related`, `prefetch_related`, and pagination under real data volume.
- Multiple frontends duplicate bundles and user flows.

## Technical Debt

- Three frontend stacks increase build and design-system drift.
- Some AI helper function names still reflect the original vendor blueprint naming and should be renamed in a compatibility-safe cleanup pass.
- Root compose, app compose files, and docs need one canonical deployment path.
- No root-level test orchestration script exists for all three apps.

## Integration Opportunities

- Keep Django as system of record for users, profiles, products, orders, payments, escrow, logistics, disputes, notifications, and audit logs.
- Treat enrichment and assistant as internal AI capability services.
- Use Django `/api/v1/ai/*` proxy endpoints for authenticated user-facing AI requests.
- Store assistant conversations, memory summaries, and enrichment jobs in PostgreSQL with references to Milvus collections and object storage artifacts.
