# Assistant Architecture

Copyright © 2026 Francis Banda.  
All Rights Reserved.

This platform, source code, architecture, workflows, models, databases, documentation, and all associated intellectual property are proprietary and exclusively owned by Francis Banda.

## Entry Point

The assistant is available through Django at:

- `POST /api/v1/ai/assistant/query/`

The endpoint requires JWT authentication and uses the Django user ID as the assistant session identity.

## Internal Services

- `chain-server`: shopping assistant graph and task routing.
- `catalog-retriever`: semantic product retrieval.
- `memory-retriever`: conversation/user memory service.
- `guardrails`: response safety validation.
- `milvus`: vector database.

## Capabilities

- Natural-language product search.
- Inventory-aware product responses through indexed product fields and Django fallback.
- Product recommendations and related products.
- Product comparison through assistant chain responses.
- Customer support context for product, order, shipping, and return questions.

## Fallback Strategy

If `chain-server` is unavailable, Django returns a safe fallback response with matching catalog products from PostgreSQL. This keeps the buyer experience usable during model restarts.

## Security

- Public assistant service URLs should not be exposed directly in production.
- Nginx should route external traffic to Django only for authenticated assistant calls.
- Assistant rate limiting is enforced with DRF scoped throttling.
