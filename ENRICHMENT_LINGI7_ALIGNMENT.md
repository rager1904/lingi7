# Enrichment And Lingi7 Backend Alignment

Copyright © 2026 Francis Banda.  
All Rights Reserved.

This platform, source code, architecture, workflows, models, databases, documentation, and all associated intellectual property are proprietary and exclusively owned by Francis Banda.

## Summary

The catalog enrichment app is now aligned behind the Lingi7 backend. The enrichment FastAPI service remains an internal workflow/model service, while browser clients use Django as the authenticated API gateway.

## New Lingi7 API Routes

All routes are under:

```text
/api/v1/products/enrichment-workbench/
```

Routes:

- `POST analyze/`
- `POST faqs/`
- `POST manual/extract/`
- `GET|POST|DELETE policies/`
- `POST generate/variation/`
- `POST generate/3d/`
- `POST protocols/generate/`
- `GET health/services/`

## Product Attachment Flow

1. User opens the enrichment workbench.
2. User optionally enters a Lingi7 product ID.
3. The workbench sends the image and product fields to Django.
4. Django verifies JWT authentication and product ownership.
5. Django forwards the request to the internal enrichment service.
6. If `product_id` was supplied, Django saves the result to the product enrichment fields.
7. Django triggers assistant catalog indexing after the product save commits.

If the product ID does not exist or does not belong to the authenticated vendor, Django returns an error and does not run a silent detached enrichment.

## Frontend Alignment

The enrichment UI now uses:

```text
NEXT_PUBLIC_LINGI7_API_BASE=http://localhost:8000/api/v1
```

It no longer calls `/vlm/*`, `/policies`, `/generate/*`, or `/protocols/*` directly on the enrichment service from the browser.

## Deployment Alignment

- Root `docker-compose.yml` passes `NEXT_PUBLIC_LINGI7_API_BASE=/api/v1`.
- `enrichment/docker-compose.yml` has been replaced with a CPU/open-source standalone layout.
- The unused bundled Kaizen UI package was removed from `enrichment/src/ui`.

## Verification

Passed:

- Python compile for product enrichment service, workbench proxy, and URLs.
- Root Docker Compose config validation.
- Standalone enrichment Docker Compose config validation.
- Targeted scan for NIM/NVIDIA runtime dependency markers in enrichment UI, product backend, and compose files.

Known local limitation:

- The enrichment UI production build still requires installing `next` into `enrichment/src/ui/node_modules`; the current workspace does not have that dependency installed.
