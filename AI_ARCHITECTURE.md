Copyright © 2026 Francis Banda.
All Rights Reserved.

This software and all associated intellectual property are proprietary and owned exclusively by Francis Banda.

Unauthorized copying, modification, distribution, sublicensing, resale, reverse engineering, or commercial use is prohibited without explicit written permission from Francis Banda.

# AI Architecture

## Current AI Systems

| System | Location | Capabilities |
| --- | --- | --- |
| Catalog enrichment | `enrichment/src/backend` | VLM product extraction, FAQ generation, policy RAG, manual PDF extraction, image variation, 3D generation, protocol schema generation |
| Shopping assistant | `assistant/chain_server`, `catalog_retriever`, `memory_retriever`, `guardrails` | Query planning, product retrieval, cart agent, response generation, summarization, streaming, guardrails |
| Fraud detection | `lingi7/apps/fraud` | Rules and ML scoring for marketplace/transaction risk |

## Target Orchestration Layer

Django should expose an AI orchestration API under `/api/v1/ai/`:

| Endpoint | Responsibility |
| --- | --- |
| `/api/v1/ai/enrichment/jobs/` | Create/list enrichment jobs for authenticated vendors |
| `/api/v1/ai/enrichment/jobs/{id}/` | Job state, result, generated assets, policy decision |
| `/api/v1/ai/assistant/sessions/` | Create/list assistant sessions linked to a Django user |
| `/api/v1/ai/assistant/query/` | Authenticated query proxy to assistant chain server |
| `/api/v1/ai/memory/` | User-controlled memory inspection and deletion |

## Shared Memory and Context

- Durable memory belongs in PostgreSQL, linked to `users.User`.
- Vector memory belongs in Milvus, keyed by Django user/session IDs.
- Assistant requests should receive only the minimum context needed:
  - user ID
  - role/vendor/customer flags
  - cart snapshot
  - permitted product/order references
  - locale/currency

## Agent Communication

- Use Django as the policy boundary.
- Assistant agents may call catalog retriever and memory retriever internally.
- Any order, cart, payment, refund, or escrow mutation must call Django APIs and pass DRF permission checks.
- Enrichment jobs write outputs back through Django-owned product/enrichment APIs.

## Safety Controls

- Pre-check user prompts with guardrails.
- Post-check assistant responses before streaming completion.
- Log safety decisions with request ID, user ID, and model version.
- Never send KYC documents, payment credentials, or secrets to general LLM prompts.

## Model Serving

| Capability | Current Target |
| --- | --- |
| Shopping LLM | Meta Llama 3.1 70B Instruct via vLLM |
| Enrichment LLM | Meta Llama 3.1 8B Instruct via vLLM |
| Vision-language | Qwen2-VL 7B Instruct via vLLM |
| Text embeddings | BGE large EN v1.5 |
| Image embeddings | CLIP ViT large patch14 |
| Safety | Llama Guard 3 8B |
| Image generation | FLUX service |
| 3D generation | TRELLIS service |

## Production Considerations

- Use async job queues for image and 3D generation.
- Enforce per-user and per-vendor quotas.
- Track model cost, latency, token usage, retries, and failure rates.
- Version prompts and model configs.
- Store evaluation datasets for assistant quality, enrichment accuracy, policy compliance, and fraud scoring.
