# Catalog Enrichment UI

This is the Lingi7-aligned catalog enrichment workbench. It is a Next.js
frontend that calls the Django API gateway instead of calling the enrichment
FastAPI service directly.

## API Alignment

Set the Lingi7 API base URL at build/runtime:

```bash
NEXT_PUBLIC_LINGI7_API_BASE=http://localhost:8000/api/v1
```

The UI sends requests to:

```text
/api/v1/products/enrichment-workbench/
```

The Django gateway handles JWT authentication, vendor product ownership,
service proxying, persistence, and assistant indexing.

## Product Attachment

The workbench includes an optional Lingi7 product ID field. When supplied,
the analysis result is saved onto that product's enrichment fields and then
indexed into the shopping assistant catalog.

## Development

```bash
pnpm install
pnpm dev
pnpm build
pnpm start
```

## UI Components

Shared layout controls are implemented locally in `ui-kit.tsx`. This keeps the
workbench self-hosted and avoids proprietary UI package dependencies.
