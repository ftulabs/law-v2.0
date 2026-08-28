#!/usr/bin/env bash
# Được gọi bởi GitHub Actions runner trên TX2.
# Build image native arm64 (nhanh hơn QEMU rất nhiều) rồi restart container.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
IMG="veritrade:arm64"
# SD card path on TX2; falls back to ~/veritrade (symlink also works)
BASE="${VERITRADE_BASE:-/mnt/sd/veritrade}"
[ -d "${BASE}" ] || BASE="${HOME}/veritrade"
ENV_FILE="${BASE}/.env"
# Ensure Docker client (runner user) can read .env — sudo cp sets root ownership
chown "$(id -u):$(id -g)" "${ENV_FILE}" 2>/dev/null || true

# ── keys come from the repository's secrets, not from whatever is on this box ─────────────
# The deployed key used to live ONLY in ${ENV_FILE}, hand-edited on the server. Nothing ever
# re-checked it, so when it was revoked the site kept serving: the dashboard still said the
# engine was "ready" (it only ever asked whether a key EXISTS), every run reached the grader,
# and every call came back 401 "User not found". Local runs were fine the whole time, because
# they read a different file. A key that only one machine knows about is a key nobody can see
# rot. Setting the secret makes the deploy the single place it is defined:
#
#     gh secret set OPENROUTER_API_KEY --repo ftulabs/law-v2.0
#
# Unset secrets change nothing — the existing ${ENV_FILE} is left exactly as it is.
upsert_env() {                      # upsert_env KEY VALUE
  local key="$1" val="$2"
  [ -n "${val}" ] || return 0
  touch "${ENV_FILE}"
  # rewrite in place, preserving every other line and never echoing the value
  grep -v -E "^${key}=" "${ENV_FILE}" > "${ENV_FILE}.tmp" 2>/dev/null || true
  printf '%s=%s\n' "${key}" "${val}" >> "${ENV_FILE}.tmp"
  mv "${ENV_FILE}.tmp" "${ENV_FILE}"
  chmod 600 "${ENV_FILE}"
  echo "▶ ${key} taken from repository secrets (…${val: -6})"
}
upsert_env OPENROUTER_API_KEY "${OPENROUTER_API_KEY:-}"
upsert_env ANTHROPIC_API_KEY  "${ANTHROPIC_API_KEY:-}"
upsert_env OPENAI_API_KEY     "${OPENAI_API_KEY:-}"
upsert_env GEMINI_API_KEY     "${GEMINI_API_KEY:-}"

echo "▶ Build image từ ${REPO_DIR}"
docker build -t "${IMG}" "${REPO_DIR}"

echo "▶ Restart container"
docker rm -f veritrade 2>/dev/null || true
docker run -d --name veritrade --restart unless-stopped \
  -p 8501:8501 \
  --env-file "${ENV_FILE}" \
  --memory=6g --memory-swap=10g \
  -v "${BASE}/outputs:/app/outputs" \
  -v "${BASE}/cache:/app/data/cache" \
  "${IMG}"

echo "▶ Chờ app khởi động..."
for i in $(seq 1 12); do
  if docker exec veritrade curl -sf http://localhost:8501/_stcore/health &>/dev/null; then
    echo "✓ VeriTrade live tại https://veritrade.ftu.fyi"
    exit 0
  fi
  sleep 5
done

echo "⚠️  App chưa healthy sau 60s — xem logs:"
docker logs --tail 30 veritrade
exit 1
