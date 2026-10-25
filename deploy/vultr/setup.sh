#!/usr/bin/env bash
# Bootstrap (and re-run on every deploy) a Vultr Ubuntu 24.04 VM for KIN: backend + LiveKit on the public IP, no
# domain yet. Idempotent: secrets are generated once into /etc/kin and kept. Run as root; deploy.sh calls it.
set -euo pipefail

KIN=/opt/kin
ETC=/etc/kin
PUBLIC_IP="${PUBLIC_IP:-$(ip -4 route get 1.1.1.1 | awk '{for (i = 1; i < NF; i++) if ($i == "src") print $(i + 1)}')}"

apt-get update -qq
apt-get install -y -qq python3-venv python3-pip rsync ufw curl openssl >/dev/null

id kin >/dev/null 2>&1 || useradd --system --home "$KIN" --shell /usr/sbin/nologin kin
# The service runs as kin: it writes the DB (data/) and backend/media (mounted at startup; glossary audio, picture cache).
mkdir -p "$KIN/data" "$KIN/backend/media" "$ETC"
chown kin:kin "$KIN/data" "$KIN/backend/media"
if [ -f "$KIN/.env" ]; then chown root:kin "$KIN/.env"; chmod 640 "$KIN/.env"; fi

command -v livekit-server >/dev/null || curl -sSL https://get.livekit.io | bash

# Secrets: generated once, never committed. The phone needs KIN_API_KEY (Sign up > Server > Key).
if [ ! -f "$ETC/kin.env" ]; then
  lk_key="API$(openssl rand -hex 6)"
  lk_secret="$(openssl rand -hex 32)"
  cat >"$ETC/livekit.yaml" <<EOF
port: 7880
rtc:
  tcp_port: 7881
  port_range_start: 50000
  port_range_end: 60000
  use_external_ip: true
keys:
  $lk_key: $lk_secret
logging:
  level: info
EOF
  # Environment variables override the copied /opt/kin/.env (pydantic-settings), so these win for deployment.
  # DEV_ENDPOINTS=1 is safe here: with a real KIN_API_KEY the server is locked, so /api/dev/* answers loopback only.
  cat >"$ETC/kin.env" <<EOF
LIVEKIT_URL=ws://$PUBLIC_IP:7880
LIVEKIT_API_KEY=$lk_key
LIVEKIT_API_SECRET=$lk_secret
KIN_API_KEY=$(openssl rand -hex 16)
ASR_PROVIDER=muse
DEV_ENDPOINTS=1
DATABASE_URL=sqlite:///$KIN/data/kin.db
EOF
  chown root:kin "$ETC/livekit.yaml" "$ETC/kin.env"
  chmod 640 "$ETC/livekit.yaml" "$ETC/kin.env"
fi

# Firewall: SSH, backend, LiveKit signal + ICE/TCP + WebRTC UDP (ports from LiveKit's config-sample.yaml).
ufw allow 22/tcp >/dev/null
ufw allow 8000/tcp >/dev/null
ufw allow 7880:7881/tcp >/dev/null
ufw allow 50000:60000/udp >/dev/null
ufw --force enable >/dev/null

[ -d "$KIN/venv" ] || python3 -m venv "$KIN/venv"
"$KIN/venv/bin/pip" install -q --upgrade pip
"$KIN/venv/bin/pip" install -q -e "$KIN/backend[livekit]"

install -m 644 "$KIN/deploy/vultr/livekit.service" /etc/systemd/system/livekit.service
install -m 644 "$KIN/deploy/vultr/kin-backend.service" /etc/systemd/system/kin-backend.service
systemctl daemon-reload
systemctl enable --now livekit.service >/dev/null
systemctl enable kin-backend.service >/dev/null
systemctl restart livekit.service kin-backend.service

[ -f "$KIN/.env" ] || echo "WARNING: $KIN/.env is missing; copy your .env there (MODEL_API_KEY etc.) and re-run deploy.sh"
echo "KIN on http://$PUBLIC_IP:8000 and LiveKit on ws://$PUBLIC_IP:7880. KIN_API_KEY is in $ETC/kin.env."
