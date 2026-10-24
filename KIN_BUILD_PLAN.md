# KIN — Build Plan for Claude Code

> A family-specific interpreter for calls between diaspora grandchildren and their grandparents.
> It translates live, grounds every translation on *this family's* people, places and foods, remembers across calls, and fades its own translation as the grandchild learns the language.
>
> Target: Meta / Facebook track, "Bringing People Closer Together with AI". 24-hour build, team of 2–4.

---

## 0. How to use this file with Claude Code

1. Create an empty repo, drop this file in as `PLAN.md`, and create a `CLAUDE.md` from §12.
2. Work phase by phase (§6). Each phase has **acceptance criteria**; do not start the next phase until the current one passes.
3. Tell Claude Code: *"Read PLAN.md. We are on Phase N. Implement it, run the acceptance checks, then stop and report."*
4. Anything marked **VERIFY** is an external API detail that must be confirmed against live docs before coding — never invented. Anything marked **FALLBACK** is a pre-decided plan B; switch to it immediately if the primary blocks you for more than 45 minutes.
5. Keep `docs/DECISIONS.md` updated (one line per decision). Judges and teammates read it.

---

## 1. The thesis (what you're actually building)

Every shipped product (Apple Live Translation, Google Gemini Live Translate, Meta Ray-Ban translation, Samsung, plus multiple prior hackathon projects) translates **words**. None of them know **your family**. KIN's contribution is two layers on top of commodity translation:

1. **Family-grounded translation.** A per-family knowledge graph (people with kinship relations, nicknames, places, dishes, recurring events) built from the calls themselves. Translations are grounded on it, so Telugu *mama* becomes "your uncle Suresh (Mom's brother)" instead of "uncle", and "Ravi" resolves to the right Ravi. The failure mode is documented in the literature (Khalilia et al. 2023; Li et al. ACL 2024); nobody has fixed it inside a live call.
2. **Fade.** Per-word mastery tracking (Bayesian Knowledge Tracing) drives a real-time policy that lets mastered words pass through untranslated. Over weeks the English fades. Pitch line: *"Apple's translator is a crutch. Ours is physical therapy."*

Everything else — the live translation pipeline, dial-a-number bridge, code-switching ASR — is **bought, not built**, and we say so in the Devpost.

**What to claim:** "No shipped product or prior hackathon project we found grounds live translation on a family graph or fades translation with a learner model. Closest work: [links]."
**What not to claim:** "First-ever real-time translation." Judges search Devpost.

---

## 2. Judging criteria → design decisions

| Criterion | How KIN hits it |
|---|---|
| Meaningfully strengthens human connection | Grandparent ↔ grandchild, across a language gap, with memory across calls and a learning loop so the gap closes over time |
| AI essential & well-integrated | ASR → grounded MT → TTS pipeline; entity extraction builds the graph; BKT policy; three models with distinct jobs |
| Originality | Family graph grounding + Fade (see §1) |
| Strength of working demo | Live two-laptop call on stage; grounded-vs-generic side-by-side; week-1 vs week-8 Fade toggle; glossary artifact with audio |
| Meta tool usage (soft criterion, Meta judges) | Muse Spark 1.1 for all reasoning/translation/extraction; Muse connector so Muse can query the family memory; Muse Voice Transcribe if it fits; Seamless as optional S2ST |

---

## 3. Tech stack — Meta where it fits, better tools where it doesn't

Principle: **use Meta's stack where it is at least as good; use the better tool where it isn't, and write down why.**

### 3.1 LLM: Muse Spark 1.1 via Meta Model API — **USE**
- OpenAI-compatible API, model id `muse-spark-1.1`, supports structured outputs, parallel tool calls, prompt caching, ~1M context. $20 free credits per new account (each teammate signs up → 4× credits). US-only preview.
- **VERIFY**: base URL, auth header, structured-output parameter name, rate limits. Read developer.meta.com docs; do not guess the endpoint.
- Use the OpenAI SDK pointed at Meta's base URL. Put model + base URL in env so you can swap to any OpenAI-compatible model at 3 a.m.
- Jobs: translation (grounded), entity/relationship extraction, idiom/pragmatics detection, glossary generation, call summaries, Muse-connector answers.
- **FALLBACK**: any OpenAI-compatible model via the same client. Nothing else changes.

### 3.2 ASR: Deepgram (primary) / Muse Voice Transcribe (if API is live and streaming) — **DECIDE IN HOUR 1**
- Need: streaming, word timestamps, speaker labels, code-switching. Deepgram documents a multi-language code-switching mode (`language=multi`) plus keyterm prompting; it is proven for Hinglish and has a known streaming SDK. Telugu/Tamil coverage: **VERIFY** language list; if the heritage language isn't supported in `multi`, fall back to monolingual streaming in that language plus keyterms for the English words.
- Muse Voice Transcribe: the hackathon lists it as "real-time audio perception". **VERIFY** at the venue: streaming WebSocket? word timestamps? language list? If yes to all three, use it (Meta judges). If no, Deepgram — and write the reason in DECISIONS.md. Do not spend >60 min on this decision.
- **FALLBACK**: faster-whisper on a GPU box with 2-second chunks (no true streaming; acceptable for demo).

### 3.3 TTS / voice: ElevenLabs (primary) — **USE**, Seamless optional
- ElevenLabs instant voice cloning + multilingual streaming TTS gives "grandma's voice in English" in ~1 hour of integration. Consent-gated (see §9).
- Meta Seamless (SeamlessM4T v2 / SeamlessStreaming / SeamlessExpressive) is the Meta-native path for speech-to-speech with prosody preservation. **Only** pursue if one teammate can get SeamlessM4T v2 running on a Modal/RunPod GPU in ≤2 hours as a side quest. If it works, offer it as a second "Meta-native" audio path in the demo. **VERIFY** model licenses (non-commercial research licenses are fine for a hackathon; note it).
- **FALLBACK**: ElevenLabs without cloning (stock multilingual voice).

### 3.4 Real-time transport: LiveKit (primary) + Twilio (phone bridge) — **USE**
- LiveKit Cloud room for the two-laptop demo; LiveKit Agents framework for the server-side pipeline agent (VAD → ASR → MT → TTS). Mature, Python SDK, handles echo/jitter.
- Twilio ConversationRelay or Media Streams for the **zero-install elder path** (grandparent dials a normal number). Twilio has a published human-to-human translation tutorial on ConversationRelay — follow its architecture (two independent relay sessions bridged by your app).
- **FALLBACK** if LiveKit fights you: plain WebSocket audio (16 kHz PCM) between two browser clients and your FastAPI server. Uglier, but the demo is two laptops you control.
- Phone bridge is Phase 5 (nice-to-have). If skipped, the pitch still says "designed for a plain phone call" with the architecture diagram.

### 3.5 Backend / data
- Python 3.11, FastAPI, uvicorn. Postgres (Supabase free tier, or local Docker) with pgvector. SQLite is acceptable for a 24-hour build if Supabase auth friction appears.
- Graph stored relationally (nodes + edges tables), not Neo4j. Embeddings via any OpenAI-compatible embedding endpoint (**VERIFY** whether Meta Model API exposes embeddings; otherwise use a small open model like `bge-m3` locally — it's multilingual, which matters).

### 3.6 Frontend
- Next.js (or plain Vite + React) single page: call view (live transcript, grounded translation, pragmatics cards), family graph view, glossary, Fade dashboard. Mobile-width friendly. Keep it to one page with tabs.

### 3.7 Image: Muse Image — **USE IF AVAILABLE, OTHERWISE SKIP**
- Only for glossary illustrations and the family-tree avatar cards. As of July 2026 Muse Image was not in the API; **VERIFY** at the venue. Not load-bearing; skip entirely if it costs >30 min.

### 3.8 Muse connector — **USE (Phase 6)**
- Muse builds a custom connector from a service's API plus an agent-readable "connector brief" markdown and a stored credential. KIN exposes 3 read endpoints + a brief at `/connectors/muse.md`. Demo line: *"Muse, what did Ammamma say about her knee last week?"*
- **VERIFY** the current custom-connector flow in the Muse app (Settings → Connectors) on a teammate's phone before the demo. Record a screen capture as backup.

---

## 4. Architecture

```
Grandparent (laptop / phone)                         Grandchild (laptop)
        │ audio                                               │ audio
        ▼                                                     ▼
   LiveKit room  ◄──────────── KIN Agent (Python) ────────────►  LiveKit room
   (or Twilio bridge)              │
                                   │ 1. VAD + 2s windows
                                   │ 2. ASR (Deepgram multi) → words, ts, speaker, lang tags
                                   │ 3. Entity linker: match spans → family graph (names, kin terms, dishes, places)
                                   │ 4. Fade policy: per-word mastery → translate | passthrough
                                   │ 5. Grounded MT (Muse Spark, structured output): {translation, grounded_spans[], pragmatics_cards[]}
                                   │ 6. TTS (ElevenLabs, cloned voice) → audio to the other side
                                   │ 7. Async: extraction job → graph upserts; glossary upserts; call log
                                   ▼
                        Postgres: families, people, edges, aliases, dishes/places,
                                  utterances, glossary, mastery (BKT), call_summaries
                                   ▲
         Web UI (Next.js) ◄────────┤────────►  /connectors/muse.md + /api/v1/* (Muse connector)
```

Latency budget (show it live in the UI): VAD end → ASR final ≤ 400 ms; MT ≤ 700 ms; TTS first byte ≤ 400 ms; total p50 ≤ 2.0 s, p95 ≤ 3.0 s.

---

## 5. Repo layout

```
kin/
  CLAUDE.md
  PLAN.md                      # this file
  docs/DECISIONS.md
  docs/DEMO_SCRIPT.md
  docs/DEVPOST.md
  backend/
    app/
      main.py                  # FastAPI
      config.py                # env, model ids, base urls
      db/ (models.py, migrations/, seed.py)
      graph/                   # family graph: schema, kinship ontology, linker
        ontology.py            # kin term → relation (seeded from Kinbank-style tables)
        linker.py              # span → node matching (aliases + embeddings)
        extract.py             # Muse Spark structured extraction → upserts
      mt/
        translate.py           # grounded translation prompt + schema
        pragmatics.py          # idiom/register card detection
      fade/
        bkt.py                 # Bayesian Knowledge Tracing
        policy.py              # per-token translate/passthrough decision
      audio/
        asr.py                 # Deepgram (or Muse Voice Transcribe) streaming
        tts.py                 # ElevenLabs streaming + voice clone
        agent.py               # LiveKit Agents pipeline
        twilio_bridge.py       # Phase 5
      api/
        calls.py, graph.py, glossary.py, fade.py, connector.py
    tests/
    eval/
      testset/                 # kinship_names_dishes.jsonl, idioms.jsonl, codeswitch_audio/
      run_eval.py              # generic vs grounded; idiom P/R; latency
      results.md               # auto-generated table → paste into Devpost
  frontend/
    (Next.js app)
  scripts/
    seed_family.py             # the demo family
    make_testset.py
```

---

## 6. Build phases (24 hours)

Timings assume 4 people. With 2–3, drop Phase 5 and Phase 7's Muse Image bits.

### Phase 0 — Setup (0:00–0:45)
- Repo, Python env, FastAPI hello, Next.js hello, Postgres up, `.env.example`.
- Every teammate: Meta Model API account (credits), Deepgram, ElevenLabs, LiveKit Cloud, Twilio trial.
- `config.py`: `LLM_BASE_URL`, `LLM_MODEL=muse-spark-1.1`, `ASR_PROVIDER`, `TTS_PROVIDER`.
- Smoke test: one Muse Spark chat completion with structured output. **VERIFY** structured-output param here; record in DECISIONS.md.
- **Accept:** `curl /health` OK; `python -m app.smoke` prints a JSON object from Muse Spark.

### Phase 1 — The demo family + test set FIRST (0:45–2:00)
Write the data before the pipeline. This is what makes the eval possible.
- `scripts/seed_family.py`: a fictional but realistic family (pick the heritage language your demo speaker actually speaks — Telugu, Tamil, Hindi, Spanish, Vietnamese…). ~12 people, with two people sharing a first name (the Ravi problem), 6 dishes, 4 places, 3 recurring events, nicknames.
- Kinship ontology for that language: a table of kin terms → structured relation (e.g. Telugu `mama` → mother's brother; `babai` → father's younger brother; `attha` → father's sister / mother-in-law, context-dependent). Seed from Kinbank-style resources; 20–40 terms is enough.
- `eval/testset/kinship_names_dishes.jsonl`: 100 source sentences in the heritage language (or romanized), each tagged with the entities it contains and the *expected grounded rendering*. At least 40 must contain a kin term, 30 a name collision, 30 a dish/place. Write them with a native speaker on the team; have Muse Spark draft, human-correct.
- `eval/testset/idioms.jsonl`: 40 idioms/proverbs/honorific-register cases with expected card text; plus 40 plain sentences as negatives (for precision).
- Record 20 short code-switched audio clips with a teammate for latency/ASR checks.
- **Accept:** `python scripts/seed_family.py` populates DB; test files validate against a Pydantic schema.

### Phase 2 — Grounded translation core (2:00–7:00)  ← the technical heart
- `graph/linker.py`: given ASR words, find candidate spans that are names, kin terms, dishes, places. Match by alias table (exact/fuzzy, romanization-tolerant) then embeddings for the rest. Return `[{span, node_id, type, confidence}]`.
- Name disambiguation: use conversational context (who's speaking, last-mentioned entities, kin term adjacency: "Ravi mama" vs "Ravi anna"). Keep a per-call `salience` map.
- `mt/translate.py`: Muse Spark structured output:
  ```json
  {
    "translation": "...",
    "grounded_spans": [{"source": "mama", "rendered": "your uncle Suresh (Mom's brother)", "node_id": "p_suresh"}],
    "pragmatics_cards": [{"kind": "idiom|register|honorific", "source": "...", "literal": "...", "meaning": "...", "why_it_matters": "..."}],
    "confidence": 0.0
  }
  ```
  Prompt includes: the linked entities with their relations to the *listener*, the last 6 utterances, speaker identities, and the rule "never flatten a kin term to a generic English word when a linked node exists."
- `eval/run_eval.py`: run **generic** (same model, no graph context) vs **grounded** on the 100-sentence set. Metrics: entity rendering error rate (exact match against expected rendering, case/punct-insensitive), kin-term flattening rate, name-collision error rate. Also idiom card precision/recall on the 80-item set. Write `eval/results.md`.
- **Accept:** grounded beats generic by a clear margin on entity error rate (target: generic ≥40% error on kin/name items, grounded ≤10%). If grounded isn't winning, fix the linker before touching anything else.

### Phase 3 — Live pipeline (parallel with Phase 2; 2:00–9:00)
- `audio/asr.py`: streaming ASR with word timestamps + speaker + language tags. Deepgram `multi` with keyterms = the family's names and dishes (pull from DB at call start — this alone improves ASR on names).
- `audio/tts.py`: ElevenLabs streaming; voice clone created from a 60-second consented sample at onboarding.
- `audio/agent.py`: LiveKit Agents worker: VAD → 2s windows → ASR final → linker → fade policy → MT → TTS → publish to the other participant. Emit a `transcript` data message to the UI with the full structured object + per-stage latencies.
- **Accept:** two laptops in one room; teammate speaks heritage language; other laptop hears English in cloned voice within p50 ≤ 2.5 s (tighten later); UI shows transcript + grounded spans highlighted.

### Phase 4 — Fade (9:00–14:00)
- `fade/bkt.py`: standard BKT per (learner, lemma): params `p_init=0.1, p_learn=0.2, p_slip=0.1, p_guess=0.2`. Update on each *exposure* (word was heard) and on each *evidence of understanding* (learner responded appropriately without asking for repeat, or passed a 1-tap "did you get it?" check in the UI). Keep it simple and honest: exposures count weakly, verified understanding counts strongly.
- `fade/policy.py`: before MT, for each heritage-language token with mastery ≥ 0.85, mark `passthrough`. MT prompt receives the list of passthrough tokens and is instructed to leave them in the original language in the output (with a tooltip in the UI). Guardrail: never passthrough inside a grounded entity span or a pragmatics-card span.
- UI: mastery curve per word; a "weeks elapsed" demo control that replays the learner's history at 1×/8× to show the same sentence rendered at week 1 vs week 8. (Demo control is clearly labeled as a simulation of accumulated history, not a cheat: it feeds real recorded exposures through the real BKT.)
- **Accept:** `tests/test_bkt.py` passes known-value cases; the demo toggle visibly reduces translated words on the fixed demo sentence; passthrough never breaks a grounded span.

### Phase 5 — Zero-install phone bridge (14:00–17:00) — optional
- Twilio ConversationRelay (or Media Streams) → your agent, bridged to the LiveKit participant or to a second relay session. Grandparent dials a Twilio number; nothing to install.
- **Accept:** a real phone dials in, speaks, the laptop hears English. If not working by 17:00, stop and keep the architecture slide.

### Phase 6 — Memory + Muse connector (17:00–19:30)
- After each call: Muse Spark summary → `call_summaries`, plus entity/relationship extraction → graph upserts (new people, new dishes, health mentions flagged as sensitive and stored only with an explicit "remember this" from the grandchild — see §9).
- Endpoints (read-only, API-key auth):
  - `GET /api/v1/family/graph`
  - `GET /api/v1/calls/recent?limit=5`
  - `GET /api/v1/memory/search?q=...` (embedding search over utterances + summaries)
  - `GET /api/v1/glossary`
- `/connectors/muse.md`: a brief describing the endpoints, auth, safety rules ("read-only", "never echo the key"), and example prompts. Mirror the structure other services publish for Muse.
- On a teammate's phone: add KIN as a custom connector in Muse; test "What did Ammamma say about her knee last week?" and "What does *gongura* mean in my family?" Screen-record it.
- **Accept:** Muse answers both prompts from KIN data (or the screen recording exists).

### Phase 7 — Artifact, polish, evals (19:30–22:00)
- Glossary page: every pragmatics card ever shown, with the original audio clip, the literal, the meaning, who said it, when. Optional Muse Image illustration per entry.
- Family graph page: tree view with kin terms in both languages on the edges.
- Latency panel: live p50/p95 per stage.
- Re-run `eval/run_eval.py`, paste `results.md` into `docs/DEVPOST.md`.
- **Accept:** results table present; UI works at phone width; no console errors.

### Phase 8 — Demo rehearsal (22:00–24:00)
- Run `docs/DEMO_SCRIPT.md` three times end to end. Record a clean backup video. Pre-warm all services. Put API keys for two teammates' accounts in env so one exhausted credit pool doesn't kill the demo.

---

## 7. Data model (Postgres)

```sql
families(id, name, heritage_lang, created_at)
people(id, family_id, display_name, lang_name, gender, birth_year_approx, notes)
aliases(person_id, alias, lang, kind)            -- nicknames, romanizations
edges(src_person, dst_person, relation, lang_term) -- relation in ontology terms; lang_term = how the family says it
things(id, family_id, kind, name, aliases[], note) -- dish | place | event
kin_terms(family_id, lang, term, relation_pattern, notes)
calls(id, family_id, started_at, ended_at, participants[])
utterances(id, call_id, speaker_id, t_start, t_end, src_text, src_lang_tags, translation, grounded_spans jsonb, cards jsonb, audio_url, latencies jsonb)
glossary(id, family_id, card jsonb, utterance_id, created_at)
mastery(learner_id, lemma, p_known, n_exposures, n_verified, updated_at)
call_summaries(call_id, summary, extracted jsonb, approved boolean)
consents(person_id, voice_clone boolean, memory boolean, signed_at)
```

---

## 8. Prompts (starting points — iterate against the eval)

**Grounded translation (system):**
> You translate live speech between a grandparent and grandchild. You receive the source utterance, the speaker, the listener, linked family entities with their relation *to the listener*, recent context, and a list of passthrough tokens. Rules: (1) Render every linked kin term as the specific person and relation to the listener, never a generic word. (2) Keep passthrough tokens in the source language verbatim. (3) Emit a pragmatics card only when a literal translation would lose meaning (idiom, proverb, honorific/register shift). Otherwise emit none. (4) Output JSON matching the schema. Be brief; this is spoken aloud.

**Extraction (post-call):**
> From this transcript, extract new people (with how the speaker refers to them and inferred relation), dishes, places, events. Return JSON. Mark anything about health, money, or conflict as `sensitive: true` and do not include details beyond the topic word.

Prompt caching: put the family graph context in the cached prefix; only the utterance changes per request.

---

## 9. Privacy & consent (one sentence each in the pitch)

- "Audio is processed in 2-second windows and discarded; only transcripts and the family graph persist, on the family's own account."
- Voice cloning requires the grandparent's recorded consent (store `consents.voice_clone`). The demo uses a teammate's voice.
- Health/money mentions are stored as topic-only unless the grandchild taps "remember this" after the call. Nothing is ever shared outside the family account.
- Muse connector is read-only and key-revocable.

---

## 10. Demo script (90 seconds + Q&A)

1. (10s) One sentence of problem: "Three of us have grandparents we can't fully talk to."
2. (25s) Live call: teammate A speaks the heritage language into laptop 1; room hears English in A's cloned voice from laptop 2. Transcript shows **"mama" → "your uncle Suresh (Mom's brother)"** highlighted. Say: "Apple would say 'uncle'. We know which one."
3. (15s) Side-by-side panel: generic vs grounded on one sentence with a name collision. Show the eval table number.
4. (15s) Fade: flip the week-1/week-8 control; same sentence, half the words now pass through in the heritage language; mastery curve visible.
5. (15s) Muse: on a phone, "Muse, what did Ammamma say about her knee last week?" → answer from KIN.
6. (10s) Close: privacy sentence + "the goal is for KIN to become unnecessary."

Backup: the recorded video for steps 2 and 5.

---

## 11. Devpost structure (`docs/DEVPOST.md`)

- **Inspiration** (3 sentences, personal)
- **What it does** (the two layers; one paragraph)
- **What exists and what we built**: explicit table — commodity (translation, phone bridge, code-switch ASR) vs ours (graph grounding, Fade, memory/connector). Link closest prior work (NativeLeap, Nudge, Twilio's translation tutorial, Apple Live Translation).
- **Evals**: paste `eval/results.md` (generic vs grounded error rates; idiom P/R; latency p50/p95).
- **How we built it**: stack with the Meta pieces named (Muse Spark 1.1, Muse connector, [Muse Voice Transcribe / Seamless if used]) and the honest reasons for non-Meta choices.
- **Privacy** (§9).
- **What's next**: dialect adaptation, more languages, on-device ASR.

---

## 12. CLAUDE.md (copy into repo root)

```markdown
# KIN — working agreements for Claude Code

- Read PLAN.md before any task. Work only on the phase named in the request.
- Never invent API endpoints, parameter names, or model IDs. If an external detail is unknown, say so and check docs; mark it VERIFY in docs/DECISIONS.md.
- All LLM calls go through app/llm.py (OpenAI-compatible client; base URL and model from env). No direct SDK calls elsewhere.
- All external calls have a timeout and a fallback path per PLAN.md §3.
- Structured outputs are validated with Pydantic; failures are logged, never silently swallowed.
- Every stage in the audio pipeline records latency into the utterance's `latencies` field.
- Keep the eval runnable at all times: `python -m eval.run_eval` must not break.
- Tests: pytest, fast, no network (mock providers). Run before claiming a phase is complete.
- One-line entries in docs/DECISIONS.md for every non-obvious choice.
- Do not add dependencies without noting why in DECISIONS.md.
- Privacy rules in PLAN.md §9 are hard constraints.
```

---

## 13. Risk register

| Risk | Trigger | Action |
|---|---|---|
| Meta Model API rate limit / credits | 429s or credit exhaustion | Second teammate's key in env; swap base URL to any OpenAI-compatible model |
| Heritage language unsupported in ASR `multi` mode | Phase 3 | Monolingual streaming + keyterms; note in DECISIONS |
| Grounded MT not beating generic | Phase 2 accept fails | Fix linker recall first (aliases, romanization), then prompt; do not proceed to Fade until it wins |
| LiveKit integration stalls | >45 min | WebSocket PCM fallback |
| Voice clone sounds bad | Phase 3 | Stock multilingual voice; keep clone as a toggle |
| Muse custom-connector flow changed | Phase 6 | Screen-record whatever works; worst case, show the brief + API in Postman |
| Demo network dies | Phase 8 | Backup video; local SQLite copy of the demo family |

---

## 14. References to cite in the Devpost

- Khalilia et al. 2023, *Lexical diversity in kinship across languages and dialects* (kin-term mistranslation failure mode)
- Li et al., ACL 2024, *Translation-based Lexicalization Generation and Lexical Gap Detection: Application to Kinship Terms*
- Kinbank (PLoS ONE 2023) — global kinship terminology database
- PersonLink (KEOD 2015) — multicultural family-relationship ontology
- Text-fading adaptive training literature (reading fluency) — precedent for adaptive fading
- Twilio ConversationRelay human-to-human translation tutorial (Feb 2025) — the phone-bridge pattern
- Prior art acknowledged: Apple Live Translation, Google Gemini Live Translate, Meta Ray-Ban translation, NativeLeap, Nudge
