#!/usr/bin/env bash
# Push this working tree to the Vultr VM, (re)run setup, restart, and smoke-test.
# Usage: deploy/vultr/deploy.sh root@<server-ip>
# Never sends .env or databases; copy secrets once yourself: scp .env root@<server-ip>:/opt/kin/.env
set -euo pipefail

HOST="${1:?usage: deploy/vultr/deploy.sh root@<server-ip>}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
EXCLUDES=(--exclude .venv --exclude __pycache__ --exclude '*.egg-info' --exclude '*.db' --exclude '*.db-*'
          --exclude media --exclude eval/audio_out --exclude .pytest_cache --exclude '.env*')

ssh "$HOST" 'mkdir -p /opt/kin'
for dir in backend scripts deploy; do
  rsync -az --delete "${EXCLUDES[@]}" "$ROOT/$dir/" "$HOST:/opt/kin/$dir/"
done
ssh "$HOST" 'bash /opt/kin/deploy/vultr/setup.sh'

ip="${HOST#*@}"
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS -m 3 "http://$ip:8000/health"; then echo; exit 0; fi
  sleep 2
done
echo "backend did not answer on http://$ip:8000/health; check: ssh $HOST journalctl -u kin-backend -n 50" >&2
exit 1
