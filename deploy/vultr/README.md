# KIN on Vultr

The hosted backend for the submission: FastAPI and LiveKit on one Vultr VM, reachable from any network. The live demo
still runs on the local network (lower latency); see docs/DEMO.md.

## 1. Create the server (Vultr dashboard)

- Cloud Compute, Shared CPU, Ubuntu 24.04 LTS, 2 vCPU / 4 GB is plenty.
- Region: Dallas (closest to Austin).
- Add your SSH public key under SSH Keys, then deploy and note the IPv4 address.

## 2. Copy your secrets (once)

The deploy script never sends `.env`. Copy it yourself from the repo root:

```bash
ssh root@<ip> 'mkdir -p /opt/kin' && scp .env root@<ip>:/opt/kin/.env
```

## 3. Deploy (and redeploy after every change)

```bash
deploy/vultr/deploy.sh root@<ip>
```

It copies `backend/`, `scripts/` and `deploy/` (no databases, no `.env`), runs `setup.sh` on the server, restarts both
services and checks `http://<ip>:8000/health`. `setup.sh` is idempotent: on the first run it installs Python and
LiveKit, opens the firewall (22, 8000, 7880-7881/tcp, 50000-60000/udp) and generates fresh LiveKit keys and a
`KIN_API_KEY` into `/etc/kin/kin.env`. Those override anything in `.env`.

## 4. Use it

- Read the app key: `ssh root@<ip> grep KIN_API_KEY /etc/kin/kin.env`.
- In the app: Sign up > Server `http://<ip>:8000`, Key = that value.
- Demo driver against the server: `KIN_BASE=http://<ip>:8000 KIN_KEY=<key> backend/.venv/bin/python scripts/demo_common_ground.py`.
- Logs: `ssh root@<ip> journalctl -u kin-backend -u livekit -f`.

## Notes

- No domain yet, so traffic is plain HTTP and `ws://` to the IP (iOS App Transport Security does not apply to IP
  addresses). With a `.tech` domain, put Caddy in front for HTTPS and `wss://`, and set `LIVEKIT_URL` to the `wss://` host.
- Dev routes (`/api/dev/*`) are on so the demo driver can plant the story, and every `/api` route needs `KIN_API_KEY`
  because the key is not the default.
- A Twilio number can point its SMS webhook at `http://<ip>:8000/twilio/sms` once `TWILIO_*` and `SMS_NUMBER` are set.
