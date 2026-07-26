# Lingi7 Unified Platform Plan

Copyright © 2026 Francis Banda.
All Rights Reserved.

This software and all associated intellectual property are proprietary and owned exclusively by Francis Banda.

Unauthorized copying, modification, distribution, sublicensing, resale, reverse engineering, or commercial use is prohibited without explicit written permission from Francis Banda.

## Current Direction

Lingi7 is consolidated around one Django-owned platform, one `/api/v1` gateway, one JWT identity source, one React/Vite shell, and self-hosted open-source AI services.

## Active Applications

1. `lingi7/`: canonical marketplace, users, roles, products, orders, escrow, payments, fraud, logistics, disputes, notifications, admin audit, and unified frontend.
2. `enrichment/`: internal catalog enrichment service for product metadata, policy checks, product manuals, generated images, and 3D assets.
3. `assistant/`: internal LangGraph shopping assistant service with retrieval, memory, cart routing, and safety checks.

## Runtime Strategy

- Default model serving is CPU-first using Ollama-compatible OpenAI endpoints.
- Default low-resource models:
  - Assistant LLM: `llama3.2:3b`
  - Catalog LLM: `qwen2.5:3b`
  - Vision-language: `llava:7b`
  - Text embeddings: `BAAI/bge-small-en-v1.5`
  - Image embeddings: `openai/clip-vit-base-patch32`
- Milvus remains the selected vector database because it is already integrated with the repository.

## Integration Strategy

- Django remains the source of truth for users, roles, permissions, marketplace data, financial state, notifications, and audit records.
- AI services remain bounded internal services behind the gateway.
- User-facing AI workflows should be accessed through authenticated Django endpoints and surfaced through the unified React dashboard.
- Conversation memory and enrichment job metadata should be stored in PostgreSQL, with vectors/assets referenced by ID.

## Production Priorities

1. Keep the root compose file deployable on CPU-only systems.
2. Route all user-facing APIs through `/api/v1`.
3. Keep one login system and one user table.
4. Add service-to-service authentication for AI backends.
5. Consolidate assistant/enrichment screens into `lingi7/frontend`.
6. Add CI for Python tests, frontend build, compose validation, dependency scanning, and secret scanning.
