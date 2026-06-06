#!/usr/bin/env bash
# =============================================================================
# VeriTrade — one-shot setup on Jetson Xavier
# Cài: Docker (nếu chưa có), cloudflared tunnel, GitHub Actions self-hosted runner
#
# Chạy trên Xavier (với sudo / root):
#   sudo bash setup_xavier_all.sh
#
# Sau đó Xavier sẽ:
#   - tự expose app ra https://veritrade.ftu.fyi  (qua CF tunnel)
#   - tự pull + rebuild + restart mỗi khi có push lên GitHub main
# =============================================================================
set -euo pipefail

# ─── CONFIG ──────────────────────────────────────────────────────────────────
GITHUB_REPO="ftulabs/law-v2.0"
GITHUB_RUNNER_VERSION="2.323.0"
APP_USER="${SUDO_USER:-$(logname 2>/dev/null || echo ubuntu)}"
APP_HOME="/home/${APP_USER}"
VERITRADE_DIR="${APP_HOME}/veritrade"

# Cloudflare Tunnel token (từ Zero Trust dashboard → Tunnels → token)
CF_TUNNEL_TOKEN="${CF_TUNNEL_TOKEN:-cfut_9z7IERyoY2lLR67DFpGWR9VcZsptjdHwsxoLcwNYe224b06c}"

# GitHub Actions runner registration token — lấy tại:
# https://github.com/ftulabs/law-v2.0/settings/actions/runners/new
# (token hết hạn sau 1 giờ, phải lấy fresh mỗi khi setup)
: "${RUNNER_TOKEN:?
  Thiếu RUNNER_TOKEN. Lấy tại:
  https://github.com/${GITHUB_REPO}/settings/actions/runners/new
  Rồi chạy lại:  sudo RUNNER_TOKEN=AXXXXX bash setup_xavier_all.sh
}"
# ─────────────────────────────────────────────────────────────────────────────

step() { echo; echo "▶ $*"; }

# ── 1. Docker ────────────────────────────────────────────────────────────────
step "[1/4] Kiểm tra Docker"
if ! command -v docker &>/dev/null; then
  echo "   Cài Docker..."
  curl -fsSL https://get.docker.com | sh
  usermod -aG docker "${APP_USER}"
  echo "   Docker đã cài — runner sẽ dùng được sau khi re-login"
else
  echo "   Docker OK: $(docker --version)"
  usermod -aG docker "${APP_USER}" 2>/dev/null || true
fi

# ── 2. Cloudflare Tunnel ────────────────────────────────────────────────────
step "[2/4] Cài cloudflared (arm64) và start tunnel → veritrade.ftu.fyi"
CF_VER="2025.5.0"
CF_DEB="cloudflared-linux-arm64.deb"
if ! command -v cloudflared &>/dev/null; then
  curl -fsSL "https://github.com/cloudflare/cloudflared/releases/download/${CF_VER}/${CF_DEB}" \
       -o "/tmp/${CF_DEB}"
  dpkg -i "/tmp/${CF_DEB}"
  rm "/tmp/${CF_DEB}"
else
  echo "   cloudflared OK: $(cloudflared --version)"
fi

mkdir -p /etc/cloudflared
printf 'TUNNEL_TOKEN=%s\n' "${CF_TUNNEL_TOKEN}" > /etc/cloudflared/veritrade.env
chmod 600 /etc/cloudflared/veritrade.env

cat > /etc/systemd/system/cloudflared-veritrade.service <<'UNIT'
[Unit]
Description=Cloudflare Tunnel — VeriTrade (veritrade.ftu.fyi)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Restart=on-failure
RestartSec=10s
EnvironmentFile=/etc/cloudflared/veritrade.env
ExecStart=/usr/bin/cloudflared tunnel --no-autoupdate run --token ${TUNNEL_TOKEN}

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now cloudflared-veritrade.service
echo "   Tunnel service: $(systemctl is-active cloudflared-veritrade)"

# ── 3. Thư mục app + .env ───────────────────────────────────────────────────
step "[3/4] Chuẩn bị thư mục VeriTrade"
mkdir -p "${VERITRADE_DIR}/outputs" "${VERITRADE_DIR}/cache"
chown -R "${APP_USER}:${APP_USER}" "${VERITRADE_DIR}"

if [ ! -f "${VERITRADE_DIR}/.env" ]; then
  cat > "${VERITRADE_DIR}/.env" <<'ENV'
# Điền key vào đây sau khi setup
OPENROUTER_API_KEY=sk-or-REPLACE_ME
LLM_PROVIDER=openrouter
OPENROUTER_MODEL=google/gemini-2.5-flash
RETRIEVER=lightrag
ENV
  chown "${APP_USER}:${APP_USER}" "${VERITRADE_DIR}/.env"
  chmod 600 "${VERITRADE_DIR}/.env"
  echo "   ⚠️  Đã tạo ${VERITRADE_DIR}/.env — nhớ điền OPENROUTER_API_KEY!"
else
  echo "   .env đã có sẵn"
fi

# ── 4. GitHub Actions self-hosted runner ────────────────────────────────────
step "[4/4] Cài GitHub Actions runner (chạy dưới user ${APP_USER})"
RUNNER_DIR="${APP_HOME}/actions-runner"

if [ -f "${RUNNER_DIR}/run.sh" ]; then
  echo "   Runner đã tồn tại tại ${RUNNER_DIR}, bỏ qua cài lại."
else
  mkdir -p "${RUNNER_DIR}"
  chown "${APP_USER}:${APP_USER}" "${RUNNER_DIR}"

  # Download runner (arm64)
  RUNNER_PKG="actions-runner-linux-arm64-${GITHUB_RUNNER_VERSION}.tar.gz"
  curl -fsSL \
    "https://github.com/actions/runner/releases/download/v${GITHUB_RUNNER_VERSION}/${RUNNER_PKG}" \
    -o "/tmp/${RUNNER_PKG}"
  tar xzf "/tmp/${RUNNER_PKG}" -C "${RUNNER_DIR}"
  rm "/tmp/${RUNNER_PKG}"
  chown -R "${APP_USER}:${APP_USER}" "${RUNNER_DIR}"

  # Cấu hình runner (chạy dưới APP_USER)
  sudo -u "${APP_USER}" "${RUNNER_DIR}/config.sh" \
    --url "https://github.com/${GITHUB_REPO}" \
    --token "${RUNNER_TOKEN}" \
    --name "xavier-$(hostname -s)" \
    --labels "self-hosted,arm64,xavier" \
    --work "${RUNNER_DIR}/_work" \
    --unattended \
    --replace
fi

# Cài runner như systemd service
"${RUNNER_DIR}/svc.sh" install "${APP_USER}" 2>/dev/null || true
"${RUNNER_DIR}/svc.sh" start 2>/dev/null || true

RUNNER_SVC="actions.runner.${GITHUB_REPO//\//.}.xavier-$(hostname -s)"
echo "   Runner service: $(systemctl is-active "${RUNNER_SVC}" 2>/dev/null || echo 'started')"

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════════"
echo " Setup xong! Tóm tắt:"
echo ""
echo " 🌐 Tunnel:  systemctl status cloudflared-veritrade"
echo "             https://veritrade.ftu.fyi  (sau khi CF dashboard config)"
echo ""
echo " 🤖 Runner:  systemctl status \"${RUNNER_SVC}\""
echo "             Xem tại: https://github.com/${GITHUB_REPO}/settings/actions/runners"
echo ""
echo " 📦 App:     Lần đầu deploy: push bất kỳ commit lên GitHub main"
echo "             Hoặc chạy thủ công: bash ${VERITRADE_DIR}/redeploy.sh"
echo ""
if grep -q "REPLACE_ME" "${VERITRADE_DIR}/.env" 2>/dev/null; then
echo " ⚠️  Chưa điền .env! Chạy:"
echo "     nano ${VERITRADE_DIR}/.env"
echo "     (điền OPENROUTER_API_KEY)"
fi
echo "════════════════════════════════════════════════════════════"
