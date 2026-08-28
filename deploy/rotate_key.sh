#!/usr/bin/env bash
# Replace the deployed API keys and restart the container — no rebuild, no test suite.
#
# `docker restart` is NOT enough and that is the whole trick here: --env-file is read once, at
# container creation, so a restarted container keeps the environment it was born with. The
# container is therefore removed and recreated FROM THE IMAGE ALREADY ON THE BOX, so the code
# serving afterwards is byte-identical to the code serving before. Only the environment moves.
set -euo pipefail

IMG="${VERITRADE_IMAGE:-veritrade:arm64}"
BASE="${VERITRADE_BASE:-/mnt/sd/veritrade}"
[ -d "${BASE}" ] || BASE="${HOME}/veritrade"
ENV_FILE="${BASE}/.env"

chown "$(id -u):$(id -g)" "${ENV_FILE}" 2>/dev/null || true

upsert_env() {                      # upsert_env KEY VALUE
  local key="$1" val="$2"
  [ -n "${val}" ] || return 0
  touch "${ENV_FILE}"
  grep -v -E "^${key}=" "${ENV_FILE}" > "${ENV_FILE}.tmp" 2>/dev/null || true
  printf '%s=%s\n' "${key}" "${val}" >> "${ENV_FILE}.tmp"
  mv "${ENV_FILE}.tmp" "${ENV_FILE}"
  chmod 600 "${ENV_FILE}"
  echo "▶ ${key} updated from repository secrets (…${val: -6})"
}
upsert_env OPENROUTER_API_KEY "${OPENROUTER_API_KEY:-}"
upsert_env ANTHROPIC_API_KEY  "${ANTHROPIC_API_KEY:-}"
upsert_env OPENAI_API_KEY     "${OPENAI_API_KEY:-}"
upsert_env GEMINI_API_KEY     "${GEMINI_API_KEY:-}"

if ! docker image inspect "${IMG}" >/dev/null 2>&1; then
  echo "✗ image ${IMG} is not on this host — run the full deploy instead" >&2
  exit 1
fi

echo "▶ Recreating the container from the existing image (no rebuild)"
docker rm -f veritrade 2>/dev/null || true
docker run -d --name veritrade --restart unless-stopped \
  -p 8501:8501 \
  --env-file "${ENV_FILE}" \
  --memory=6g --memory-swap=10g \
  -v "${BASE}/outputs:/app/outputs" \
  -v "${BASE}/cache:/app/data/cache" \
  "${IMG}"

echo "▶ Waiting for the app…"
for _ in $(seq 1 12); do
  if docker exec veritrade curl -sf http://localhost:8501/_stcore/health &>/dev/null; then
    echo "✓ VeriTrade live at https://veritrade.ftu.fyi"
    exit 0
  fi
  sleep 5
done

echo "⚠️  Not healthy after 60s — logs:"
docker logs --tail 30 veritrade
exit 1
