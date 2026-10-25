# KIN

Common ground for people who live apart.

KIN is a calling app for one-to-one calls between friends and family who live far from each other. During a call it
tracks what each person knows about the other's world and fills only the gaps, privately, in each listener's own
language. Most of the time it shows nothing: it speaks up only when someone would be lost.

Built at HackTX 2026 on Meta Muse Spark and Muse Voice Transcribe, with LiveKit, ElevenLabs, Twilio and SwiftUI.
Code written with Claude Code.

## What it does

- **Live captions in your language.** Grounded in who your people are, so a name like "Ravi" becomes "your uncle Ravi
  mama" and not just "uncle". Translation switches on only when two people's languages differ.
- **"Who's that?" cards.** When someone you have likely forgotten comes up, you get one quiet line on who they are.
  Heard it last week, and KIN stays quiet.
- **Bridges.** A private nudge when the conversation makes your own news relevant: "You haven't told Nithin: started
  bouldering." Only your own facts, never something someone else told you, and it clears once you say it.
- **Storylines and "Who is X?" cards.** Where an ongoing thread stands, and a one-tap way to add someone new.
- **Ask for more.** Double-twist the phone, or tap a word in a caption, for a card about what was just said.
- **Cultural meaning.** Tone and care, not just words.
- **Texts to KIN.** Text your own news to KIN in the app or by SMS; it stays private.
- **Pause and delete.** Everyone sees KIN is on and anyone can pause it. Audio is never kept, and deleted means gone.

## How it works

```
iPhone A ── LiveKit (one track per voice) ── Muse Voice Transcribe (partial and final transcripts)
                                                  │
           partials, milliseconds                 │ finals, about 3 s
           ▼                                      ▼
  name matcher ─ common-ground model ─ card picker ─ privacy guard     Muse Spark: grounded captions,
  (plain code, no model call, under 3 ms)                               card localization, fact extraction
           │                                      │
           └────────────── world graph: people, kinship, who heard what ┘
                                                  ▼
                                   iPhone B: its own card and caption
```

Muse is called for speech, captions, card localization, fact extraction, text parsing, bridge reranking and the
twist when its answer is unclear. Deciding who needs which card is plain code, so it runs on the partial transcript
in milliseconds and privacy is enforced in code rather than in a prompt.

## Results

Same Muse Spark model (muse-spark-1.3) on both sides of every comparison:

| Test | KIN | Without KIN's engine |
| --- | --- | --- |
| Names and relationships wrong in captions (105 family sentences, 150 entities) | 1% | 54% |
| Same-name people mixed up | 0% | 97% |
| Moments caught after three months of history (63 planted scenarios) | 26 of 27 | 22 of 27 |
| Private texts shown to the wrong person, same test | 0 | 2 |
| Median time to decide on a card, same test | 2.0 to 2.7 ms | 3.7 to 4.4 s |

Reports: `backend/eval/results.md` and `backend/eval/common_ground/results_live*.md`.

## Run it locally

```bash
cp .env.example .env    # set MODEL_API_KEY (Muse); ELEVENLABS_API_KEY and TWILIO_* are optional
cd backend && python3.12 -m venv .venv && source .venv/bin/activate && pip install -e ".[livekit]"
livekit-server --dev    # LiveKit on ws://localhost:7880
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Every setting is an environment variable (see `backend/app/config.py` and `.env.example`). Dev routes
(`/api/dev/*`, used to plant demo history) are off unless the server runs with `DEV_ENDPOINTS=1`.

The iOS app is in `ios/` (SwiftUI, LiveKit Swift 2.17.0). Generate the project and point it at a server with build
settings, so nothing is hardcoded:

```bash
cd ios && xcodegen generate
xcodebuild -project Kin.xcodeproj -scheme Kin -destination 'generic/platform=iOS' \
  KIN_DEFAULT_SERVER=http://<server>:8000 build
```

`KIN_DEFAULT_NAME`, `KIN_DEFAULT_LANG` and `KIN_DEFAULT_SIGNIN` pre-fill a demo phone the same way. The server can
also be typed under Sign up > Server.

## Demo

`scripts/seed_demo.py` plants two months of history for two demo worlds: part 1, two friends speaking English; part 2,
a grandson and his grandmother, who speaks Tamil. Every card shown changes what KIN thinks each person knows, so save
a snapshot right after seeding and restore it between runs:

```bash
cd backend && KIN_BASE='http://127.0.0.1:8000' .venv/bin/python ../scripts/seed_demo.py --part 1
.venv/bin/python ../scripts/demo_snapshot.py save       # after seeding
.venv/bin/python ../scripts/demo_snapshot.py restore    # between runs, with no call live
```

The in-app reset (People > gear > Demo) swaps in `kin.demo-part1.db` or `kin.demo-part2.db`, saved next to the
server's database.

The live script is in [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md).

## Deploy on Vultr

One VM runs the backend and LiveKit, reachable from any network. Step by step:
[deploy/vultr/README.md](deploy/vultr/README.md).

```bash
deploy/vultr/deploy.sh root@<server-ip>
```

## Evaluation

```bash
cd backend && python -m eval.run_eval          # grounded captions vs the same model without KIN's graph
cd backend && python -m eval.run_cg --live     # common-ground decisions vs one model call with the full history
```

## Repository

| Path | What it is |
| --- | --- |
| `backend/` | FastAPI server: calls, speech, the common-ground engine, captions, texts, privacy |
| `ios/` | The KIN iPhone app (SwiftUI) |
| `deploy/vultr/` | Server setup, deploy script and systemd units |
| `scripts/` | Demo seeding and snapshots, kinship-table builder |
| `backend/eval/`, `eval_scenarios/` | Evaluation harness and its test data |
| `design/` | Design source, brand assets and mockups |
| `overlay/`, `frontend/`, `mobile/` | Earlier clients (desktop call overlay, web UI, React Native), kept for reference |
