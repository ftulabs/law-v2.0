#!/usr/bin/env bash
# Được gọi bởi GitHub Actions runner trên Xavier.
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
