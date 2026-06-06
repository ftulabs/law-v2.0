#!/usr/bin/env bash
# Install cloudflared on Jetson Xavier/Nano (arm64) and run the VeriTrade tunnel as a
# systemd service.  The tunnel token comes from the Zero Trust dashboard:
#   dash.cloudflare.com → Zero Trust → Networks → Tunnels → <tunnel> → Configure → token
#
# Usage (run AS ROOT on the Xavier):
#   TUNNEL_TOKEN=cfut_xxx bash setup_cf_tunnel.sh
#
# After this script the tunnel survives reboots — no cloudflared login needed.
set -euo pipefail

: "${TUNNEL_TOKEN:?Set TUNNEL_TOKEN=cfut_xxx before running}"

CF_ARCH="arm64"
CF_VER="2025.5.0"
CF_DEB="cloudflared-linux-${CF_ARCH}.deb"
CF_URL="https://github.com/cloudflare/cloudflared/releases/download/${CF_VER}/${CF_DEB}"

echo ">> [1/3] installing cloudflared ${CF_VER} (${CF_ARCH})"
if ! command -v cloudflared &>/dev/null; then
  curl -fsSL "$CF_URL" -o "/tmp/${CF_DEB}"
  dpkg -i "/tmp/${CF_DEB}"
  rm "/tmp/${CF_DEB}"
else
  echo "   cloudflared already installed: $(cloudflared --version)"
fi

echo ">> [2/3] writing systemd service"
cat > /etc/systemd/system/cloudflared-veritrade.service <<EOF
[Unit]
Description=Cloudflare Tunnel — VeriTrade (ftu.fyi)
After=network-online.target docker.service
Wants=network-online.target

[Service]
TimeoutStartSec=0
Type=simple
Restart=on-failure
RestartSec=10s
# Token stored here — not in this file
EnvironmentFile=/etc/cloudflared/veritrade.env
ExecStart=/usr/bin/cloudflared tunnel --no-autoupdate run --token \${TUNNEL_TOKEN}

[Install]
WantedBy=multi-user.target
EOF

echo ">> [2b/3] storing token in /etc/cloudflared/veritrade.env (mode 600)"
mkdir -p /etc/cloudflared
printf 'TUNNEL_TOKEN=%s\n' "$TUNNEL_TOKEN" > /etc/cloudflared/veritrade.env
chmod 600 /etc/cloudflared/veritrade.env

echo ">> [3/3] enabling and starting service"
systemctl daemon-reload
systemctl enable --now cloudflared-veritrade.service

echo ""
echo "Done. Check status:"
echo "  systemctl status cloudflared-veritrade"
echo "  journalctl -u cloudflared-veritrade -f"
echo ""
echo "If VeriTrade isn't running yet, start it first:"
echo "  bash ~/veritrade/run_on_jetson.sh   (or run_on_xavier.sh)"
