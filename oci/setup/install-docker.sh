#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Lingi7 — Bootstrap an Oracle Cloud Ubuntu 22.04 host with Docker.
#
# Run as:  sudo bash install-docker.sh
# Works on both the ARM CPU host and the x86_64 GPU host.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "ERROR: run with sudo:  sudo bash install-docker.sh" >&2
  exit 1
fi

echo "==> Updating apt and installing prerequisites"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
  ca-certificates \
  curl \
  git \
  jq \
  openssl \
  ufw \
  util-linux

echo "==> Installing docker engine + compose v2 (convenience script)"
if command -v docker >/dev/null 2>&1; then
  echo "docker already installed: $(docker --version)"
else
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker

echo "==> Adding ubuntu user to the docker group"
if id -u ubuntu >/dev/null 2>&1; then
  usermod -aG docker ubuntu || true
fi

echo "==> Verifying compose plugin"
docker compose version

echo "==> Disk space check"
df -h / | awk 'NR==1 || NR==2'

echo
echo "DONE. Log out and back in (or run:  newgrp docker) so docker works without sudo."
echo "Your host is ready. Next: run the deploy script for this host type."