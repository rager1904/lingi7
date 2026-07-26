# eCommerce Platform Audit

Copyright © 2026 Francis Banda.  
All Rights Reserved.

This platform, source code, architecture, workflows, models, databases, documentation, and all associated intellectual property are proprietary and exclusively owned by Francis Banda.

## Current Architecture

The repository contains three active applications now wired as one platform:

1. `lingi7`: Django REST marketplace backend with PostgreSQL, Redis, Celery, JWT authentication, products, stores, orders, escrow, payments, logistics, disputes, notifications, fraud checks, and React/Vite frontend.
2. `enrichment`: FastAPI catalog enrichment service with image analysis, product field enrichment, policy/manual RAG, FAQ generation, image variation, and 3D asset endpoints.
3. `assistant`: FastAPI shopping assistant stack with chain server, catalog retriever, memory retriever, guardrails, React assistant UI, Milvus vector search, and local OpenAI-compatible model endpoints.

## Integrated Services

- Catalog enrichment is connected to Django vendor products through `CatalogEnrichmentService` and `ExternalCatalogEnrichmentClient`.
- Approved/enriched products are exported into the assistant catalog index through `AssistantCatalogIndexer`.
- Django now exposes `/api/v1/ai/search/`, `/api/v1/ai/recommendations/`, `/api/v1/ai/similar-products/<id>/`, and `/api/v1/ai/assistant/query/`.
- Product search uses catalog retriever semantic search first and database fallback second.
- Recommendations use buyer order history when available and newest visible products as fallback.
- Assistant calls are authenticated through Django JWT and proxied to the local chain server.

## Databases And Indexes

- PostgreSQL remains the system of record for users, products, stores, inventory, orders, escrow, payments, and audit logs.
- Milvus remains the active vector database for assistant catalog retrieval.
- The assistant catalog CSV is now treated as an index feed, not a second source of truth.
- Redis remains the broker/cache for Django and Celery.

## Authentication

- Django SimpleJWT is the unified authentication layer for platform APIs.
- The assistant gateway uses Django `request.user.pk` as the assistant `user_id`, avoiding duplicate assistant identities.
- Standalone assistant services remain internal services behind Django/nginx.

## Issues Found And Fixed

- NVIDIA runtime/container dependencies were removed from root deployment.
- NIM/NVIDIA hosted endpoint defaults were replaced with local Ollama/open-source model settings.
- Catalog enrichment was not connected to marketplace products; it is now called from Django product enrichment.
- Assistant catalog indexing was disconnected from product approval/enrichment; indexing now runs after approval and enrichment changes.
- The unified dashboard only exposed partial integration status; it now reports the open-source AI stack and provider-neutral model status.
- Enrichment UI depended on a bundled NVIDIA Kaizen package; active imports now use a local UI shim.
- Assistant UI loaded NVIDIA-hosted fonts and showed NVIDIA branding; active branding and font calls were removed.

## Remaining Risks

- Full Django runtime checks require installing the Django dependency set in the active Python environment.
- Assistant/enrichment standalone UI builds require local `node_modules`; `react-scripts` and `next` were not installed in this workspace.
- Milvus append indexing should be upgraded to true upsert/delete semantics before very large catalogs.
