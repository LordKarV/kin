# Devpost submission draft: KIN

Replaces the old translation-first story in docs/DEVPOST.md. Items marked [CONFIRM] depend on what runs end to end at
the feature freeze; delete the line if it does not.

**Name:** KIN

**Tagline:** Common ground for people who live apart.

**Prize opt-ins:** Meta: Bringing People Closer Together with AI; Best Overall; Best Pitch (if presenting).

**Video:** [public YouTube link]  **Repo:** https://github.com/LordKarV/hacktx

---

## Inspiration

Six weeks after a call, a friend in Shanghai says "Lin and I finally did the trip." You nod, because asking who Lin is
feels like admitting you weren't listening. She told you. You forgot. And she has no idea you started bouldering,
because you told a different friend.

Psychologists call what two people both know, the thing that makes conversation easy, common ground (Clark and
Brennan, "Grounding in communication", 1991). When people live apart it wears down: you lose track of who is in each other's lives, and your
own news reaches some people and not others. Add a language gap, as with a grandmother who speaks Tamil, and it wears
down faster. We wanted a calling app that notices those gaps and fills only them.

## What it does

KIN is an iOS calling app for one-to-one video and audio calls. It keeps a model of what each person on the call
knows about the other's world, and it speaks only when someone would be lost.

- **"Who's that?" cards.** When Mei mentions Lin, Arjun sees "Lin: Mei's friend from the Fudan climbing wall. She
  mentioned her Sept 14." If he heard about Lin last week, he sees nothing. Mei never sees a card about her own
  friend.
- **Bridges.** When Mei talks about climbing, Arjun alone gets a private chip: "You haven't told Mei: you started
  bouldering." KIN knows he told Priya and not Mei. Bridges only ever use your own facts. [CONFIRM]
- **Captions in each listener's language.** Captions are on by default; a translated voice is an optional toggle.
  Translation is grounded in who people are: "your uncle Ravi mama (Mom's younger brother)", not "uncle".
- **Cross-world cards.** When Arjun tells his grandmother "Mei and I went hiking", she gets a card in Tamil: "Mei:
  Arjun's friend from high school, now in Shanghai." [CONFIRM]
- **Texts about your own life.** Text KIN "started bouldering" and it updates your world. Texts are private and never
  forwarded. [CONFIRM]

Nothing is pre-loaded. A new user starts with themselves and whoever they call.

## How it strengthens human connection

KIN does not schedule calls, send reminders, keep streaks or suggest topics before a call. It works inside a call the
two people already chose to have, and its output is something one person can say to the other: "wait, I actually
started bouldering." Each person sees only their own help. Most of the time KIN shows nothing.

## Why AI is essential (and where it isn't)

- **Muse Spark 1.3** (Meta Model API, strict JSON-schema output) does grounded translation, cultural-meaning cards
  ("you've gotten thin" from a grandmother is care) and fact extraction from calls. Without KIN's graph, the same
  model with the same input gets 54% of entity spans wrong on our Tamil family test set; with it, 1%.
- **Muse Voice Transcribe** does real-time speech recognition with Tamil-English code-switching, keyword biasing with
  names from the graph, and speaker separation.
- **Not AI:** finding names in a transcript is an alias table plus fuzzy matching (2% error on its own, 2 ms per
  sentence in the eval). Who-knows-what is knowledge tracing with forgetting, plain math. Cards on partial transcripts
  match in under a millisecond (p50 0.15 ms). The model is used where meaning is needed.

## How we built it

- **Backend:** FastAPI and SQLite. A world graph of people, places, events and storylines where every fact records
  who said it, who heard it and when. A knowledge model per (person, item) with forgetting, and a disclosure graph of
  who has heard each fact about you.
- **Calls:** LiveKit, with a server-side KIN participant that sends each listener their own captions and cards on a
  private data channel, and their own voice track only if they turned voice on.
- **Speech and language:** Muse Voice Transcribe streaming ASR; Muse Spark for translation, cards and extraction;
  ElevenLabs eleven_flash_v2_5 for the optional voice (a stock voice; no voice cloning).
- **Cross-script matching:** 林, Lin and Lynn resolve to one person, with segmentation-free matching for Chinese.
- **Kinship:** tables for all 25 Muse Voice Transcribe languages. Tamil is hand-verified and evaluated; the other 24
  are Muse Spark drafts marked "draft" in the UI.
- **App:** SwiftUI with LiveKit Swift.
- **Texts:** Twilio SMS into the same ingestion path. [CONFIRM]
- **Harness:** a live eval on 150 entity spans in 105 Tamil sentences, an offline mock eval that runs in CI, a pytest
  suite, and docs/DECISIONS.md with one line per non-obvious choice.
- **AI coding tools:** the code was written with Claude Code, from written specs (docs/PRODUCT.md,
  docs/ARCHITECTURE.md).

## Results

| On our 105-sentence Tamil family test set (muse-spark-1.3) | Generic (same model, same input, no graph) | KIN |
|---|---|---|
| Entity errors overall (n=150) | 54% | 1% |
| Kinship terms (n=54) | 72% | 4% |
| Two people with the same name (n=32) | 97% | 0% |
| Dishes and places (n=41) | 24% | 0% |
| Cultural-meaning card precision (n=83) | 90% | 100% |

Grounded caption latency is p50 3.0 s, p95 4.8 s per sentence. The test set was drafted with Claude and has not had a
native-speaker review yet.

## Privacy

- Everyone on the call sees KIN is on, and anyone can pause it.
- Audio is processed and discarded; only transcripts and extracted facts are kept.
- Bridges use only facts about you. KIN never suggests repeating what someone else told you.
- People who are discussed but are not users: only what was said, visible only to those who heard it, expiring after
  120 days unless pinned.
- Health, money and conflict are stored as a single topic word unless someone taps to keep the details.
- Every card lists the facts it uses, and a last-line check drops any card that cites a fact the listener cannot see.
- You can see, correct and delete what KIN holds about you; SQLite secure_delete is on.
- KIN never reads message histories.

## Challenges we ran into

- Caption latency. Muse Spark always reasons, and Muse Voice Transcribe ends a turn about 3.5 s after speech stops.
  WebRTC sends nothing during silence, so sentences sat unfinished; feeding silence to the ASR cut one transcript
  from 28.6 s to 9.4 s.
- A faster split translation path got p50 1.9 s but flattened 4% of kinship terms (vs 0%), so we kept the slower
  single call.
- Deciding when to stay quiet. A model with the whole history explains Lin every time she comes up; the knowledge
  model is what makes KIN silent the next day.
- Privacy across worlds: what Mei says in her calls can never reach Paatti, but who Mei is to Arjun can.

## Accomplishments we're proud of

- 54% to 1% entity errors, and 97% to 0% on same-name people, with the same model.
- Per-listener delivery: two people on one call see different, private help.
- A privacy rule enforced at delivery time, not only in prompts.
- [CONFIRM] Bridges and cross-world cards running end to end on real calls.

## What we learned

- The hard part was the listener, not translation: what does this person already know?
- Saying where AI is not needed made the system faster and easier to test.
- One-to-one calls with captions by default felt more human than a translated voice talking over someone.

## What's next

- Grow the common-ground eval (63 planted scenarios today; results in backend/eval/common_ground/results_live*.md): how often a card appears exactly when someone is
  missing something, and how often one person's words reach someone else, for KIN and for an AI given everyone's full
  history.
- Native-speaker review of the Tamil test set and of the 24 draft kinship tables, then evals beyond Tamil, starting
  with Mandarin.
- Storyline cards ("Mei's job search: applied in September, second round in October").
- A Muse connector, so Meta's Muse agent can answer "what hasn't Paatti heard from me yet?" from your own world.

## What's real today

[Fill at the feature freeze, one line per item: works end to end / works with a dev endpoint / not built.] Calls,
captions, grounded Tamil translation and the eval run on main. The common-ground engine is on feat/common-ground.

## Built with

meta-muse-spark, muse-voice-transcribe, livekit, elevenlabs, twilio, swiftui, swift, ios, python, fastapi, sqlite,
pydantic, rapidfuzz, claude-code
