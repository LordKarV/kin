# KIN — Devpost draft

## Inspiration
Three of us have grandparents we can only half-talk to. Every call goes through a parent, or through a translator app that calls Ravi mama "uncle" and Paatti's rasam "soup". We wanted a translator that knows *our* family, and that gets out of the way as we learn.

## What it does
KIN is a live interpreter for calls between diaspora grandchildren and their grandparents, with two layers nobody ships:

1. **Family-grounded translation.** A per-family knowledge graph (people with kinship relations and nicknames, dishes, places, recurring events) built from the calls. Every translation is grounded on it: Tamil *mama* becomes "your uncle Ravi mama (Mom's younger brother)", and a bare "Ravi" resolves to the right one of the two Ravis using co-mentions, place and topic cues, what was said a moment ago, who is speaking, and even the honorific verb ending.
2. **Fade.** Per-word mastery (Bayesian Knowledge Tracing) decides, in real time, which heritage words the grandchild already knows and leaves them untranslated. Over weeks the English fades. *Apple's translator is a crutch. Ours is physical therapy.*

Plus memory across calls (summaries, extraction, a glossary of every idiom explained with audio) and a read-only Muse connector so you can ask "what did Ammamma say about her knee last week?".

## What exists and what we built
| Commodity (bought, not built) | Ours |
|---|---|
| Live speech translation (Apple Live Translation, Gemini Live, Meta Ray-Ban, NativeLeap, Nudge) | Family-graph grounding inside a live call |
| Code-switching ASR (Muse Voice Transcribe, Deepgram nova-3) | Kinship resolver + entity linker with name-collision scoring |
| Phone bridge pattern (Twilio ConversationRelay translation tutorial) | Fade: BKT mastery → passthrough policy with entity guardrails |
| TTS + voice cloning (ElevenLabs) | Memory with a privacy rule, glossary artifact, Muse connector brief |

Closest prior work: Khalilia et al. 2023 and Li et al. ACL 2024 document kin-term mistranslation; nobody we found fixes it inside a live call or fades translation with a learner model.

## Evals
See `backend/eval/results.md` (regenerate with `python -m eval.run_eval`). 105 Tamil sentences authored for the demo family (42 kin-term, 32 name-collision, 31 dish/place) and 83 idiom/register items (42 positive, 41 plain negatives).

_Latest run (replace with the live generic-vs-grounded run once MODEL_API_KEY is set):_

## Entity grounding (error rate, lower is better)

| Condition | Overall | Kin terms | Name collisions | Dishes/places | Kin flattening | MT p50 | MT p95 | API errors |
|---|---|---|---|---|---|---|---|---|
| linker-only (no LLM) | 2% (n=144) | 4% (n=53) | 3% (n=32) | 0% (n=40) | 0% | 3 ms | 49 ms | 0 |

## Idiom cards

| Condition | Precision | Recall | TP | FP | FN | n |
|---|---|---|---|---|---|---|
| linker-only (no cards in mock) | n/a | n/a | 0 | 0 | 42 | 83 |

Offline floor (no LLM at all): the linker alone reaches 2% entity error overall and 3% on name collisions, with 0% kin flattening.

## How we built it
- **Muse Spark 1.3** (Meta Model API, OpenAI-compatible, strict JSON-schema structured output, automatic prefix caching with the family roster as the stable prefix) for grounded translation, pragmatics cards, call summaries and extraction.
- **Muse Voice Transcribe** realtime WebSocket for Tamil/English code-switched ASR with family names as keywords; **Deepgram nova-3** as the alternative (Tamil monolingual + keyterms) when word timestamps matter.
- **ElevenLabs** flash v2.5 for live speech (Tamil supported), consent-gated instant voice clone.
- **FastAPI + SQLite** (Postgres a URL away), relational graph (nodes + edges), **Vite + React** single page, plain-WebSocket 16 kHz PCM transport (LiveKit kept as an optional adapter), **Twilio ConversationRelay** for the zero-install phone leg.
- Honest non-Meta choices are logged one line each in `docs/DECISIONS.md` (e.g. no embeddings endpoint on Meta Model API → alias/fuzzy linking + fuzzy memory search).

## Privacy
Audio is processed in short windows and discarded; only transcripts and the family graph persist, on the family's own account. Voice cloning requires the grandparent's recorded consent (the demo uses a teammate's voice). Health, money and conflict mentions are stored as a topic word only unless the grandchild taps "remember this". The Muse connector is read-only and key-revocable.

## What's next
Dialect adaptation (Madurai vs Chennai Tamil), more languages (the ontology and seed are data, not code), on-device ASR, and verified understanding from the conversation itself (did Arjun answer without a repeat?) instead of a tap.

## References
Khalilia et al. 2023 (lexical diversity in kinship across languages); Li et al., ACL 2024 (lexical gap detection, kinship terms); Kinbank (PLoS ONE 2023); PersonLink (KEOD 2015); text-fading adaptive training literature; Twilio ConversationRelay human-to-human translation tutorial (Feb 2025). Prior art acknowledged: Apple Live Translation, Google Gemini Live Translate, Meta Ray-Ban translation, NativeLeap, Nudge.
