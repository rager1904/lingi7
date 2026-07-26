Copyright © 2026 Francis Banda.
All Rights Reserved.

This software and all associated intellectual property are proprietary and owned exclusively by Francis Banda.

Unauthorized copying, modification, distribution, sublicensing, resale, reverse engineering, or commercial use is prohibited without explicit written permission from Francis Banda.

# AI Orchestration Architecture

## Architecture Decision

Use Django as the policy and identity control plane, with LangGraph-based assistant services and enrichment services behind authenticated internal APIs. The orchestration layer is a gateway pattern, not a rewrite of every agent.

## Routing Domains

| Intent Domain | Routed To | Current Implementation |
| --- | --- | --- |
| Marketplace/product shopping | Shopping assistant | `assistant/chain_server` and catalog retriever |
| Catalog enrichment | Enrichment service | `enrichment/src/backend` |
| Fraud/risk | Django fraud app | `lingi7/apps/fraud` |
| Education/student/medical/research | Future domain agents | Add as new Django-registered agent capabilities, not duplicate apps |
| Analytics/admin | Django dashboard and admin audit | Django admin/API plus future analytics views |

## Request Flow

1. User authenticates once through Django JWT.
2. React frontend calls `/api/v1`.
3. Django validates permissions and creates an `AIRequestLog`.
4. Django routes the request to the correct internal service.
5. AI service returns structured output.
6. Django stores durable metadata/memory and returns standardized JSON.

## Shared Memory

- Short-term context: assistant session state.
- Long-term user memory: PostgreSQL model linked to `apps.users.User`.
- Retrieval memory: Milvus vectors keyed by Django UUIDs and product IDs.
- Sensitive data: never sent to general prompts unless strictly needed and explicitly scoped.

## Standard Response Contract

```json
{
  "data": {},
  "meta": {
    "request_id": "uuid",
    "model": "llama3.2:3b",
    "service": "assistant"
  }
}
```

Errors:

```json
{
  "error": {
    "code": "ai_service_unavailable",
    "message": "The assistant service is temporarily unavailable.",
    "details": {}
  },
  "meta": {
    "request_id": "uuid"
  }
}
```

## Security Controls

- JWT for users.
- Short-lived internal tokens for service-to-service calls.
- Request IDs across Nginx, Django, Celery, FastAPI, and model calls.
- Per-user rate limits and AI quotas.
- Prompt/input/output safety filters for assistant and generated content.
