#!/usr/bin/env bash
# One command for the desktop demo: KIN backend (Muse speech-to-text) + the call overlay.
# Starts with NO family: the overlay opens on "Set up your family" and KIN learns the rest from the call.
# Quit from the overlay (or Ctrl-C here) and the backend stops too.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x backend/.venv/bin/uvicorn ]; then
  echo "backend venv missing: cd backend && python3.12 -m venv .venv && .venv/bin/pip install -e '.[dev]'" >&2
  exit 1
fi
if [ ! -d overlay/node_modules ]; then (cd overlay && npm install); fi
if [ "$(uname)" = "Darwin" ] && [ ! -x overlay/native/syscap ]; then (cd overlay && npm run build:native); fi

# Muse handles all 25 heritage languages with code-switching; Deepgram rejected Tamil streams in testing.
(cd backend && ASR_PROVIDER=muse .venv/bin/uvicorn app.main:app --port 8000) &
BACKEND=$!
trap 'kill $BACKEND 2>/dev/null' EXIT

for _ in $(seq 1 60); do curl -s -m 1 localhost:8000/health >/dev/null && break; sleep 0.5; done
curl -s localhost:8000/health >/dev/null || { echo "backend did not start" >&2; exit 1; }
echo "KIN backend up on :8000. Opening the overlay (Cmd/Ctrl+Shift+K hides it)."

(cd overlay && npx electron . "$@")  # extra args go to Electron, e.g. --remote-debugging-port=9333
