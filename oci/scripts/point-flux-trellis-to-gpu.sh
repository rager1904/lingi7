#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Lingi7 — Point the CPU-host enrichment backend at the GPU-host FLUX/TRELLIS.
#
# Usage:  bash point-flux-trellis-to-gpu.sh <GPU_PUBLIC_IP>
#
# Rewrites just the `flux` / `trellis` url entries in
# enrichment/shared/config/config.yaml (bind-mounted read-only into the
# enrichment-backend container). Idempotent — safe to re-run.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

GPU_IP="${1:-}"
if [[ -z "$GPU_IP" ]]; then
  echo "Usage: bash point-flux-trellis-to-gpu.sh <GPU_PUBLIC_IP>" >&2
  exit 1
fi

CONFIG="enrichment/shared/config/config.yaml"

if [[ ! -f "$CONFIG" ]]; then
  echo "ERROR: $CONFIG not found. Run from the repo root." >&2
  exit 1
fi

echo "==> Updating $CONFIG -> FLUX/TRELLIS at $GPU_IP"

# Rewrite the yaml block for flux and trellis wholesale (python for safety).
python3 - "$CONFIG" "$GPU_IP" <<'PY'
import re, sys
path, gpu_ip = sys.argv[1], sys.argv[2]
with open(path, "r", encoding="utf-8") as f:
    text = f.read()

def swap(section, url):
    pat = re.compile(
        rf"(^{section}:\n)(\s*url: ).+",
        re.MULTILINE,
    )
    return pat.sub(lambda m: m.group(1) + m.group(2) + url, text)

text = swap("flux", f"http://{gpu_ip}:8030/v1/infer")
text = swap("trellis", f"http://{gpu_ip}:8031/v1/infer")

with open(path, "w", encoding="utf-8") as f:
    f.write(text)
PY

echo "==> Resulting flux/trellis config:"
grep -nA2 -E '^flux:|^trellis:' "$CONFIG"

echo
echo "Now restart the enrichment backend so it reloads the config:"
echo "  docker compose restart enrichment-backend"