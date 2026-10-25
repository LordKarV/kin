# Start here (for a second Claude session working outside the main build)

You are joining KIN, a hackathon project for the Meta track "Bringing People Closer Together with AI" (HackTX,
October 2026). Another Claude session is building the backend and the iOS app in parallel on branch
`feat/common-ground`. Your job is the non-coding and design work listed below, in your own folders, so the two of you
never edit the same files.

Read in this order:
1. `docs/PRODUCT.md`: the agreed product (source of truth). Read all of it.
2. `docs/collab/WORKING_RULES.md`: how to work in this repo (tools, git, style, verification).
3. `docs/collab/STORIES.md`: the demo cast and every story we have used so far.
4. The brief for your task: `docs/collab/DESIGN_BRIEF.md` and/or `docs/collab/EVAL_SCENARIOS_BRIEF.md`.

## KIN in one paragraph

Distance and language erode common ground: the shared context that makes talking easy. KIN is a common-ground engine
for calls between people who live apart (grandparents and grandkids, friends in other countries, friends at different
colleges, friend groups). During a video or audio call it models what each person knows about the other's world and
fills only the gaps, live, in each listener's language: a "who's that?" card when you have forgotten who Lin is, a
private "bridge" chip when your own news becomes relevant and the other person has not heard it, storyline cards,
translation when languages differ. Context comes from calls, plus an SMS number you can text updates to. It speaks only
when someone would be lost.

## Where things stand (2026-10-24)

| Branch | What is on it |
|---|---|
| `main` | Desktop call overlay (Electron), phone-merge mode (Twilio), family built as you go, 25-language kinship tables, Hindi/Indic matching fix |
| `feat/live-cards` | Instant culture cards on partial transcripts (~0.15 ms), split translation (p50 1.9 s, was 3.0 s), LiveKit call agent, `mobile/` web call app |
| `feat/common-ground` | The pivot: `docs/PRODUCT.md`, `docs/ARCHITECTURE.md`, and (in progress) the common-ground engine, connected graph, bridges, storylines, SMS, group calls, native iOS app (SwiftUI + LiveKit) |

Measured so far: generic AI gets the family member wrong 54% of the time on our eval, KIN 1%. Cards reach the screen
mid-sentence (about 2 s into a 3.5 s sentence). Translation p50 1.9 s.

Stack: FastAPI backend (Python 3.12), Meta Muse Spark (LLM) and Muse Voice Transcribe (speech-to-text, 25 languages),
ElevenLabs (voice), LiveKit (calls), Twilio (SMS), SwiftUI (iOS client, being built).

## Your boundaries (hard)

- Work on your own branch: `git checkout -b collab/design-and-eval origin/feat/common-ground` (or the current base the
  user tells you). Never commit to `feat/common-ground`, `main` or `feat/live-cards`.
- Only create or edit files in: `design/` (SwiftUI mockups), `eval_scenarios/` (test data), `docs/collab/`.
- Do NOT edit `backend/`, `ios/`, `mobile/`, `overlay/`, `frontend/` or other `docs/` files. The build agents are
  rewriting those right now; parallel edits to the same files are the main way this goes wrong.
- No secrets: never read or print `.env` files; nothing you make needs API keys.

## How your work gets used

- Design mockups in `design/` become the reference the iOS app is styled after (not merged as production code).
- Eval scenarios in `eval_scenarios/` get wired into the backend eval harness by the build session. Keep them as plain
  data files exactly as the brief describes, so wiring them in is easy.
- When you finish a piece, commit on your branch and tell the user; they will coordinate the merge.
