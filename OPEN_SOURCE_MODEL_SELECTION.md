Copyright © 2026 Francis Banda.
All Rights Reserved.

This software and all associated intellectual property are proprietary and owned exclusively by Francis Banda.

Unauthorized copying, modification, distribution, sublicensing, resale, reverse engineering, or commercial use is prohibited without explicit written permission from Francis Banda.

# Open-Source Model Selection

## Default Low-Resource Profile

Optimized for Intel i7, 16GB RAM, CPU-only hosts.

| Capability | Model | Runtime | Reason |
| --- | --- | --- | --- |
| Assistant LLM | `llama3.2:3b` | Ollama | Practical CPU latency and broad instruction following |
| Catalog LLM | `qwen2.5:3b` | Ollama | Strong structured extraction for small model size |
| Vision-language | `llava:7b` | Ollama | Widely available local VLM fallback |
| Text embeddings | `BAAI/bge-small-en-v1.5` | Custom FastAPI/Hugging Face | Lower memory than large embeddings, strong retrieval baseline |
| Image embeddings | `openai/clip-vit-base-patch32` | Custom FastAPI/Hugging Face | Lower memory visual search baseline |
| Vector database | Milvus | Milvus standalone | Already integrated with assistant and enrichment |

## Higher-Accuracy Profile

Use on hosts with stronger CPU/GPU resources:

- Assistant LLM: Llama 3.1/3.3 8B or Qwen 2.5 7B/14B
- Catalog LLM: Qwen 2.5 7B
- Vision-language: Qwen2-VL 7B
- Text embeddings: BGE large or multilingual E5 large
- Image embeddings: CLIP ViT large patch14

## Model Pull Commands

For Ollama-backed services:

```powershell
docker compose up -d llm llm-small vlm llama-guard
docker exec lingi7-llm ollama pull llama3.2:3b
docker exec lingi7-llm-small ollama pull qwen2.5:3b
docker exec lingi7-vlm ollama pull llava:7b
docker exec lingi7-llama-guard ollama pull llama3.2:3b
```

## Selection Policy

- Default to small CPU-capable models.
- Increase model size only after measuring task accuracy and latency.
- Keep OpenAI-compatible clients so runtime can switch between Ollama, vLLM, and Hugging Face-compatible gateways without changing app code.
