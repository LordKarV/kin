# KIN

A family-specific interpreter for calls between diaspora grandchildren and their grandparents.
Translates live, grounds every translation on *this family's* people, places and foods, remembers across calls,
and fades its own translation as the grandchild learns the language.

Plan: [KIN_BUILD_PLAN.md](KIN_BUILD_PLAN.md). Decisions: [docs/DECISIONS.md](docs/DECISIONS.md).

## Run

```bash
cp .env.example .env            # fill in MODEL_API_KEY, DEEPGRAM_API_KEY, ELEVENLABS_API_KEY
cd backend && python3.12 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
python -m app.smoke             # one structured completion from Muse Spark
uvicorn app.main:app --reload   # http://localhost:8000/health
```

```bash
cd frontend && npm install && npm run dev   # http://localhost:5173
```

Tests: `cd backend && pytest -q`. Eval: `cd backend && python -m eval.run_eval`.

## Architecture

```
Grandparent (laptop / phone)                                Grandchild (laptop)
        │ 16 kHz PCM over WebSocket (or Twilio ConversationRelay)         │
        ▼                                                                 ▼
   FastAPI CallSession ── per utterance ──────────────────────────────────┤
     1. ASR final (Muse Voice Transcribe | Deepgram nova-3 | typed)      │
     2. Linker: names, kin terms, dishes, places → family-graph nodes     │
     3. Fade policy: mastered words → passthrough (never inside a span)   │
     4. Grounded MT (Muse Spark, strict JSON): translation + spans + cards │
     5. TTS (ElevenLabs pcm_16000, consented clone) → peer                │
     6. Persist utterance + latencies; glossary audio; Fade exposures      │
        ▼
   SQLite/Postgres: families, people, aliases, edges, things, kin_terms, calls, utterances,
                    glossary, mastery (BKT), call_summaries, consents
        ▲
   React UI (Call · Family · Glossary · Fade)  ·  /connectors/muse.md + /api/v1/* (Muse connector)
```

Latency budget shown live in the UI: ASR final ≤ 400 ms · MT ≤ 700 ms · TTS first byte ≤ 400 ms · total p50 ≤ 2.0 s, p95 ≤ 3.0 s.

## Phone bridge (optional)
`ngrok http 8000`, put the hostname in `PUBLIC_WSS_HOST`, point the Twilio number's voice webhook at `https://<host>/twilio/voice`. The grandparent dials; the laptop hears English.

## Docs
[Demo script](docs/DEMO_SCRIPT.md) · [Devpost draft](docs/DEVPOST.md) · [Decisions](docs/DECISIONS.md) · [Eval results](backend/eval/results.md)

## Phone calls (merge KIN into the call)

The grandchild calls the grandparent as usual, taps **Add call**, dials KIN's Twilio number, and taps **Merge**.
KIN greets both people, then interprets turn by turn into the call (heritage language for the grandparent, English
for the grandchild). The grandchild's phone shows captions and who/what cards at `https://<host>/phone`.

```bash
cloudflared tunnel --url http://localhost:8000      # gives https://<random>.trycloudflare.com
# .env: PUBLIC_WSS_HOST=<random>.trycloudflare.com, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, ELEVENLABS_API_KEY
# Twilio console: the number's "A call comes in" webhook -> POST https://<host>/twilio/buddy
```

Desktop video calls (Zoom, Meet, FaceTime, WhatsApp desktop) use the overlay in `overlay/` instead.
