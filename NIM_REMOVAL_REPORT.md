# NIM Removal Report

Copyright © 2026 Francis Banda.  
All Rights Reserved.

This platform, source code, architecture, workflows, models, databases, documentation, and all associated intellectual property are proprietary and exclusively owned by Francis Banda.

## Result

Active runtime and dependency scans now return no NVIDIA NIM, NVIDIA hosted endpoint, NVIDIA container runtime, NVIDIA SDK, NVIDIA API Catalog, or NVIDIA cloud integration references outside documentation.

## Dependencies Removed Or Replaced

| Dependency found | Location | Previous purpose | Replacement | Status |
|---|---|---|---|---|
| GPU/vLLM runtime services | `docker-compose.yml` | LLM/VLM inference with GPU assumptions | Ollama CPU-first services | Removed |
| GPU reservations/runtime flags | `docker-compose.yml` | NVIDIA runtime scheduling | CPU-compatible compose services | Removed |
| NVIDIA hosted model endpoints | `assistant/shared/configs/**/config-build.yaml` | Hosted inference defaults | Local OpenAI-compatible service URLs | Replaced |
| NVIDIA model IDs | `enrichment/shared/config/config.yaml`, assistant configs | LLM/embedding defaults | `qwen2.5:3b`, `llama3.2:3b`, BGE-small, CLIP-base | Replaced |
| NIM-specific integration naming | enrichment UI/backend | Health checks and function names | Provider-neutral local AI service names | Replaced |
| NVIDIA Kaizen UI dependency | `enrichment/src/ui/package.json`, `pnpm-lock.yaml` | Enrichment frontend component library | Local `ui-kit.tsx` shim | Removed |
| NVIDIA-hosted fonts and visible branding | `assistant/ui/src/chatbox.css`, chat components | Assistant UI font/branding | System font stack and Lingi7 branding | Removed |

## Verification

Commands run:

- `rg -n -i "nim|nemotron|nv-embed|nvclip|nvcr|integrate\.api\.nvidia|runtime:\s*nvidia|device_ids|capabilities:\s*\[gpu\]|@kui|kui-foundations|brand-assets|nvidia-logo|nvinfo" -g "!*.md" -g "!*.ipynb" -g "!lingi7.worktrees/**"`
- `rg -n -i "nvidia" -g "!*.md" -g "!*.ipynb" -g "!lingi7.worktrees/**"`

Both active scans completed with no runtime/dependency matches.
