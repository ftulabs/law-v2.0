#!/usr/bin/env bash
# Run the VeriTrade self-host container on the Jetson Nano.
#
# Prereqs on the Nano: Docker, the 'veritrade:arm64' image already loaded (built on a
# bigger host — see deploy/build_and_ship.sh), and an .env with the secrets:
#   ~/veritrade/.env   (OPENROUTER_API_KEY=..., LLM_PROVIDER=openrouter,
#                        OPENROUTER_MODEL=google/gemini-2.5-flash, RETRIEVER=lightrag)
# The .env is mounted at runtime — the key is NEVER baked into the image.
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
  --memory=3g --memory-swap=6g \
  -v "$BASE/outputs:/app/outputs" \
  -v "$BASE/cache:/app/data/cache" \
  "${IMG}"

echo "VeriTrade starting on http://$(hostname -I | awk '{print $1}'):${PORT}  (give it ~40s)"
echo "logs:  docker logs -f veritrade"
