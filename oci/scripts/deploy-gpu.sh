#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Lingi7 — Deploy FLUX + TRELLIS on the Oracle GPU instance.
#
# Prereqs:
#   * install-docker.sh already ran
#   * repo cloned at ${APP_DIR} (default: /opt/lingi7)
#   * git remote points at a repo containing docker/flux.Dockerfile,
#     docker/trellis.Dockerfile, docker/flux_server.py, docker/trellis_server.py
#
# Usage:
#   bash deploy-gpu.sh
#
# The two services bind host ports 8030 and 8031. Lock them down in OCI to the
# CPU host's IP if possible (see OCI guide, NSG step).
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/lingi7}"

if [[ ! -d "$APP_DIR/.git" ]]; then
  echo "ERROR: repo not found at $APP_DIR. Clone it first (see ORACLE_DEPLOYMENT_GUIDE.md)." >&2
  exit 1
fi

cd "$APP_DIR"

echo "==> Refreshing repo (fast-forward only)"
git fetch origin
git pull --ff-only || echo "WARN: pull not fast-forward; continuing with local files"

if [[ ! -f .env ]]; then
  echo "ERROR: missing .env. Create one with HF_TOKEN=<your huggingface token>" >&2
  echo '  echo "HF_TOKEN=..." > .env' >&2
  exit 1
fi

echo "==> Verifying HF gated access for FLUX.1-schnell"
if ! curl -sL "https://huggingface.co/api/models/black-forest-labs/FLUX.1-schnell" -H "Authorization: Bearer ${HF_TOKEN:-}" >/dev/null 2>&1; then
  echo "WARN: could not verify HF token. FLUX will fail at startup if the model is gated."
fi

echo "==> Building FLUX + TRELLIS images (first build can take 20-40 min)"
docker compose -f docker-compose.yml -f docker-compose.gpu.yml build --pull flux trellis

echo "==> Starting FLUX (host :8030) and TRELLIS (host :8031)"
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --no-deps flux trellis

echo "==> Waiting for model servers to come up (first load downloads big models)"
for i in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:8030/health" >/dev/null 2>&1 \
     && curl -sf "http://127.0.0.1:8031/health" >/dev/null 2>&1; then
    echo "OK: flux + trellis healthy."
    break
  fi
  echo "  ...waiting (${i}/60)"
  sleep 10
done

curl -sf "http://127.0.0.1:8030/health" || echo "WARN: flux /health not up yet — check 'docker compose logs flux'"
curl -sf "http://127.0.0.1:8031/health" || echo "WARN: trellis /health not up yet — check 'docker compose logs trellis'"

echo
echo "DONE. Logs:"
echo "  docker compose -f docker-compose.yml -f docker-compose.gpu.yml logs -f flux trellis"
echo "Health:"
echo "  curl http://127.0.0.1:8030/health   # flux"
echo "  curl http://127.0.0.1:8031/health   # trellis"