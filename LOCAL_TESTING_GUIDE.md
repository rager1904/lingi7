# Local Testing Guide

Copyright © 2026 Francis Banda.
All Rights Reserved.

This platform, source code, architecture, workflows, models, databases, documentation, and all associated intellectual property are proprietary and exclusively owned by Francis Banda.

## Integrated Lingi7 + Enrichment Test

Use the root Docker Compose stack when testing the Lingi7 backend and the enrichment workbench together.

```powershell
$env:SECRET_KEY='dev-secret'
$env:POSTGRES_PASSWORD='dev-postgres'
$env:MINIO_ROOT_USER='minioadmin'
$env:MINIO_ROOT_PASSWORD='minioadmin123'
$env:API_KEY='ollama'
docker compose config --quiet
docker compose up -d
```

Open the platform through the configured web gateway. The enrichment frontend is configured to call the Lingi7 API gateway at `/api/v1`, so authenticated enrichment requests go through Lingi7 before reaching the enrichment service.

## Direct Frontend Build Tests

Lingi7 frontend:

```powershell
cd D:\lingi7_scaffold\lingi7\frontend
npm run build
```

Enrichment frontend on Windows:

```powershell
cd D:\lingi7_scaffold\enrichment\src\ui
$env:NEXT_OUTPUT_STANDALONE='false'
cmd /c node_modules\.bin\next.cmd build
```

The `NEXT_OUTPUT_STANDALONE=false` flag is only for local Windows builds that cannot create Next.js standalone symlinks. Docker and Linux builds keep standalone output enabled by default.

## Manual Enrichment Flow

1. Log in through the Lingi7 app so a JWT access token is available to the frontend.
2. Open the enrichment workbench.
3. Optionally enter a Lingi7 product ID before uploading a product image.
4. Run analysis.
5. If a product ID was supplied, Lingi7 validates product ownership, saves the enrichment result to the product, and indexes it for the assistant.

## API Gateway Endpoints

All enrichment UI calls now use the Lingi7 API gateway:

```text
POST   /api/v1/products/enrichment-workbench/analyze/
POST   /api/v1/products/enrichment-workbench/faqs/
POST   /api/v1/products/enrichment-workbench/manual/extract/
GET    /api/v1/products/enrichment-workbench/policies/
POST   /api/v1/products/enrichment-workbench/policies/
DELETE /api/v1/products/enrichment-workbench/policies/
POST   /api/v1/products/enrichment-workbench/generate/variation/
POST   /api/v1/products/enrichment-workbench/generate/3d/
POST   /api/v1/products/enrichment-workbench/protocols/generate/
GET    /api/v1/products/enrichment-workbench/health/services/
```

## Standalone Enrichment Stack

For testing only the enrichment service and UI:

```powershell
$env:API_KEY='ollama'
docker compose -f enrichment\docker-compose.yml config --quiet
docker compose -f enrichment\docker-compose.yml up -d
```

The standalone stack uses open-source CPU-compatible services and does not require NVIDIA infrastructure.
