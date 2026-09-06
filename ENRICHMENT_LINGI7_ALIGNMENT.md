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

The enrichment workbench now runs as a first-class page inside the Lingi7 Vite + React
frontend (the standalone Next.js app under `enrichment/src/ui` has been removed):

```text
Route:  /vendor/enrichment      (auth required, logged-in user)
Entry:  Vendor dashboard → "Enrich listings with AI studio →"
Admin:  Platform dashboard → "Catalog enrichment" card → /vendor/enrichment
```

The page uses the shared app stack — `Vite + React 18 + Tailwind 3`, the shared
authenticated axios `apiClient` (JWT injection + silent refresh), and the
`src/components/enrichment/*` components with the dark studio theme scoped under
`.enrichment-shell` in `src/styles/enrichment.css`.

It no longer calls `/vlm/*`, `/policies`, `/generate/*`, or `/protocols/*` directly on the enrichment service from the browser.

## Security Alignment

The enrichment FastAPI service follows Lingi7's internal-service security model:

- **No public exposure.** nginx no longer proxies `/api/enrichment/` to the
  enrichment backend (the upstream and location blocks were removed; the path
  now returns `404`). The service is reachable only on the internal Docker
  network.
- **Shared internal-service key.** Django sends `settings.INTERNAL_API_KEY` as
  the `X-Internal-Api-Key` header on every call to the enrichment service
  (the workbench proxy and the background `ExternalCatalogEnrichmentClient`).
  The enrichment FastAPI requires this header on all endpoints except `/health`
  (used by the container healthcheck and Colab health probe) and rejects
  requests with `401` when it is missing/invalid, or `503` when the key is not
  configured. Both sides fail closed when `INTERNAL_API_KEY` is unset.
- **Role gate.** `EnrichmentWorkbenchProxy` requires `IsAuthenticated` plus
  `IsVendor` OR `IsAdmin` (vendor workbench; admins may access from the
  platform dashboard). Buyers and anonymous users are denied.
- **Rate limiting.** The workbench routes remain under the `ai` throttle scope
  (`60/hour`).
- The enrichment FastAPI no longer enables browser CORS; it serves the Django
  gateway only.

## Deployment Alignment

- Root `docker-compose.yml` no longer builds an `enrichment-frontend` Next.js container; the workbench is served by the Lingi7 web app.
- nginx no longer proxies `/enrichment/` to `enrichment-frontend:3000` nor
  `/api/enrichment/` to the enrichment backend (those upstreams and location
  blocks have been removed).
- `lingi7/config/urls.py` no longer serves the standalone `enrichment/src/ui/out` build at `/workbench`.
- `enrichment/docker-compose.yml` (standalone local dev) still exists for running the enrichment FastAPI service in isolation; it requires `INTERNAL_API_KEY` for any authenticated call.
- The unused bundled Kaizen UI package was removed from `enrichment/src/ui`; the entire standalone UI package is now removed.

## Verification

Passed:

- Python compile for product enrichment service, workbench proxy, and URLs.
- Root Docker Compose config validation.
- Standalone enrichment Docker Compose config validation.
- Targeted scan for NIM/NVIDIA runtime dependency markers in enrichment UI, product backend, and compose files.

Known local limitation:

- The enrichment studio is only reachable after logging in as a registered user/vendor; it renders full-screen without the marketplace TopBar/Footer chrome.
