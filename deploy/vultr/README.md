# KIN on Vultr

The hosted backend for the submission: FastAPI and LiveKit on one Vultr VM, reachable from any network. The live demo
can still run on the local network for lower latency; see docs/DEMO_SCRIPT.md.

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
- In the app: Sign up > Server `http://<ip>:8000`, Key = that value. Or build the phones with the server baked in:
  `xcodebuild -project ios/Kin.xcodeproj -scheme Kin KIN_DEFAULT_SERVER=http://<ip>:8000 ...` (after `xcodegen generate`).
- Plant the demo worlds through an SSH tunnel, because a locked server answers `/api/dev/*` only to loopback callers.
  In one terminal run `ssh -N -L 8100:127.0.0.1:8000 root@<ip>`, then in another, from the repo root:
  `KIN_BASE=http://127.0.0.1:8100 KIN_KEY=<key> backend/.venv/bin/python scripts/seed_demo.py --part 1`.
  The tunnel address is loopback, so the printed sign-in links carry no `server=` and each phone keeps
  `http://<ip>:8000`.
- Save a snapshot right after seeding, on the server itself (the server's database is `/opt/kin/data/kin.db`):
  `ssh root@<ip> '/opt/kin/venv/bin/python /opt/kin/scripts/demo_snapshot.py save --db /opt/kin/data/kin.db --snapshot /opt/kin/data/kin.demo-snapshot.db'`.
  Restore between runs with the same command and `restore`. The in-app Demo reset instead looks for
  `/opt/kin/data/kin.demo-part1.db` and `kin.demo-part2.db`.
- Logs: `ssh root@<ip> journalctl -u kin-backend -u livekit -f`.

## Notes

- No domain yet, so traffic is plain HTTP and `ws://` to the IP (iOS App Transport Security does not apply to IP
  addresses). With a `.tech` domain, put Caddy in front for HTTPS and `wss://`, and set `LIVEKIT_URL` to the `wss://` host.
- Dev routes (`/api/dev/*`) are on so the demo driver can plant the story, but because the key is not the default
  they answer only loopback callers (the key travels in every invite link), and every `/api` route needs `KIN_API_KEY`.
- A Twilio number can point its SMS webhook at `http://<ip>:8000/twilio/sms` once `TWILIO_*` and `SMS_NUMBER` are set.
