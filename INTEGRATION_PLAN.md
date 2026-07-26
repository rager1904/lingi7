Copyright © 2026 Francis Banda.
All Rights Reserved.

This software and all associated intellectual property are proprietary and owned exclusively by Francis Banda.

Unauthorized copying, modification, distribution, sublicensing, resale, reverse engineering, or commercial use is prohibited without explicit written permission from Francis Banda.

# Integration Plan

## Recommended Architecture

Use Django as the platform control plane and system of record. Keep enrichment and assistant as internal AI services behind Nginx and, for user-facing flows, behind Django proxy/orchestration endpoints. This preserves working functionality while avoiding a risky full rewrite.

## Phase Plan

1. Stabilize gateway and health checks.
   - Status: initial implementation complete.
   - `/health/` is enabled.
   - `/api/v1/` is routed through Nginx.
   - Compose required secrets now fail fast.

2. Authentication and SSO.
   - Keep Django custom user model and SimpleJWT.
   - Add Django-issued internal service token exchange for enrichment and assistant.
   - Pass `user_id`, role claims, and request ID to AI services.
   - Reject direct unauthenticated browser calls to AI services in production.

3. Unified profiles and permissions.
   - Keep user profile/KYC in `apps.users`.
   - Add permission gates for vendor enrichment, assistant cart actions, order access, and admin AI workflows.
   - Use DRF permissions for every Django-facing AI endpoint.

4. Shared API layer.
   - Standardize envelope:
     - Success: `{ "data": ..., "meta": { "request_id": "..." } }`
     - Error: `{ "error": { "code": "...", "message": "...", "details": ... }, "meta": { "request_id": "..." } }`
   - Preserve existing endpoints for backward compatibility while introducing normalized `/api/v1/ai/*` endpoints.

5. Database strategy.
   - Do not merge AI service transient state directly into core tables.
   - Add Django models for `AIJob`, `EnrichmentResult`, `ConversationSession`, `ConversationMemory`, and `GeneratedAsset`.
   - Store vectors in Milvus and durable relational metadata in PostgreSQL.

6. Frontend integration.
   - Make `lingi7/frontend` the unified shell.
   - Add routes:
     - `/assistant`
     - `/products/:slug/enrich`
     - `/vendor/products/:id/enrichment`
   - Port assistant chat and enrichment forms into shared components gradually.

7. Notifications, logging, and monitoring.
   - Route AI job status changes through Django notifications.
   - Add correlation IDs in Nginx, Django, FastAPI, and Celery.
   - Export app metrics and logs to a central backend.

## Migration Strategy

- First migrate identity and API gateway behavior; do not migrate data until identity mapping is stable.
- Preserve existing Django user IDs as canonical IDs.
- For assistant memory, map old service-level user IDs to Django users through a migration table before writing to `ConversationMemory`.
- For enrichment, backfill existing output files into `GeneratedAsset` rows without moving binary files unless object storage is ready.

## Risks and Tradeoffs

- A single Django-owned identity model reduces auth drift but makes Django a critical dependency for AI UX.
- Keeping AI services separate preserves model/runtime flexibility but requires robust internal auth and tracing.
- Merging all frontends immediately would be high risk; route-level integration first is safer.

## Immediate Implementation Backlog

- Add Django `/api/v1/ai/enrichment/*` and `/api/v1/ai/assistant/*` proxy endpoints.
- Add internal HMAC or JWT service authentication between Django and AI services.
- Add request ID middleware to all apps.
- Add image upload size and magic-byte validation to enrichment.
- Replace permissive assistant CORS with environment-configured origins.
- Create root `Makefile` or script for `check`, `test`, `type-check`, and `compose-config`.
