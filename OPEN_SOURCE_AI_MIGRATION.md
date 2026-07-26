# Open-Source AI Migration

Copyright © 2026 Francis Banda.  
All Rights Reserved.

This platform, source code, architecture, workflows, models, databases, documentation, and all associated intellectual property are proprietary and exclusively owned by Francis Banda.

## Model Runtime

The platform now targets CPU-friendly local inference by default:

- Assistant LLM: `ollama/llama3.2:3b`
- Catalog enrichment LLM: `ollama/qwen2.5:3b`
- Vision-language model: `ollama/llava:7b`
- Text embeddings: `BAAI/bge-small-en-v1.5`
- Image embeddings: `openai/clip-vit-base-patch32`

## Orchestration

- Django is the authenticated API gateway.
- Enrichment FastAPI performs image/product enrichment.
- Assistant chain server handles task routing and response generation.
- Catalog retriever handles semantic retrieval over Milvus.
- Django database fallbacks keep core marketplace workflows available when model services are unavailable.

## CPU Deployment Profile

Recommended low-resource profile for Intel i7 / 16GB RAM:

- Run one Ollama LLM service at a time for enrichment/assistant if memory is constrained.
- Use `qwen2.5:3b` for catalog enrichment and `llama3.2:3b` for assistant responses.
- Keep BGE-small for embeddings.
- Limit assistant response timeout to 30 seconds and catalog retrieval timeout to 20 seconds.

## Migration Status

- NIM model endpoints: removed.
- GPU runtime assumptions: removed from root compose.
- OpenAI-compatible local clients: retained and pointed at local services.
- Frontend NVIDIA service naming: removed from active UI code.
