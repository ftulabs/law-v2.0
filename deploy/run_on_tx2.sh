#!/usr/bin/env bash
# Run the VeriTrade container on the Jetson TX2.
# TX2 has 8 GB RAM vs Nano's 4 GB, so memory limits are relaxed.
#
# Prereqs: same as run_on_jetson.sh — image loaded + .env present.
#   ~/veritrade/.env  (OPENROUTER_API_KEY, LLM_PROVIDER, OPENROUTER_MODEL, RETRIEVER)
set -euo pipefail

IMG="${IMG:-veritrade:arm64}"
BASE="${BASE:-$HOME/veritrade}"
ENV_FILE="${ENV_FILE:-$BASE/.env}"
PORT="${PORT:-8501}"

[ -f "$ENV_FILE" ] || { echo "missing $ENV_FILE (OPENROUTER_API_KEY etc.)"; exit 1; }
mkdir -p "$BASE/outputs" "$BASE/cache"

docker rm -f veritrade 2>/dev/null || true
docker run -d --name veritrade --restart unless-stopped \
  -p "${PORT}:8501" \
  --env-file "${ENV_FILE}" \
  --memory=8g --memory-swap=12g \
  -v "$BASE/outputs:/app/outputs" \
  -v "$BASE/cache:/app/data/cache" \
  "${IMG}"

echo "VeriTrade starting on http://$(hostname -I | awk '{print $1}'):${PORT}  (give it ~30s)"
echo "Public URL (after CF tunnel): https://veritrade.ftu.fyi"
echo "logs:  docker logs -f veritrade"
