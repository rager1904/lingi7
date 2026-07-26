Copyright © 2026 Francis Banda.
All Rights Reserved.

This software and all associated intellectual property are proprietary and owned exclusively by Francis Banda.

Unauthorized copying, modification, distribution, sublicensing, resale, reverse engineering, or commercial use is prohibited without explicit written permission from Francis Banda.

# Database Migration Plan

## Current Databases

| Store | Current Owner | Purpose | Decision |
| --- | --- | --- | --- |
| PostgreSQL | Django | Users, marketplace data, payments, escrow, logistics, disputes, notifications, audit | Canonical relational store |
| Redis | Django/Celery | Cache, sessions, Celery broker/results | Keep |
| Milvus | Assistant/enrichment | Product, policy, text, and image vector retrieval | Keep because already integrated |
| MinIO | Milvus | Object storage backend for Milvus | Keep for local compose; use S3-compatible storage in production |
| SQLite policy library files | Enrichment | Local policy document metadata | Migrate metadata to PostgreSQL later; keep file path compatibility during transition |
| Memory retriever volume | Assistant | Conversation/cart memory | Migrate durable user memory to PostgreSQL |

## Shared Entities

| Entity | Canonical Table/App | Migration Action |
| --- | --- | --- |
| User | `apps.users.User` | Preserve UUIDs and roles |
| Role/permissions | `apps.users`, Django groups/permissions | Extend, do not duplicate |
| Product | `apps.products` | Enrichment results reference products |
| Order/cart | `apps.orders`, frontend cart store | Assistant cart actions must call Django APIs |
| Notification | `apps.notifications` | AI services publish notification intents to Django |
| Conversation session | New Django model | Add after service-auth layer |
| Conversation memory | New Django model plus Milvus vectors | Backfill from memory retriever volume |
| Enrichment job/result | Existing product enrichment fields plus optional new job model | Preserve existing product enrichment behavior |
| Generated asset | New Django model | Store object key, owner, product, type, checksum |

## Proposed Django Migration Models

Create these in a future migration after service authentication is added:

- `AIServiceCredential`
- `AIRequestLog`
- `ConversationSession`
- `ConversationMemory`
- `AIJob`
- `GeneratedAsset`

## Safe Migration Sequence

1. Add read-only Django models for AI metadata.
2. Backfill assistant session identifiers to Django user UUIDs.
3. Backfill generated/enriched asset metadata without moving binary files.
4. Add write paths through Django APIs.
5. Switch assistant/enrichment services to use Django-owned IDs.
6. Decommission standalone durable memory only after parity checks.

## Rollback

- Do not delete source service volumes during migration.
- Use idempotent backfill scripts with source checksum tracking.
- Keep old service IDs in compatibility columns until all consumers are migrated.
# eCommerce Database Migration Plan Update

Copyright © 2026 Francis Banda.  
All Rights Reserved.

This platform, source code, architecture, workflows, models, databases, documentation, and all associated intellectual property are proprietary and exclusively owned by Francis Banda.

## Current Decision

PostgreSQL remains the canonical source of truth. Milvus is an index, not a product database. The assistant catalog CSV is an export/index feed and must not become an editable source of product records.

## Shared Entities

- Users: `apps.users.User`
- Stores/vendors: `apps.products.Store`
- Products: `apps.products.Product`
- Inventory: `apps.products.InventoryRecord`
- Categories: `apps.products.Category`
- Orders: `apps.orders.Order`, `apps.orders.OrderLine`
- Enrichment data: enrichment fields on `Product`
- Search indexes: Milvus text/image collections
- Recommendation signals: order history plus product category/tag similarity

## Migration Path

1. Keep marketplace product records in Django/PostgreSQL.
2. Export approved visible products to assistant catalog CSV and `/index/products`.
3. Use product primary keys as vector index IDs for retriever-to-Django mapping.
4. Add true upsert/delete support in Milvus before high-volume production indexing.
5. Add a future `ProductEmbeddingIndex` relational audit table if vector sync reconciliation becomes necessary.

## Duplicate Data Policy

- Product names, descriptions, prices, inventory, and categories are authoritative only in PostgreSQL.
- Vector metadata may duplicate product display fields for retrieval speed.
- Assistant memory may store user conversation state but must not override marketplace records.
