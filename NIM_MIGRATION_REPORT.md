Copyright © 2026 Francis Banda.
All Rights Reserved.

This software and all associated intellectual property are proprietary and owned exclusively by Francis Banda.

Unauthorized copying, modification, distribution, sublicensing, resale, reverse engineering, or commercial use is prohibited without explicit written permission from Francis Banda.

# NIM Migration Report

## Summary

All active source/configuration references to the prior proprietary hosted inference path were replaced with self-hosted open-source alternatives. The default deployment path is now CPU-first and does not require proprietary cloud inference, proprietary inference containers, or GPU runtime reservations.

## Migration Matrix

| Dependency Found | File Location | Current Purpose | Replacement Selected | Migration Status |
| --- | --- | --- | --- | --- |
| Hosted LLM API override | `assistant/shared/configs/chain_server/config-build.yaml` | Assistant routing/chatter/summarization override | Local Ollama OpenAI-compatible endpoint with `llama3.2:3b` | Complete |
| Hosted text embedding override | `assistant/shared/configs/catalog_retriever/config-build.yaml` | Build-time semantic retrieval embeddings | Local BGE endpoint with `BAAI/bge-small-en-v1.5` | Complete |
| Hosted image embedding override | `assistant/shared/configs/catalog_retriever/config-build.yaml` | Build-time visual retrieval embeddings | Local CLIP endpoint with `openai/clip-vit-base-patch32` | Complete |
| Hosted guardrails override | `assistant/shared/configs/rails/config-build.yaml` | Safety/topic-control model override | Local safety endpoint at `http://llama-guard:8000/v1` | Complete |
| Cloud quality-test client | `assistant/tests/integration/response_quality.py` | LLM-based response quality judging | Environment-driven local OpenAI-compatible clients | Complete |
| Vendor-specific test copyright/header text | `assistant/tests/unit/chain_server/test_functions.py` | Unit test documentation/header | Francis Banda ownership inherited from repository notices; generic open-source model wording | Complete |
| GPU-only model serving | `docker-compose.yml` | Root LLM/VLM/safety services | CPU-first `ollama/ollama` services on OpenAI-compatible `/v1` endpoints | Complete |
| GPU runtime reservations | `docker-compose.yml` | Model and embedding services | Removed from default deployment path | Complete |
| Large default embedding models | `assistant/shared/configs/catalog_retriever/config.yaml`, `enrichment/shared/config/config.yaml`, `docker-compose.yml` | Text/image retrieval embeddings | BGE small and CLIP base defaults for 16GB RAM targets | Complete |
| Large default LLM/VLM model names | `assistant/shared/configs/chain_server/config.yaml`, `assistant/shared/configs/rails/config.yml`, `enrichment/shared/config/config.yaml` | Assistant, enrichment, safety | `llama3.2:3b`, `qwen2.5:3b`, `llava:7b` | Complete |

## Verification

- Active source/config scan for prior provider/container/runtime identifiers returned no matches after migration.
- `docker compose config --quiet` passes with required platform secrets supplied.
- `npm run type-check` passes in `lingi7/frontend`.
- `npm run build` passes in `lingi7/frontend`.

## Notes

- The repository still contains migration reports that name historical dependencies for audit traceability.
- Ollama model images do not include pulled model weights by default. Pull the selected models during deployment or bake them into a private deployment image.
- FLUX and TRELLIS remain open-source self-hosted services. They are resource-intensive; low-resource deployments should disable user-facing media generation until capacity is available.
