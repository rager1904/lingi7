# Lingi7 Platform — Oracle Cloud Deployment Guide

Deploy the **full platform** (all ~21 services, including FLUX image generation
and TRELLIS 3D generation) on Oracle Cloud using your Always-Free tier plus your
new-account free credit.

```
                    Internet
                       │  http://<CPU_IP>:80
                       ▼
┌──────────────────────────────┐        ┌──────────────────────────────┐
│  ARM instance (FREE forever) │        │  GPU instance (credit/billed)│
│  VM.Standard.A1.Flex        │        │  VM.GPU.A10.1 (24GB VRAM)     │
│  4 OCPU / 24 GB RAM          │        │  x86_64 Ubuntu 22.04          │
│  Ubuntu 22.04 aarch64        │        │                              │
│                              │        │  flux   :8030 → /v1/infer     │
│  Django + Celery + Postgres  │        │  trellis:8031 → /v1/infer     │
│  Redis + Milvus + MinIO      │ 8030/31│                              │
│  4× Ollama (3B + 7B models)  │◄──────►│  (HF gated FLUX.1-schnell)    │
│  BGE + CLIP embeddings       │        │                              │
│  Enrichment + Assistant stack│        │  STOP when not testing to     │
│  Nginx (port 80)             │        │  save your $300 credit.       │
└──────────────────────────────┘        └──────────────────────────────┘
```

**Cost during your 30-day credit window:**
- ARM instance: **$0** (Always-Free, stays free after credits expire).
- GPU instance: billed from your credit (~$1–4/hr depending on shape/region).
  ≈ 75–300 hours of GPU uptime. **Stop it when you're not testing.**
- After the 30 days: keep the FREE ARM box only (delete the GPU instance).

---
## 0. Account status check (30 seconds)

1. Your account must be **Upgraded to Pay As You Go** to use the GPU shape and
   the free credit. Console → top-right profile → **Upgrade to Pay As You Go**.
   *(If you never upgrade, you are restricted to Always-Free shapes only — no GPU.)*
2. Confirm the credit: Billing → **Credits & Budgets** → should show your
   promotional credit and expiry date.

> ✅ **Audit result (verified in git):** `lingi7/.env.dev` is gitignored
> (`lingi7/.gitignore:36`), was **never committed**, and the real Brevo/MTN keys
> appear in **no commit** in `rager1904/lingi7`. A sweep of every tracked file
> and the full history found no AWS keys, GitHub tokens, HuggingFace tokens,
> private keys, or hardcoded secrets. **Nothing leaked.**
>
> Good hygiene either way: your local `.env.dev` holds *working* MTN/Brevo sandbox
> credentials — treat them as secret, don't paste them into chats, and never
> `git add -f` that file. On the server, `deploy-cpu.sh` generates placeholder
> creds; if you want live payments/email during the test, fill the real values
> **directly into the server's** `/opt/lingi7/lingi7/.env.dev` (never into git).

---
## 0.5 Generate an SSH key (both instances use it)

```powershell
# Windows PowerShell  — creates %USERPROFILE%\.ssh\id_ed25519(.pub)
ssh-keygen -t ed25519 -C "lingi7-oracle" -f $env:USERPROFILE\.ssh\id_ed25519
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub   # copy this for the console
```

Paste the `.pub` content as the SSH key on **both** instances (§4, §5). Then from
PowerShell: `ssh ubuntu@<IP>` (or `ssh -i <key> ubuntu@<IP>` if you chose another path).

---
## 1. Pick region + confirm GPU capacity

- Console top-right → **Region: Africa South 1 (Johannesburg)** if not set.
- Open **Governance → Limits, Quotas and Usage** (a.k.a. Limits, Quotas and
  Usage) and look for `compute` → shape:
  - `VM.GPU.A10.1` (1× A10, 24 GB VRAM) — **preferred for FLUX**
  - `VM.GPU.A100.1` / `VM.GPU.A100.2` (40/80 GB) — bigger, pricier fallback
- If the region shows **zero GPU quota**, you have two options:
  - Request a limit increase (takes hours–days), or
  - Create the **GPU instance in another region** (e.g. `eu-frankfurt-1`). The
    ARM box stays in Johannesburg; FLUX/TRELLIS calls just go over the public
    internet. This guide works unchanged — only the GPU IP differs.

---
## 2. Commit & push your current work first

The server pulls the repo from GitHub, so your latest state must be pushed:

```powershell
# Windows, in D:\lingi7_scaffold
git add -A
git commit -m "feat: oracle oci deployment pack"
git push origin HEAD
```

If you have uncommitted data you must keep (e.g. `assistant/shared/data/products_extended.csv`),
commit and push it too — the change sits in the working tree right now.

---
## 3. Create the network

Console → **Networking → Virtual cloud networks → Create VCN**:

| Field | Value |
|---|---|
| Name | `lingi7-vcn` |
| IPv4 CIDR | `10.0.0.0/16` |
| DNS resolution / hostname labels | enabled |
| Internet Gateway | add a default route `0.0.0.0/0 → Internet Gateway` |

Use the default public subnet (`10.0.0.0/24`, public IP on launch) OR create two:
- `public-subnet` (10.0.0.0/24) — public IPs, internet gateway route
- `private-subnet` (10.0.1.0/24) — no public IP (optional hardening)

### Security list / Network security group — ingress rules

One NSG or security-list update that covers BOTH instances:

| Direction | Source | Port | Purpose |
|---|---|---|---|
| Ingress | `0.0.0.0/0` | `22/tcp` | SSH (tighten to your IP if you want) |
| Ingress | `0.0.0.0/0` | `80/tcp` | Platform HTTP |
| Ingress | `0.0.0.0/0` | `8030/tcp` | FLUX on GPU host *(tighten to CPU IP or your IP)* |
| Ingress | `0.0.0.0/0` | `8031/tcp` | TRELLIS on GPU host *(same)* |

---
## 4. Create the CPU instance (Always-Free ARM)

Console → **Compute → Instances → Create instance**:

| Field | Value |
|---|---|
| Name | `lingi7-cpu` |
| Image | **Canonical Ubuntu 22.04 (aarch64)** — pick the `aarch64` variant |
| Shape | **VM.Standard.A1.Flex** |
| — OCPUs | `4` |
| — Memory | `24 GB` |
| Boot volume | `200 GB` |
| Networking | `lingi7-vcn` → `public-subnet`, assign **public IPv4** |
| SSH keys | paste your public key |
| Availability domain | `AD-1` (any) |

> The Always-Free quota allows up to 4 OCPU / 24 GB ARM total and ~200 GB of
> block volume. This single instance uses exactly that.

Once running, note its **public IP** (instance details → Primary VNIC).

##
## 5. Create the GPU instance (credit-billed)

Console → **Compute → Instances → Create instance**:

| Field | Value |
|---|---|
| Name | `lingi7-gpu` |
| Image | **Canonical Ubuntu 22.04 (x86_64)** |
| Shape | `VM.GPU.A10.1` (fallback `VM.GPU.A100.1`) |
| Boot volume | `200 GB` (FLUX.1-schnell weights ≈ 24 GB on disk) |
| Networking | same VCN / subnet as CPU host, public IPv4 |
| SSH keys | same public key |

Note its **public IP** too.

> The GPU instance is **billed to your credit while running**. Stop it in the
> console whenever you are not actively generating images/3D (see §9). You'll
> see the charge clock running from the moment it starts.

---
## 6. Bootstrap both hosts (1 command each)

From your machine, for **each** host, copy the `oci/` pack up and run it:

```powershell
scp -r oci ubuntu@<IP>:~/oci
ssh ubuntu@<IP> "sudo bash ~/oci/setup/install-docker.sh"
```

> ⚠️ Run this as `ubuntu@<IP>` — replace `<IP>` with each host's public IP
> (CPU host, then GPU host).

This installs Docker Engine + Compose v2 and adds `ubuntu` to the `docker` group.
**Log out and back in** after it finishes.

Once this script is pushed to GitHub yourself, the one-liner also works:

```bash
sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/rager1904/lingi7/main/oci/setup/install-docker.sh)"
```

---
## 7. Deploy the FLUX + TRELLIS GPU stack

```bash
# on the GPU host:  ssh ubuntu@<GPU_IP>
sudo mkdir -p /opt/lingi7 && sudo chown ubuntu:ubuntu /opt/lingi7
cd /opt/lingi7
git clone https://github.com/rager1904/lingi7.git .        # or your fork

# HuggingFace token — REQUIRED for gated FLUX.1-schnell
#   1. https://huggingface.co/settings/tokens  -> create a read token
#   2. https://huggingface.co/black-forest-labs/FLUX.1-schnell
#      click "Agree and access repository" (accept the licence)
echo "HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" > .env
chmod 600 .env

# Build + start (first build 20-40 min, first model load downloads ~24 GB)
bash oci/scripts/deploy-gpu.sh
```

Verify on the GPU host:

```bash
curl -s http://127.0.0.1:8030/health   # {"status":"healthy","model_loaded":true}
curl -s http://127.0.0.1:8031/health
```

---
## Security hardening (already wired into this pack)

- **No dev settings on a public IP.** The CPU host runs `config.settings.oci`
  (`lingi7/config/settings/oci.py`): `DEBUG=False`, strict CORS/CSRF, DRF
  throttle rates, Django password validators, security headers, and a restricted
  email fallback (console). Previously the compose shipped `settings.dev`, which
  forces `DEBUG=True` and open CORS.
- **gunicorn instead of `runserver`** for the Django web process
  (`docker-compose.oci.yml`).
- **Debug endpoint removed from prod paths.** `/_debug/register/` in
  `config/urls.py` is now gated behind `settings.DEBUG`.
- **Media/static via Nginx** (`/media/` from the shared volume), whitenoise for
  compiled static — no dependency on DEBUG serving.
- **Fresh secrets generated on first deploy** (`openssl`) for `SECRET_KEY`,
  `POSTGRES_PASSWORD`, `MINIO_ROOT_PASSWORD`, `API_KEY`, `INTERNAL_API_KEY`.
  Nothing security-critical is ever baked into git.
- **`ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` / CORS pinned to your IP.**
- **Only port 80 (HTTP) + 22 (SSH) exposed** through the OCI security list;
  8030/8031 should be locked to your IP (§3). Everything else (Postgres, Redis,
  MinIO, Milvus, Ollama) stays on the private Docker network.

> What this is **not** (yet): TLS, a real domain, WAF/rate limits at the edge,
> secrets manager. Add those before real production users. The 30-day test runs
> over plain HTTP on a throwaway IP — fine for functional testing, not for live
> money/accounts.

---
## 8. Deploy the CPU stack

```bash
# on the CPU host:  ssh ubuntu@<CPU_IP>
sudo mkdir -p /opt/lingi7 && sudo chown ubuntu:ubuntu /opt/lingi7
cd /opt/lingi7
git clone https://github.com/rager1904/lingi7.git .

# Everything is automated: generates secrets, edits ALLOWED_HOSTS,
# points enrichment at your GPU host, starts all 19 CPU services.
bash oci/scripts/deploy-cpu.sh <CPU_IP> <GPU_IP>
```

If you deploy the GPU box later (or it restarts with a new IP), just re-run:

```bash
cd /opt/lingi7
bash oci/scripts/point-flux-trellis-to-gpu.sh <GPU_IP>
docker compose restart enrichment-backend
```

### Final wiring check

```bash
cd /opt/lingi7 && bash oci/scripts/verify.sh <CPU_IP>
```

Expected PASS: Django health, platform status API, assistant health, assistant
UI, admin login page.

---
## 9. Test the platform fully

| What | How |
|---|---|
| Landing / API index | `http://<CPU_IP>/` |
| Admin | `http://<CPU_IP>/admin/` → create a superuser first: `docker compose exec lingi7-web python manage.py createsuperuser` |
| Register a vendor & product | register at `http://<CPU_IP>/`, then create a product |
| Enrichment workbench (VLM/LLM + FLUX + TRELLIS) | Dashboard → products → **Enrichment Workbench** — generate descriptions, image variations (FLUX), and 3D assets (TRELLIS) |
| Shopping assistant chat | `http://<CPU_IP>/assistant/` |
| Assistant API | `http://<CPU_IP>/api/assistant/` |
| Logs | `docker compose logs -f --tail=100 lingi7-web enrichment-backend lingi7-chain-server` |
| Watch GPU usage | GPU host: `nvidia-smi` (inside `lingi7-flux` / `lingi7-trellis`) |

### Saving credit while testing

- GPU instance **Stop** in the console when idle. Starting it again may change
  the public IP → re-run `point-flux-trellis-to-gpu.sh` and `restart enrichment-backend`.
- ARM host keeps running 24/7 at **$0** — leave it up through the whole 30 days.

---
## 10. After the 30-day credit window

- **Delete or stop the GPU instance** so you are never billed.
- The ARM box keeps working at $0 — but **remove the now-dead GPU URL** from the
  enrichment config (`flux`/`trellis` appear as unavailable; the rest of the
  platform is unaffected) and re-run deploy without the GPU arg.
- Before any real production use: rotate the committed MTN/Brevo keys, add a
  domain + TLS (Certbot), set `DJANGO_DEBUG=False`, and restrict identity rules.

---
## Troubleshooting

| Symptom | Fix |
|---|---|
| `docker compose up` builds on CPU host then fails on `flux`/`trellis` | You typed `docker compose up -d` with no service list. Always use `oci/scripts/deploy-cpu.sh` or explicit service names with `--no-deps`. |
| `401 Client Error` from FLUX at startup | HF token missing, or licence not accepted for `FLUX.1-schnell`. See §7. |
| `DisallowedHost` on Django | Run deploy script again — it appends `<CPU_IP>` to `DJANGO_ALLOWED_HOSTS` in `lingi7/.env.dev`; afterwards restart `lingi7-web`. |
| No GPU capacity in Johannesburg | Request limit increase or create the GPU instance in another region (§1). |
| Memory pressure on ARM box | Whole-CPU stack fits in 24 GB, but model RAM spikes during generation. Give the VLM/LLM a moment; queries are queued by Ollama. |
| GPU IP changed after restart | Re-run `point-flux-trellis-to-gpu.sh <new-ip>` + `docker compose restart enrichment-backend`. |
| `git pull --ff-only` warns | Local files differ from origin (e.g. your uncommitted csv). Push your branch first (§2). |

---
## Files in this pack

```
oci/
  ORACLE_DEPLOYMENT_GUIDE.md       this file
  setup/install-docker.sh          Docker bootstrap (both hosts)
  scripts/deploy-cpu.sh            full CPU stack + secrets + allowed hosts
  scripts/deploy-gpu.sh            FLUX + TRELLIS build/start on GPU host
  scripts/point-flux-trellis-to-gpu.sh   repoint enrichment → GPU IP
  scripts/verify.sh                endpoint checks
  .env.server.template             server-side .env reference
docker-compose.gpu.yml             GPU host override (exposes :8030/:8031)
docker-compose.oci.yml             OCI hardening override (settings + gunicorn)
lingi7/config/settings/oci.py      hardened settings module used on the CPU host
```

### Change log relevant to security

| Change | Why |
|---|---|
| `lingi7/config/settings/oci.py` (new) | DEBUG off, CORS/CSRF locked, throttling, validators, whitenoise — no public dev settings |
| `docker-compose.oci.yml` (new) | Uses `settings.oci` + gunicorn; nginx mounts media |
| `lingi7/config/urls.py` | `/_debug/register/` now only exists when `DEBUG=True` |
| `nginx.conf` | `/media/` served from shared volume |
| `oci/scripts/deploy-cpu.sh` | Bootstraps gitignored `lingi7/.env.dev` from the example template; generates fresh secrets; pins allowed hosts/CSRF/CORS to the public IP; bootstraps DB/media volume paths |