# KIN call app (mobile)

A phone web app for the KIN call: the grandchild and grandparent talk over LiveKit and KIN interprets. Each person
hears the other's real voice, plus KIN's translation for them on top (the real voice ducks to 25% while KIN speaks).
Works in iPhone Safari and Android Chrome.

## Run

From a clean checkout, three terminals on the laptop:

```sh
cd backend && source .venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000
livekit-server --dev --bind 0.0.0.0
cd mobile && npm install && npm run dev
```

Open `https://<LAN-IP>:5174` on the phone (`ipconfig getifaddr en0` prints the Mac's LAN IP) and accept the
self-signed certificate once. The microphone needs a secure context, which is why the dev server uses HTTPS.

Vite proxies `/api` and `/media` to the backend on :8000 and `/rtc` (websocket) to LiveKit on :7880, so the phone
only ever talks to port 5174. When the backend's LiveKit URL is a `wss://` URL (LiveKit Cloud), the app connects
there directly instead.

## Call flow

1. Grandchild: open the app. With no family yet it shows the setup form; otherwise pick the family and tap
   **Call <name>**.
2. The call screen shows an invite link with **Copy link** and **Share** (the system share sheet). Send it to the
   grandparent. It looks like `https://<host>/?call=12&family=3&role=grandparent`.
3. Grandparent: open the link and tap the big **Join call** button. The tap is needed so the phone allows audio.
4. Hang up on either side to see the "Call ended" screen.

If the backend is locked with an API key, open the app with `?key=<key>`; the key is carried into the invite link.

## Develop

```sh
npm test        # node --test with type stripping (Node 24): cards, track routing, invite links
npm run build   # tsc -b && vite build
```
