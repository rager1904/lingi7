#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Lingi7 — Quick endpoint checks after deployment.
#
# Usage:  bash verify.sh [CPU_PUBLIC_IP]
#         (defaults to the instance's own public IP at icanhazip.com)
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

IP="${1:-$(curl -fsS https://icanhazip.com 2>/dev/null || echo localhost)}"
BASE="http://${IP}"

echo "==> Verifying platform at ${BASE}"

check() {
  local name="$1" url="$2" expect="${3:-200}"
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 "$url" 2>/dev/null)
  if [[ "$code" == "$expect" ]]; then
    echo "PASS  ($code)  $name  -> $url"
  else
    echo "FAIL  ($code, wanted $expect)  $name  -> $url"
  fi
}

check "Django health"           "$BASE/health/"
check "Platform status API"     "$BASE/api/v1/platform/status/"
check "Assistant health"        "$BASE/api/assistant/health"
check "Assistant UI"            "$BASE/assistant/"
check "Admin login page"        "$BASE/admin/login/"

echo
echo "==> Container status:"
docker compose -f docker-compose.yml ps