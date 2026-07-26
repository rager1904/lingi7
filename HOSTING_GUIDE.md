# Lingi7 Platform — Hosting Guide

## Platform Resource Requirements

| Component | RAM | CPU | Storage | GPU |
|---|---|---|---|---|
| Django + Celery + Postgres + Redis | ~2 GB | 2+ cores | 20 GB | No |
| Milvus + etcd + MinIO | ~3 GB | 2+ cores | 50 GB | No |
| Ollama (llama3.2 + qwen2.5 + llava) | ~8-10 GB | 4+ cores | 50 GB | No |
| Embedding servers (BGE + CLIP) | ~2 GB | 2+ cores | 10 GB | No |
| 3 Frontends + Nginx | ~1 GB | 1 core | 10 GB | No |
| FLUX image generation | ~4 GB | 2+ cores | 30 GB | 24 GB VRAM |
| TRELLIS 3D generation | ~4 GB | 2+ cores | 30 GB | 24 GB VRAM |
| **Total** | **~16-20 GB** | **6+ cores** | **~200 GB** | **24 GB+ (optional)** |

---

## Can It Run on Google Colab Free Tier?

**No.** Colab free tier provides 12.7GB RAM, no Docker, no persistence, and limited GPU.
The full 18-service stack cannot fit. See the main README for details.

---

## Hosting Options by Budget

### Option 1: CPU-Only (No FLUX/TRELLIS) — $7-22/mo

Runs everything except image generation and 3D generation.

| Provider | Plan | Specs | Price | Notes |
|---|---|---|---|---|
| Contabo | VPS M | 6 vCPU, 16 GB RAM, 400 GB SSD | ~$7/mo | Best RAM per dollar |
| Hetzner | CPX41 | 8 vCPU, 16 GB RAM, 160 GB | ~$22/mo | Best balance, fast AMD EPYC |
| Vultr | Regular Cloud | 4 vCPU, 8 GB RAM, 200 GB | ~$48/mo | Too expensive for this |
| DigitalOcean | General Purpose | 4 vCPU, 8 GB RAM | ~$48/mo | Too expensive for this |

### Option 2: Full System with GPU — $30-50/mo

For FLUX + TRELLIS you need 24GB+ VRAM.

| Provider | GPU | Price/hr | Monthly (8hr/day) |
|---|---|---|---|
| Vast.ai (marketplace) | RTX 3090 24GB | ~$0.20 | ~$48 |
| RunPod | RTX 4090 24GB | ~$0.44 spot | ~$106 |
| Lambda Labs | A10 24GB | ~$0.75 | ~$180 |
| Google Cloud | L4 24GB | ~$0.71 | ~$173 |
| AWS | L4 24GB | ~$0.81 | ~$197 |

### Option 3: Split Approach (Recommended for Production)

| Component | Where | Cost |
|---|---|---|
| All CPU services (Django, Ollama, Milvus, etc.) | Hetzner CPX41 | $22/mo |
| FLUX + TRELLIS (on-demand only) | Vast.ai RTX 4090 | ~$0.50/hr when needed |

Pay GPU costs only when generating images/3D, not 24/7.

### Option 4: Free / Near-Free (Development Only)

| Service | Free Option |
|---|---|
| Oracle Cloud Free Tier | Always-free ARM: 4 OCPU, 24 GB RAM — fits all CPU services |
| HuggingFace Spaces | Can host lightweight FastAPI services |
| GitHub Codespaces | 2-core, 16GB — temporary dev only |
| Railway / Render | Free tiers too small for full stack |

---

## Recommended Phased Approach

| Phase | Setup | Monthly Cost |
|---|---|---|
| Development | Oracle Cloud Free Tier (skip FLUX/TRELLIS) | $0 |
| MVP / Testing | Hetzner CPX41 (CPU-only, minus GPU services) | $22 |
| Production | Hetzner CPX41 + Vast.ai on-demand GPU | $22 + usage |
| Full Production 24/7 | Hetzner CPX41 + dedicated GPU VPS | ~$70-100 |

---

## Key Insight

Skip FLUX and TRELLIS initially. They are image variation and 3D asset generation features
that are not core to the escrow marketplace. The platform works fully without them.
Disable these two services in docker-compose and the entire stack fits on a $22/mo VPS.

---

## Provider Sign-Up Links

- Hetzner Cloud: https://hetzner.cloud
- Contabo: https://contabo.com
- Vast.ai: https://vast.ai
- RunPod: https://runpod.io
- Lambda Labs: https://lambdalabs.com
- Oracle Cloud Free Tier: https://cloud.oracle.com/free
