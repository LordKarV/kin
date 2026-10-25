# KIN common-ground engine: build architecture

Status: final spec for the `feat/common-ground` build (base commit d58c76d). Product source of truth is
`docs/PRODUCT.md`; this file says how to build it. Every build agent reads PRODUCT.md, this file, and its own task spec.

Base design: "data-first" (one space, one canonical Person per human, Fact as the unit of provenance and visibility),
with the live-path mechanics of "realtime-first" and the guards of "privacy-correctness-first" grafted in. Section 0
lists every contradiction between the three designs and how it was resolved.

## Amendments (2026-10-24, from the user; these override anything below)

1. **One-to-one calls are the product.** Calls with more than two people must keep working (per-listener delivery is
   already the design), but nothing is optimized, featured or demoed around group calls. Where a section below
   describes group-call behavior, keep it correct but do not add extra group-specific work.
2. **Captions by default; translated voice is an optional per-person toggle, off by default.** TTS runs only for a
   listener who turned voice on. The preference is per call, in memory (no schema change): `POST
   /api/calls/{call_id}/voice {"on": bool}` with the caller identified by X-KIN-User, stored on the CallSession side
   (`Side.voice_on`, default False). Ducking of the other person's audio and `audio_start`/`audio_end` only happen for
   listeners with voice on. The iOS call screen shows a voice toggle next to the captions.
3. **Bridges use only the listener's own facts.** Example to test: in Arjun's call with Paatti, "You haven't told
   Paatti: you went hiking with Mei when she visited" is allowed (Arjun's own experience); anything Mei said in her own
   calls is never suggested to anyone.
4. **The client is a native iOS app** (SwiftUI + LiveKit Swift 2.17.0) in `ios/`; `mobile/` (web) is frozen. Task
   specs in the plan already reflect this.
5. **On-demand context (tap a word in the caption).** `POST /api/calls/{call_id}/explain {"text": str, "utterance_id":
   int | null}` with the caller from X-KIN-User. The server runs the alias matcher (3.2) over `text` (the tapped word or
   span), resolves it with the same WorldView render and visibility rules as push cards for THIS listener, and returns
   `{"items": [GlanceItem]}` (a who/what/storyline/term card), or a single `kind: "ask"` item when the span matches
   nothing visible (the "Who is X?" flow), or `{"items": []}` when the span is not a name or term. It never returns
   anything the listener could not get as a push card. Each returned entity records ASKED evidence for this listener
   (knowledge model: the listener did not know it) and a card_log row with `via = "explain"`, so card dedupe, rate
   limits and the eval see it. Response is to the caller only; nothing is broadcast. Typed caption taps never change
   what other listeners see.
6. **Pause stays tiny:** the existing pause (`kin_status`) is one tap in the "KIN on" pill, visible to everyone in the
   call with who paused; no separate pause screen in the client.
7. **On-demand by gesture ("what's this about?").** `POST /api/calls/{call_id}/explain` also accepts `{"text": null,
   "recent": true}`. The server builds candidates from the last 4 final utterances the caller heard (not their own lines):
   alias-matcher hits, storyline keywords and relational spans, filtered by the same WorldView visibility and
   deliver_ok as push cards, scored by recency and (1 - p_know) for this listener; already-shown-this-call items rank
   lower, not out. If the top candidate beats the next by a clear margin (or is the only one), it is returned with no LLM
   call. Otherwise Muse Spark (app/llm.py, effort minimal, strict schema `{"choice": "<candidate id>" | "none"}`, 2.5 s
   timeout) gets those lines plus the candidate list (ids and display names only) and picks one; "none" widens the
   window to the last 12 utterances and repeats once; timeout or failure falls back to the top-ranked candidate. The LLM
   never sees facts the listener cannot see and can only return a candidate id. Same response shape and ASKED evidence
   as item 5; card_log via = "gesture". Empty result -> `{"items": []}` (client plays a soft "nothing" haptic).

Verified against the code while writing this (no files other than this one were changed):

- `pytest -q` is 197 passed in about 10 s. `python -m eval.run_eval --mock` exits 0 and its linker-only row is
  `| linker-only (no LLM) | 2% (n=150) | 4% (n=54) | 3% (n=32) | 0% (n=41) | 0% |`. That row is the regression pin.
- `db/session.py` already sets `PRAGMA foreign_keys=ON`, so `ondelete="CASCADE"` on new FKs is enforced on a fresh DB.
- `cards/glance.py::live_glance` returns early unless `side.role == "grandparent"` and broadcasts to every side;
  `glance_sent` is one call-wide set.
- `pipeline.process_utterance` awaits TTS inline to one peer and broadcasts the transcript to every side and watcher.
- `mt/translate.py:151` hard-codes "Tamil script" for any non-English target (wrong for Hindi; byte-identical for Tamil).
- `memory/service.py:142,151` calls `linker.link(name, "p_kamala", "p_arjun")`; `_slug` folds CJK/Tamil names to `p_x`.
- `rtc/agent.py::_join` drops participants whose metadata role is not grandparent/grandchild and has no client-to-agent
  data handler. `api/twilio.py::_verify_twilio(request, form)` exists. `/twilio/*` is a public prefix in `security.py`.
- `CardsOut` has one field; adding a field with a default keeps old mocks valid.

---

## 0. Decisions and resolved contradictions

| # | Question | Decision | Why |
|---|---|---|---|
| D1 | Tenancy | Keep `Family` as the tenant, called a **space** in new code (`families.kind = "space"`). One world space per install; every user and third party is one canonical `Person` row in it. The Krishnan seed stays as a separate `kind="family"` row for tests and eval. `Person.family_id` stays NOT NULL. | `FamilyGraph.from_session`, seed, eval and 197 tests keep working. Realtime-first's nullable `family_id` escapes `UniqueConstraint(family_id, slug)` in SQLite. |
| D2 | Two engines? | `Call.mode = "legacy" | "world"`. Legacy calls (`/ws/call`, overlay, phone merge, Twilio Relay, legacy `/api/rtc/join` body) run today's code byte-for-byte: old roster, old `live_glance`, old `_broadcast`. All new LiveKit calls are `world`, **including the Paatti segment**: Paatti is an ordinary Tamil-speaking user in the world space. | Feasibility wants untouched legacy tests; product wants one engine for the demo. Both hold: the legacy branch is the old code, the demo never uses it. |
| D3 | Identity keys | `CallSession.sides` is keyed by identity. Legacy callers pass the role string as the identity (`"grandparent"`), world calls use `f"p{person_id}"`. | No legacy caller changes; stable LiveKit identity evicts stale rejoins. |
| D4 | Structural knowledge | A hard gate checked **before** p (`structural_known`), never a decaying prior. | Realtime-first and privacy-first priors decay a person's own friend into a "reminder". |
| D5 | Half-life growth | Grows at most once per distinct UTC day of evidence. | One call must not stack half-lives. |
| D6 | Partials | In memory only (no DB, no LLM, no old `Linker`). A card needs the same entity at the same offset in 2 consecutive partials (or a final). `shown` evidence is applied only when the final confirms the mention; otherwise `glance_retract`. | Wrong partials must not poison dedupe or knowledge. |
| D7 | Dedupe | Per `(listener identity, card key)` per call. | Different listeners need different cards. |
| D8 | Bridge relevance | Concept-group keyword scan over folded text (works on unspaced 攀岩). Pass when one strong concept hits, or two concepts hit. Gap = binary disclosure (`S not in fact_audience(F)`), not p. Rerank flag exists, default **off**. No "first 20 s" window. | Data-first's whitespace token score gives the headline bridge a score of 1 and no chip. |
| D9 | Cross-world rule | `disclosable(F, S)`: the speaker's own shareable IDENTITY facts (`tie, lives_in, from, works_at, studies_at`) about themselves or an entity they just mentioned, plus the owner's own storyline states when the owner raises the storyline. | Keeps "Mei: Arjun's friend from high school, now in Shanghai" (when Arjun said it) without leaking what Mei said. |
| D10 | Storyline visibility | Not narrowed: the owner raising their own storyline discloses their own states. Third-party claims about the storyline stay audience-only. | PRODUCT: "Across circles KIN only shares YOUR facts". Owner states are the owner's facts. |
| D11 | Third-party TTL | `third_party_ttl_days = 120`. | Must exceed the 6-week demo gap (realtime-first's 30 days purges Lin before call 2). |
| D12 | Auth | `X-KIN-User: <token>` (random 32-byte token returned once by `POST /api/users`, stored as sha256). No self-asserted `me`. The KIN key gate stays. | Anyone with the key could otherwise read anyone's world. |
| D13 | Last-line guard | Every card carries internal `fact_ids`; `deliver()` drops and logs any card citing a fact that is neither visible to the listener nor disclosable by the current speaker. `card_log` records what was shown. | A leak bug becomes a dropped card plus a log line. |
| D14 | Extraction | Debounced (every 4 finals, 30 s idle, pause, call end) on its own 2-worker pool, with a validator (cited lines inside the window; a fact about a user only from that user's own lines; `same_as`/`contradicts` only to the speaker's own facts; drop, never guess). | Realtime-first's per-final extraction triples LLM load; Muse A alone is 1.9 s p50. |
| D15 | New-name "Who is X?" | From `CardsOut.new_people` on call B (already running per final per differing language), and from extraction for same-language calls. No extra per-final LLM call. | No MentionsOut call. |
| D16 | Transliteration | No new dependency. Extraction (and the place endpoint) returns `forms` for each new entity: native, romanization, English spelling, and the name in each connected user's script (max 8). Stored as `aliases(kind="translit")`. Nothing calls the LLM at match time. | pypinyin covers only zh; Muse covers all 25 languages in one call already being made. |
| D17 | Client-to-agent messages | None. Pause, card feedback and typed text go over REST (`/api/calls/{id}/pause|feedback|text`). | Avoids the unverified `data_received` shape; LiveKit only carries server-to-client data. |
| D18 | Rewording RULES | Not done. Legacy prompts stay byte-identical; world calls add a roster section and a neutral naming line only when `listener is None`. | Protects the eval headline numbers. |
| D19 | SQLite concurrency | `journal_mode=WAL`, `secure_delete=ON` pragmas. | Extraction threads write while handlers read; "deleted means gone". |
| D20 | Who owns `main.py` | Wave 1 task 1B registers every new router as a stub; later tasks fill the router modules and never touch `main.py`. Only the DECISIONS task writes `docs/DECISIONS.md`. | No same-wave file conflicts. |
| D21 | Hysteresis band | Not added. A shown card raises p to about 0.89, so the threshold is not crossed twice in one call. `ponytail:` note in code. | YAGNI; revisit if the eval sweep shows flicker. |
| D22 | Dev clock | `POST /api/dev/clock {offset_days}` sets a process-wide offset read by `world/clock.now()`. Demo and eval use it; no test-only clock injection. | The demo runs through the real server. |

Dev DB: `create_all` never alters tables. After this lands, run `rm backend/kin.db` once (logged in DECISIONS). Tests use a
temp DB per test and are unaffected.

---

## 1. Data model (`backend/app/db/models.py`)

`family_id` on new tables means space id. All new FKs to `people.id` use `ondelete="CASCADE"` unless marked `SET NULL`.
Timestamps are timezone-aware UTC. `world/clock.now()` (not `models.now`) supplies times written by world code.

### 1.1 Changes to existing tables

| Table | Action | Change |
|---|---|---|
| `families` | Keep (space) | Add `kind: str(8) = "family"` (`family` or `space`). `heritage_lang` = first user's language for a space; world code never reads it except as a linker fallback. |
| `people` | Keep (canonical person) | No new columns. Language and phone live on `users`. World code never writes `notes` or `cues`. World slugs: `prefix + "_" + ascii_fold(romanized name)[:24] + "_" + str(id)` set after flush (e.g. `p_lin_17`; all-CJK name gives `p_17`). Prefixes: `p` person, `pl` place, `ev` event, `th` thing, `g` group, `s` storyline. "node_id starting `p_` is a person" stays true. |
| `aliases` | Keep | New `kind` values `translit` and `asr`. `lang` = the form's language. |
| `edges` | Extend | `fact_id: int | None` FK facts `ondelete=CASCADE`. NULL = legacy or setup, visible to everyone in the space. |
| `things` | Extend | `owner_id: int | None` FK people CASCADE (whose world), `fact_id: int | None` FK facts CASCADE, `keys: JSON list[list[str]] = []` (concept groups, see 5). `kind` adds `org`, `activity`, `thing`. |
| `calls` | Extend | `mode: str(8) = "legacy"`. `participants` JSON kept and written; `call_participants` is the truth for world calls. |
| `utterances` | Extend | `lang: str(8) = ""`, `audience: JSON list[int] = []` (person ids present and not paused, speaker excluded), `translations: JSON dict = {}` (`{lang: text}`). `translation`/`listener_id` keep the first listener for legacy readers. |
| `mastery`, `call_summaries`, `glossary`, `kin_terms`, `languages`, `consents` | Keep unchanged | Fade, legacy end/approve, term cards, test pins. World mode never writes `call_summaries` or `consents`. |

### 1.2 New tables

```python
class User(Base):                       # a Person who has the app
    __tablename__ = "users"
    id: int pk
    person_id: int FK people.id CASCADE, unique
    lang: str(8)                        # spoken language, a MUSE_LANGUAGES code
    phone: str(20) | None, unique       # E.164 "+15125550101"
    token_hash: str(64), unique         # sha256 hex of the X-KIN-User token
    created_at: datetime

class Group(Base):                      # "Fudan crew"
    __tablename__ = "groups"
    id pk; family_id FK families; slug str(64); name str(120); lang_name str(120) = ""
    fact_id: int | None FK facts CASCADE
    UniqueConstraint(family_id, slug)

class GroupMember(Base):
    __tablename__ = "group_members"
    id pk; group_id FK groups CASCADE; person_id FK people CASCADE; fact_id: int | None FK facts CASCADE
    UniqueConstraint(group_id, person_id)

class Tie(Base):                        # social relation: "dst is src's <kind>"
    __tablename__ = "ties"
    id pk; family_id FK families
    src_person FK people CASCADE        # owner side: Mei in "Mei's friend Lin"
    dst_person FK people CASCADE
    kind: str(16)                       # friend|close_friend|partner|roommate|classmate|coworker|teammate|knows
    context: str(160) = ""              # "from the Fudan climbing wall" (English)
    status: str(8) = "active"           # active|ended
    fact_id: int | None FK facts CASCADE   # NULL only for setup rows
    created_at

class Fact(Base):
    __tablename__ = "facts"
    id pk; family_id FK families
    subject_id FK people CASCADE        # whose fact it is
    speaker_id: int | None FK people SET NULL   # who said/texted/tapped it
    predicate: str(16)                  # tie|lives_in|from|works_at|studies_at|did|started|plans|state|attribute|mention
    text: str(400)                      # short canonical English: "started bouldering"
    text_src: str(400) = ""             # original-language span ("" when sensitive)
    lang: str(8)
    keys: JSON list[list[str]] = []     # concept groups, each with multilingual forms: [["bouldering","climbing","攀岩","抱石"],["gym","岩馆"]]
    source_kind: str(8)                 # call|message|card|setup
    call_id: int | None FK calls SET NULL; utterance_id: int | None FK utterances SET NULL; message_id: int | None FK messages SET NULL
    said_at: datetime
    status: str(12) = "active"          # active|resolved|contradicted|superseded
    superseded_by: int | None FK facts SET NULL
    storyline_id: int | None FK storylines CASCADE
    sensitive_kind: str(8) = ""         # ""|health|money|conflict; when set, text = topic word, keys = []
    remembered: bool = False
    shareable: bool = True              # False for SMS facts: never disclosed by KIN to anyone but the author
    third_party: bool = False           # subject is not a user at write time
    expires_at: datetime | None         # said_at + third_party_ttl_days when third_party and not pinned
    pinned: bool = False
    Index(subject_id), Index(expires_at)

class FactAudience(Base):               # who has heard it: visibility AND disclosure, one table
    __tablename__ = "fact_audience"
    id pk; fact_id FK facts CASCADE; person_id FK people CASCADE
    via: str(8)                         # said|heard|authored|told|card
    at: datetime; call_id: int | None FK calls SET NULL
    UniqueConstraint(fact_id, person_id)

class FactRef(Base):                    # entities a fact mentions
    __tablename__ = "fact_refs"
    id pk; fact_id FK facts CASCADE; kind: str(10)  # person|thing|group
    ref_id: int; Index(kind, ref_id)

class Storyline(Base):
    __tablename__ = "storylines"
    id pk; family_id FK families; slug str(64)
    owner_id FK people CASCADE          # whose thread
    title: str(120)                     # "job search"
    keys: JSON list[list[str]] = []     # concept groups
    status: str(8) = "open"             # open|resolved
    unresolved: bool = False            # contradiction flag
    created_at; updated_at

class StorylineState(Base):
    __tablename__ = "storyline_states"
    id pk; storyline_id FK storylines CASCADE; seq: int
    label: str(80)                      # "second round"
    fact_id FK facts CASCADE, NOT NULL  # provenance and visibility come from the fact
    at: datetime
    status: str(12) = "active"          # active|superseded|contradicted

class Knowledge(Base):                  # common-ground state, one row per (knower, item)
    __tablename__ = "knowledge"
    id pk; knower_id FK people CASCADE
    item_kind: str(8)                   # person|thing|group|fact|state
    item_id: int
    p: float                            # P(knows) at last_at, after the update
    half_life_days: float
    first_at: datetime; last_at: datetime
    last_day: str(10)                   # "YYYY-MM-DD" (UTC) of last evidence; spacing rule
    n_heard: int = 0; n_shown: int = 0; n_said: int = 0; n_confirmed: int = 0; n_asked: int = 0
    UniqueConstraint(knower_id, item_kind, item_id)

class CardLog(Base):                    # what was delivered: rate limits, bridge "not again", eval, delete scans
    __tablename__ = "card_log"
    id pk; call_id FK calls CASCADE; listener_id FK people CASCADE
    target_id: int | None FK people SET NULL   # bridges: the person who has not heard it
    kind: str(10); key: str(80)
    fact_ids: JSON list[int] = []
    at: datetime; final: bool = False; retracted: bool = False

class Message(Base):                    # SMS, private to the author
    __tablename__ = "messages"
    id pk; family_id FK families; author_id FK people CASCADE
    body: Text = ""                     # cleared after a successful parse
    from_number: str(20); provider_sid: str(64) | None, unique   # Twilio MessageSid (idempotent retries)
    received_at: datetime
    status: str(8) = "received"         # received|parsed|failed
    reply: str(200) = ""; error: str(200) = ""
    fact_ids: JSON list[int] = []

class CallParticipant(Base):
    __tablename__ = "call_participants"
    id pk; call_id FK calls CASCADE; person_id FK people CASCADE
    identity: str(64)                   # "p<person_id>"
    lang: str(8); joined_at: datetime; left_at: datetime | None
    UniqueConstraint(call_id, person_id)
```

`db/session.py` adds, inside the existing SQLite connect listener: `PRAGMA journal_mode=WAL`, `PRAGMA secure_delete=ON`.

`world/users.py` (pure DB helpers, owned with the schema): `get_space(s) -> Family` (first `kind="space"`, created
lazily with `name="KIN space"`, `heritage_lang` = the creating user's lang), `create_user(s, name, lang, phone) ->
(User, Person, token)`, `user_by_token(s, token) -> User | None`, `normalize_phone(raw) -> str | None` (digits only,
leading `+`, 8-15 digits).

The Krishnan seed (`db/seed.py`) is not changed. World tests create their own space next to it.

### 1.3 Visibility, one definition (`backend/app/world/visibility.py`, pure, no DB)

```python
IDENTITY = frozenset({"tie", "lives_in", "from", "works_at", "studies_at"})

@dataclass(frozen=True)
class FactV:
    id: int; subject_id: int; speaker_id: int | None; predicate: str; text: str; keys: tuple[tuple[str, ...], ...]
    status: str; sensitive_kind: str; remembered: bool; shareable: bool; third_party: bool
    expires_at: datetime | None; pinned: bool; storyline_id: int | None; said_at: datetime
    refs: frozenset[tuple[str, int]]          # {("person", 17), ("thing", 4)}

def expired(f, now) -> bool:        return f.expires_at is not None and not f.pinned and f.expires_at <= now
def content_ok(f) -> bool:          return f.sensitive_kind == "" or f.remembered
def fact_visible(f, audience: frozenset[int], viewer: int, now) -> bool:
    return viewer in audience and not expired(f, now)
def disclosable(f, speaker: int, mentioned: frozenset[int], now) -> bool:
    if f.speaker_id != speaker or not f.shareable or not content_ok(f) or expired(f, now) or f.status != "active":
        return False
    if f.storyline_id is not None and f.subject_id == speaker:      # owner raising their own storyline
        return True
    return f.predicate in IDENTITY and (f.subject_id == speaker or f.subject_id in mentioned)
def usable(f, audience, viewer, speaker, mentioned, now) -> bool:   # what a card body may cite
    return content_ok(f) and (fact_visible(f, audience, viewer, now) or (speaker is not None and disclosable(f, speaker, mentioned, now)))
def bridge_candidate(f, audience, listener, other, now) -> bool:
    return (f.subject_id == listener and f.speaker_id == listener and f.status == "active" and content_ok(f)
            and not expired(f, now) and other not in audience)
```

Entity visibility (in `WorldView`, section 2): entity E is visible to viewer V when E == V; or E is a current
participant; or a tie, edge or group membership links V and E directly (always visible to its endpoints); or that link
has a NULL `fact_id` (setup/legacy); or its fact is visible to V; or some fact visible to V (or disclosable by the
current speaker) has E as subject or in `refs`.

---

## 2. Graph API (`backend/app/world/view.py`)

### 2.1 `WorldView`

Immutable snapshot built per world call, in a worker thread, at join/leave and on `refresh()`; swapped atomically.

```python
@dataclass(frozen=True)
class PersonV: id: int; slug: str; name: str; lang_name: str; is_user: bool; lang: str; aliases: tuple[tuple[str, str], ...]  # (form, lang)
@dataclass(frozen=True)
class ThingV:  id: int; slug: str; kind: str; name: str; owner_id: int | None; keys: tuple[tuple[str, ...], ...]; aliases: tuple[str, ...]
@dataclass(frozen=True)
class GroupV:  id: int; slug: str; name: str; members: frozenset[int]
@dataclass(frozen=True)
class Hop:     to: int; kind: str; label: str; context: str; fact_id: int | None   # kind: kin|tie|group
@dataclass(frozen=True)
class StoryV:  id: int; slug: str; owner_id: int; title: str; keys: tuple; status: str; unresolved: bool
               states: tuple[tuple[int, str, datetime, int, str], ...]  # (state_id, label, at, fact_id, status) by seq

class WorldView:
    space_id: int; members: frozenset[int]
    kin: FamilyGraph                      # FamilyGraph.from_session(s, space_id, person_ids=scope)
    people: dict[int, PersonV]; things: dict[int, ThingV]; groups: dict[int, GroupV]
    adj: dict[int, tuple[Hop, ...]]       # kin + ties + group hops, both directions
    facts: dict[int, FactV]; audience: dict[int, frozenset[int]]
    storylines: dict[int, StoryV]
    first_mention: dict[int, datetime]    # entity id -> earliest said_at of a fact that refs it

    @classmethod
    def build(cls, s: Session, space_id: int, members: Iterable[int], now: datetime) -> "WorldView"
    def visible(self, viewer: int, kind: str, id: int, speaker: int | None = None) -> bool
    def structural_known(self, knower: int, kind: str, id: int) -> bool
    def render(self, listener: int, person_id: int, speaker: int | None = None) -> str
    def card_body(self, listener: int, kind: str, id: int, speaker: int | None, now) -> tuple[str, tuple[int, ...]]  # (body, fact_ids cited)
    def roster(self, listeners: frozenset[int], speaker: int) -> str
    def index_forms(self) -> list[tuple[str, str, int]]      # (form, kind, id) for AliasIndex
    def fact_forms(self) -> list[tuple[str, str, int]]       # concept forms -> ("fact"|"storyline", id) for the keyword index
```

As built (2A): `WorldView` also keeps defaulted indexes after these fields (`now`, `links`, `about`, `gpair`,
`first_known`, `group_forms`). `card_body(..., now)` with a different `now` re-evaluates on
`dataclasses.replace(self, now=now)`, so the render and the cited facts use one clock.

Scope of a build: the members; every person, thing and group referenced by a fact whose audience intersects the members
or that a member said; everyone within 2 hops (kin, tie, group) of a member; all users in the space. Expected size: tens
to low hundreds of rows. Target build time under 50 ms.

`FamilyGraph.from_session(session, family_id, person_ids: set[int] | None = None)` gets the optional filter (additive;
when given, only those people and edges between them are loaded). Non-kin people are nodes with no kin edges, which is
safe: `neighbors()` only yields kin steps, so `WORD`/`CAT` never see a social step.

### 2.2 `structural_known(K, kind, id)`

True when: the item is K; K is a current call participant and the item is a person who is also a participant; a direct
tie or group membership links K and the item (person or group); `kin.distance(K, item) <= 1`; K owns the thing
(`owner_id == K`) or the storyline; or a fact about the item was authored by K (`subject == K` and `speaker == K`).

### 2.3 `render(L, E, speaker=S)`: listener-relative over kin and social paths

Rules in order; first hit wins. Only hops visible to L (or disclosable by S) are walked.

1. E == L: `"you"`.
2. Kin path L -> E (depth <= 4): `FamilyGraph.render(L, E)` ("your uncle Ravi mama (Mom's younger brother)").
3. Direct tie L - E: `"your {kind} {E.name}"` plus `" ({context})"` when set.
4. Speaker context: S has a kin path, tie or group link to E that is visible to L or disclosable by S:
   `"{prefix(S)}'s {label} {E.name}"` plus context. `prefix(S)` is `"your {role} {S.name}"` when S is kin to L
   (`FamilyGraph.role`), `"your {kind} {S.name}"` when tied to L, else `S.name`. Example for Paatti:
   "your grandson Arjun's friend Mei (from high school)". For Arjun: "Mei's friend Lin (from the Fudan climbing wall)".
5. BFS from L over visible hops, max 3, edge cost kin 1, tie 1, group 1.5, stopping at the first anchor A (A == L, or
   `structural_known(L, A)`): `"{render-to-A}'s {last label} {E.name}"` ("Priya's roommate's sister Jess").
6. Fallback: `"{E.name}, mentioned by {S.name}"` (or just the name with no speaker).

`card_body(L, "person", E, S, now)`: `render(L, E, S)`, then up to 2 IDENTITY facts about E that are `usable` for L
("now in Shanghai"), then `"first mentioned {Mon D}"` from `first_mention[E]` when that fact is usable for L, else from
L's own `knowledge.first_at`. Returns the body and the fact ids it cited (for the delivery guard). Spec example:
"Lin: Mei's friend from the Fudan climbing wall, first mentioned Sep 14" (`title` "Lin" + body).

### 2.4 Roster scoping for prompts

`roster(listeners, speaker)` is the PEOPLE section of a world call's MT system prompt. It contains the participants,
plus entities within 2 hops of any participant that are visible to **every** listener in the set or disclosable by the
speaker, plus entities linked in the last 6 utterances. Capped at 40 lines, ranked by most recent evidence. Line format:
`slug | name | native | rendering | aliases`. With one listener the rendering is `render(L, E, speaker)`; with several
(one A call per target language) it is third person ("Arjun's uncle Ravi"). `Person.notes` never appears. Grounded
spans are re-rendered per listener after the call (8.3); a span whose node is not visible to that listener is sent as
plain surface text with `node_id: null`.

### 2.5 "Who is X?" for social relations and other people's worlds

- Triggers (all per listener, after the delivery guard):
  1. Kin word with no referent (`unknown-relative` linker span on a final), as today.
  2. New name from call B: `CardsOut.new_people: list[NewPerson] = []`, `NewPerson{source, name, owner: "speaker"|"listener"|"other", owner_name, relation, context}`. Names already in the alias index are dropped.
  3. New entity created by extraction with no relation to anyone the listener knows (late card, via `emit`).
  4. Ambiguous mention: top two candidates within margin 1.0 (3.4) gives an ask with candidates, never a guessed who card.
- Card: `kind: "ask"`, `term`, `guess` (the suggested name), `suggestions: [{owner: slug, relation, label}]`. Labels
  combine social kinds ("Mei's friend", "Mei's classmate") and kin paths from `builder.suggest` for kin words.
- Answer: `POST /api/world/place` (9.2). `world/apply.place_person` then:
  - creates or reuses the Person (by `person` slug, or by name match in the alias index), with `forms` aliases
    scheduled in the background (`FormsOut`, 3.3);
  - social relation: a `Tie(src=owner, dst=person, kind, context)` with a Fact (`predicate="tie"`,
    `source_kind="card"`, `speaker=me`, `subject=owner`), audience = me plus the call audience when `call_id` is set;
  - kin relation: `link_kin(s, space, anchor=owner, path, person)`: walks the path from the anchor with
    `builder` placeholders for intermediate steps, then attaches an edge to the existing person (new helper in
    `apply.py`; `builder.add_relative` is used unchanged when the person does not exist yet). The edge's Fact audience is
    me plus the endpoints;
  - `confirmed` evidence for me on the person; then `LiveWorld.refresh()` on any active call with me in it.
- Signatures as built (2C): `place_person(s, space_id, me, name, owner, relation, context='', call_audience=(), *,
  person=None, now=None, call_id=None) -> (Person, list[Evidence])` and `link_kin(s, space_id, anchor_id, path,
  person_id, *, me, name='', call_audience=(), now=None, call_id=None) -> (Person, list[Evidence])`. `person` is a slug
  that must exist (LookupError, 404 at the route); only `name` creates a new Person. The route resolves the target
  through the caller's own WorldView first (3C) and calls `place_person(s, space, me, body.name or '', owner, relation,
  body.context or '', audience, person=target, call_id=body.call_id)`.

---

## 3. Cross-script matching (`backend/app/world/match.py`, pure, stdlib only)

### 3.1 Normalization

```python
def fold(s: str) -> tuple[str, list[int]]
    """Per char. Latin: NFKD, drop combining marks, casefold (Lín/LIN -> lin). Other scripts: NFKC + casefold, vowel
    signs KEPT (same rule as ontology.normalize_term). Unicode P/S/Z -> ' '. Returns the folded string and, for each
    folded char, the index of the original char it came from (span offsets survive NFKC expansion)."""
def script_of(ch: str) -> str          # lru_cache: from unicodedata.name: "han"|"hiragana"|"katakana"|"thai"|"latin"|"tamil"|"devanagari"|...
def skel(latin: str) -> str            # Latin phonetic skeleton: y->i, ph->f, collapse doubled letters (Lynn->lin). Linh stays linh.
ISOLATING = {"han", "hiragana", "katakana", "thai", "lao", "khmer", "myanmar"}
```

`ontology.normalize_term` is not changed (the kin linker and Tamil eval depend on its Latin collapsing).

### 3.2 `AliasIndex`

```python
@dataclass(frozen=True)
class Hit: start: int; end: int; surface: str; kind: str; ids: tuple[int, ...]; form: str; exact: bool   # offsets into the ORIGINAL text

class AliasIndex:
    def __init__(self, forms: Iterable[tuple[str, str, int]])   # (surface form, kind, id); kind person|thing|group|fact|storyline
    def scan(self, text: str, speaker_lang: str = "") -> list[Hit]
```

- One char trie (dict of dicts) over `fold(form)` plus a second trie over `skel(form)` for Latin forms (`exact=False`).
  Scan from every position, keep the longest match, suppress overlaps (reuse `cards.matcher._suppress` logic or a
  local copy of it), one hit per (kind, id) per span. Pure Python is enough: about 1 ms for 5k forms on a 300-char line.
  `ponytail:` comment names the ceiling (pyahocorasick past about 50k forms).
- Boundary rules come from the **script of the matched form**, not the family language:
  - Space-delimited scripts: left side is text start or a non-letter; right side is a non-letter, or the rest of the
    token is in the speaker language table's `suffixes`. `roman_suffixes` apply only when the speaker's table script is
    not Latin (so "Maya" never matches "May" for an English speaker). `'s` counts as punctuation.
  - Isolating scripts, forms of 2+ chars: no boundary needed.
  - Isolating, single-char Han or kana forms (林): accepted only when the left neighbour is in
    `CUE_BEFORE = set("和跟与同叫给找带问对是让") | {"と"}`, or the right neighbour is in
    `CUE_AFTER = set("说她他也都的呢吗们") | {"さん","ちゃん","くん","君","と","が","は","も"}` (multi-char cues matched by
    prefix), or BOTH neighbours are boundaries (space, punctuation, Latin, start/end of text). No longer form may start
    at the same position. Single-char Thai forms are never accepted. (As built in wave 1: with either-side boundaries,
    `林檎を食べた` at text start would give 林. Cost, pinned in test_match.py: `我见了林。` and `林去了` give nothing; the
    translator still grounds them, only the instant card is skipped.)
  - Hit contract (as built): a skeleton match on the same span as an exact match is reported as a SECOND
    `Hit(exact=False)` carrying only the ids not already in the exact Hit, so live.py (3.4) receives exact and skeleton
    ids as separate hits.
  - Tamil (and other virama scripts): a non-Latin form ending in a virama is also indexed without it, and that stem
    matches only when the rest of the token is a speaker-table suffix (அர்ஜுன் -> அர்ஜுனுக்கு).
  - Results that are tests: `我和林去攀岩了` gives 林; `林檎を食べた` gives nothing; `ลินไปปีนเขา` gives ลิน when ลิน is a
    form; `Lín`, `Lynn` and `Lin` give the same id; `Maya` gives nothing for alias `May` with `speaker_lang="en"`.

### 3.3 Where cross-script forms come from

- At creation, off the live path: extraction (6.1) returns `forms` per new entity: native script, romanization
  (pinyin, romaji, RTGS, ISO-15919), the common English spelling, and the name in the script of each language spoken by
  users connected to the entity (max 8). Validated mechanically (one script per form via `lexicon._mixed_script`,
  length 1-40) and stored as `Alias(kind="translit", lang=...)`.
- For people placed through `/api/world/place` or created at sign-up: one background `FormsOut{forms: [{lang, form}]}`
  call (effort minimal, `max_completion_tokens=1500`).
- Known name heard in a new script (extraction sees "known entities: id + forms" and returns `existing_id` with a new
  surface): stored as `Alias(kind="asr")`.
- ASR bias: `LiveWorld.keyterms(speaker)` = Latin forms of entities in the speaker's world, including `name`, capped at
  100. Whether Muse `keywords` accepts non-Latin strings is **VERIFY**; until checked, send Latin only.

### 3.4 Candidate ranking (in `world/live.py`)

When a hit carries several ids: +3 when the entity is structurally known to the speaker or kin distance <= 2 from the
speaker, +2 when linked in the last 6 utterances of this call (weight 1/(k+1)), +1 when visible to any participant,
+0.5 for an exact (non-skel) hit. A top margin under 1.0 means ambiguous: no who card, an ask card on the final.

### 3.5 References ("her roommate", "that trip")

- Live, rule-based, English only (cut-line item): `my|your|her|his|their <word>` with word in
  `{friend, roommate, boss, coworker, girlfriend, boyfriend, partner, classmate, teammate}`. Owner: my = speaker,
  your = the single listener (1:1 only), her/his = the most recently linked person in the last 6 lines. If the owner has
  exactly one tie of that kind, emit a hit with `method="relational"`. `that|the <head>` matching a key of an event or
  thing owned by a participant, newest first, gives `method="relational"`.
- Everything else (other languages, "that trip" across calls) is resolved by extraction, which gets the candidate list
  and returns `existing_id`; late who cards come through `emit`.

### 3.6 Latency budget on a partial (server CPU)

| Stage | Budget |
|---|---|
| `fold` + `AliasIndex.scan` + lexicon `Matcher.match` | 1 ms |
| Ranking + stability gate | 0.3 ms |
| Per listener: knowledge dict lookup, `decide`, cached `card_body`, guard | 0.2 ms each |
| **`on_partial` total, p95 target** | **<= 10 ms for 8 listeners** (measured in the eval) |

The old `Linker` (10-17 ms, O(tokens x aliases)) runs only on finals inside the MT worker thread, for kin terms.

---

## 4. Common-ground model (`backend/app/world/knowledge.py`, pure)

Knowledge tracing with forgetting. Between observations p decays toward a floor with a per-item half-life. Each
exposure is the BKT learning transition at a rate set by its evidence type. "Said it yourself" and "confirmed" are strong
learning events; "asked who X is" is a BKT incorrect observation. Half-life grows when the item is reinforced on a new day
while still remembered (spacing effect, half-life-regression style).

```python
P_FLOOR = 0.02
PRIOR   = 0.02                      # any item with no row (structural knowledge is a separate gate)
LEARN   = {"heard": .70, "shown": .50, "said": .95, "authored": .95, "confirmed": .98}
H0_DAYS = {"heard": 30, "shown": 21, "said": 60, "authored": 60, "confirmed": 90, "asked": 30}
GROWTH, H_MAX = 1.5, 365
FORGOT = 0.35                       # reminder below this
SLIP, GUESS = 0.05, 0.02            # for "asked"

@dataclass(frozen=True)
class State: p: float; half_life_days: float; first_at: datetime; last_at: datetime; last_day: str
             n_heard: int = 0; n_shown: int = 0; n_said: int = 0; n_confirmed: int = 0; n_asked: int = 0

def p_now(st: State | None, t: datetime) -> float:
    if st is None: return PRIOR
    dt = max(0.0, (t - st.last_at).total_seconds() / 86400)
    return P_FLOOR + (st.p - P_FLOOR) * 2 ** (-dt / st.half_life_days)

def update(st: State | None, ev: str, t: datetime) -> State:          # returns a new State; never mutates
    p0 = p_now(st, t); day = t.date().isoformat()
    if ev == "asked":
        p = p0 * SLIP / (p0 * SLIP + (1 - p0) * (1 - GUESS)); h = H0_DAYS["asked"]
    else:
        p = p0 + (1 - p0) * LEARN[ev]
        if st is None:              h = H0_DAYS[ev]
        elif day != st.last_day:    h = min(H_MAX, max(st.half_life_days, H0_DAYS[ev]) * (1 + GROWTH * p0))
        else:                       h = max(st.half_life_days, H0_DAYS[ev])        # same day: no growth
    return State(p, h, st.first_at if st else t, t, day, ...counts incremented...)

def decide(st: State | None, t: datetime, structural: bool) -> str | None:   # None | "new" | "reminder"
    if structural: return None
    if st is None: return "new"
    return "reminder" if p_now(st, t) < FORGOT else None
```

Worked demo numbers (these are the acceptance test for task 1C, to 3 decimals):

| Case | Computation | p | Card |
|---|---|---|---|
| Never heard of Lin | no row | 0.020 | new |
| Priya heard Lin once, 6 days ago (if no tie) | 0.02 + 0.686 x 2^(-6/30) | **0.617** | none |
| Arjun heard Lin once, 42 days ago | 0.02 + 0.686 x 2^(-42/30) | **0.280** | reminder |
| Arjun in call 2: `shown` (new day, p0 0.280) | p = 0.640, h = 30 x 1.42 = **42.6** | 0.640 | |
| then `heard` the same final (same day) | p = 0.640 + 0.36 x 0.7, h stays 42.6 | **0.892** | |
| Arjun the next day | 0.02 + 0.872 x 2^(-1/42.6) | **0.878** | none |

One hearing crosses FORGOT after about 32 days ("six weeks ago and likely forgotten").

Evidence and where it is written:

| Event | Knower | Evidence | Item | Written by |
|---|---|---|---|---|
| Mention confirmed on a final (stable hit or linker span) | each audience member except the speaker | `heard` | person/thing/group | `live.on_final` |
| Same | speaker | `said` | same | `live.on_final` |
| Card confirmed by the final (who/what/storyline/ask) or a late card delivered | that listener | `shown` | the card's item (and storyline state) | `live.on_final` / `live` emit path |
| Extraction creates or matches fact F | audience(F) / speaker | `heard` / `said` | fact F, its refs, its storyline state | `apply.py` |
| SMS fact | author | `authored` | fact | `world/sms.py` via apply |
| Ask answered, or card feedback `know` | that listener | `confirmed` | item | `api/world.py`, `/api/calls/{id}/feedback` |
| "Who's Lin?" said in a call (B `new_people` with relation "question") or ask tapped without answer | asker | `asked` | person | `live.on_translated` |
| Paused call, watchers, `dismiss` feedback | nobody | none | | |

Ordering rule: card decisions for an utterance read the state **before** that utterance's evidence; `shown` is applied
before `heard` on the same final.

Storage: `knowledge` table. `LiveWorld.kcache: dict[(knower, kind, id), State]` is loaded at join for the participants.
Updates replace dict entries (new frozen States); dirty keys are upserted once per final on the world pool
(`world/live._WORLD_POOL`, 2 workers) and at call end. Out of call (SMS, REST) writes go straight to the DB.
Concurrent calls by the same user: last write wins per row (stated ceiling).

---

## 5. Bridges (`backend/app/world/cards.py::bridges`)

For each listener L who is a user, on `on_translated` for speaker S's final:

1. **Candidates** (self-only by construction): view facts with `bridge_candidate(f, audience[f], L, S, now)`, capped at
   50 newest per listener, `said_at >= now - 180 days`. This includes L's SMS facts (`shareable=False` stops KIN from
   disclosing them, not L from being nudged to share them).
2. **Relevance (no embeddings, 0 LLM calls by default)**: a keyword `AliasIndex` built from each candidate's concept
   groups (`fact_forms()`), scanned over S's `src_text` and L's translation (or `src_text` when languages match).
   A concept group counts once however many of its forms hit. A hit is strong when the matched form is Latin with 4+
   chars or isolating with 2+ chars. Linked-entity overlap (a stable hit on an entity in `f.refs`) counts as one extra
   concept. **Pass** when at least one strong concept hit, or at least 2 concept hits. Ties broken by newest `said_at`.
3. **Optional rerank**: `bridge_rerank=False` by default. When true: one `BridgeOut{fact_id: int | None}` call (effort
   minimal, 2.5 s timeout) over the top 3; timeout or error means no bridge.
4. **Rate limits** (from `card_log`): at most 1 bridge per listener per 90 s, at most 3 per listener per call, and no
   `card_log` row with `kind="bridge", listener=L, target=S, key="bridge:{F}"` within 7 days. The 7-day rule is what makes
   "same sentence the next day: nothing" true for bridges.
5. **Card**: `{kind:"bridge", key:"bridge:{F}", title:"You haven't told {S.name}", body: F.text localized, target: S.slug,
   private: true}` with internal `fact_ids=(F,)`. Sent only to L's identity; never stored on an utterance, never to
   watchers.
6. **Closing the loop**: when L's own final, with S present, hits F's concepts at pass strength, write
   `FactAudience(F, S, via="told")` immediately (it only suppresses future bridges, so a false positive fails safe).
   Extraction later confirms with `same_as=F`. If L was shown the `bridge:{F}` chip for S in this call, L gets
   `glance_retract {keys:["bridge:{F}"]}` in that line's sends; the key stays in `sent`, so it never comes back in
   the call (4C).

---

## 6. Extraction and storylines (`backend/app/world/extract.py`, `backend/app/world/apply.py`)

### 6.1 Extraction call

- Trigger (`live.py`): 4 new finals, 30 s idle, pause, or call end; one in flight per call; runs on `_WORLD_POOL`.
- Window: finals since the last run plus 3 lines of overlap, numbered, each with speaker id and language.
- `LLM.structured(WorldUpdateOut, ...)`, effort low, `max_completion_tokens=4000`, timeout from settings,
  `prompt_cache_key=f"kin-world-{call_id}"`.
- Prompt prefix (privacy-scoped): participants (id, name, lang); for each speaker, **only that speaker's own** active
  facts (id, text) and storylines (id, title, latest state); names, ids and forms (no facts) of entities visible to that
  speaker (max 60); the languages of users connected to the speakers (for `forms` and `keys`). Utterances last.

```python
# strict schema: every key required; "" / null / [] for none
class EntityOut:  ref: str; name: str; native: str; forms: list[str]; kind: Literal["person","place","event","thing","group"]; existing_id: int | None
class TieOut:     a: str; b: str; kind: str; context: str          # a/b: ref | "speaker" | existing slug
class StoryOut:   existing_id: int | None; title: str; state_label: str; resolved: bool
class FactOut:    subject: str; predicate: str; text_en: str; text_src: str; keys: list[list[str]]; refs: list[str]; lines: list[int]
                  sensitive_kind: Literal["","health","money","conflict"]; same_as: int | None; contradicts: int | None; storyline: StoryOut | None
class WorldUpdateOut: entities: list[EntityOut]; ties: list[TieOut]; facts: list[FactOut]
```

### 6.2 Validator (drop the item and log; never guess)

- every `lines` index inside the window; every fact cites at least one line;
- a fact whose subject is a user must cite only that user's own lines; a fact about a third party must cite lines by
  the speaker who introduced it;
- `same_as`/`contradicts` must name a fact whose speaker is the cited speaker;
- a sensitive fact: `text` reduced to the topic word (reuse `memory.service._reduce_sensitive` rule), `text_src=""`,
  `keys=[]`, and the cited utterances get `sensitive_topic` set (existing `withheld()` keeps working);
- `existing_id` must be an id from the prompt's candidate list.

### 6.3 Apply (`apply.apply_update(s, update, ctx) -> ApplyResult`)

`ctx = {space_id, call_id | None, message_id | None, speaker_of_line: dict[int, int], audience_of_line: dict[int,
list[int]], utterance_of_line, now, source_kind, shareable}`. Pure DB writes plus returned evidence; the caller applies
evidence to its cache.

- Entities: reuse `existing_id`, else create Person/Thing/Group with world slugs and `translit` aliases from `forms`.
- Ties: `Tie` + a Fact (`predicate="tie"`, subject = owner, text "Lin is Mei's friend from the Fudan climbing wall").
  A tie with no matching LLM tie fact gets a synthesized tie Fact only when one person spoke in the window; with two
  or more speakers it is dropped, because nothing says who said it.
- Facts: `said_at` = utterance time; `third_party` when the subject has no `users` row, then
  `expires_at = said_at + third_party_ttl_days`; `FactAudience`: the speaker (`said`), the line audience (`heard`);
  `FactRef` rows for `refs`. `same_as` merges audience into the existing fact instead of writing a new one.
- Returned evidence: `heard`/`said` for facts, refs and storyline states.
- `place_person(...)` and `link_kin(...)` (2.5) live here too.

### 6.4 Storyline state transitions

- New: `storyline.existing_id is None` -> `Storyline(owner=subject, title, keys)` plus `StorylineState(seq=1)`. When the
  LLM forgets the id, match by same owner and `rapidfuzz.fuzz.token_set_ratio(title) >= 70` or 2 shared concepts.
- Progression from the owner (self-report, newer `said_at`): previous active state `superseded`, fact
  `superseded_by = new`.
- Terminal: `resolved: true`, or a label in `{offer accepted, accepted, done, moved, finished, ended}`: storyline
  `status="resolved"`, fact `status="resolved"`.
- Contradiction (`contradicts=F`): if the new fact's speaker is F's subject (people update their own news), F becomes
  `superseded`. Otherwise both become `contradicted`, the storyline gets `unresolved=True`, and a card shows
  "unclear: Beijing or Shanghai" only to listeners for whom both facts are usable.

### 6.5 When a storyline card shows (per listener L, speaker S)

All of:
1. The storyline is mentioned: a keyword-index hit on its concept groups or title, or a stable hit on its owner plus
   one concept hit.
2. V = states whose fact is usable for L (visible to L, or disclosable by S because S is the owner) is non-empty.
3. `decide(kcache[L, "state", newest V], now, structural=False) != None` (L is behind on the newest usable state).
4. L knows the owner: `structural_known(L, owner)` or `p_now(L, owner) >= 0.5`.

Body: last 3 states of V as `label (Mon)`, each `known: bool` (`p_now >= FORGOT`), e.g.
"Mei's job search: applied (Sep) -> second round (Oct)". Once per storyline per listener per call. `fact_ids` = the
cited state facts.

---

## 7. SMS (`backend/app/world/sms.py`, `backend/app/api/sms.py`)

- `POST /twilio/sms` (form `From, To, Body, MessageSid`; `/twilio/` is outside the key gate). Calls
  `api.twilio._verify_twilio(request, form)` (import it, do not copy it).
- Idempotent: a repeated `MessageSid` returns the stored `reply`.
- Sender: `users.phone == normalize_phone(From)`. Unknown number: reply "This number isn't linked to KIN yet. Add it in
  the app under You." and store nothing.
- Body over 1600 chars is truncated; 30 messages per user per hour (in memory), over that: reply "Slow down a little."
- `ingest(s, user, body, sid) -> (reply, fact_ids)`: save `Message`, then `LLM.structured(SmsOut)` (effort minimal,
  2000 tokens, 8 s budget):
  ```python
  class SmsFact: predicate: str; text_en: str; keys: list[list[str]]; sensitive_kind: Literal["","health","money","conflict"]
                 storyline: StoryOut | None; told: list[str]          # names the author says already know
  class SmsOut:  facts: list[SmsFact]; ack: str                        # <= 120 chars, restates the news, no advice
  ```
  Every fact: subject = speaker = author, `source_kind="message"`, `shareable=False`, `FactAudience(author, "authored")`.
  Each `told` name resolved by `AliasIndex` over the author's visible people gets `FactAudience(person, "told")`.
  Facts about other people are dropped (prompt and validator). Storylines go through 6.4. Then `Message.body = ""`,
  `status="parsed"`, `fact_ids` set, and `LiveWorld.refresh()` for any active world call with the author in it.
- Reply: TwiML `<Response><Message>{xml-escaped ack}</Message></Response>`, `application/xml`. If the parse exceeds 8 s
  or fails: reply "Got it." and finish in a background task (one retry). Twilio's webhook timeout of about 15 s is
  **VERIFY**; STOP/HELP rely on Twilio Advanced Opt-Out, **VERIFY**.
- Dev: `POST /api/dev/sms {from, body}` -> `{reply, message_id, facts:[{id,text}]}` through the same `ingest`, no
  signature check. This is the demo path until a Twilio number exists.

---

## 8. Real-time pipeline for N participants

### 8.1 `CallSession` (`backend/app/audio/pipeline.py`)

- `Side` gains `identity: str`, `person_id: int | None = None`, `tts_lock: asyncio.Lock`. `role` stays: the legacy role
  string, or `"participant"` for world calls.
- `sides: dict[identity, Side]`. Signature, positionally compatible:
  `join(identity, person, send_json, send_bytes, wants_audio=True, start_asr=True, *, lang=None, person_id=None)`.
  `lang is None` means the legacy rule (heritage for `"grandparent"`, else `"en"`). Same identity = reconnect (today's
  replace semantics). `leave(identity, token)`, `on_audio(identity, pcm)`, `on_text(identity, text)` keep their names.
- `cs.world: LiveWorld | None`. Set by `CallRegistry.get_or_create` when `call.mode == "world"`; `cs.fade = None` and
  `cs.on_utterance = None` for world calls (Fade is the optional legacy mode).
- Every world branch is `if self.world is not None:`. The legacy code paths (`_glance`, `process_utterance`,
  `_broadcast`, `peer`, `_default_listener`) are left as they are; the world path is a separate method
  `_process_world(side, text, ...)`.
- `paused_by: int | None`; `async set_paused(by_person_id, paused)`: sets it, sends
  `{"type":"kin_status","on":not paused,"paused_by":...}` to every side. While paused, `on_audio` drops frames before
  ASR and `on_text` ignores input: nothing is transcribed, stored, carded or counted as evidence.
- World `join` also sends `participants` to everyone and `kin_status` to the joiner, and calls
  `await asyncio.to_thread(world.join, identity, person_id, lang)`.
- Watchers (`/ws/watch`) receive nothing from world calls.

### 8.2 World partial and final flow

```
_asr_loop (world): partial -> send {"type":"partial",...} to every side (public: raw text of what everyone just heard)
                              sends = world.on_partial(speaker_identity, text)      # sync, in memory, <= 10 ms
                              deliver sends per identity
                   final   -> fr = world.on_final(speaker_identity, text)            # cards, retracts, spans for MT
                              deliver fr.sends; await _process_world(side, text, spans=fr.spans)
```

### 8.3 `_process_world(side, text, spans)`

```
if paused: return
listeners = [s for id, s in sides.items() if id != side.identity]
audience  = [s.person_id for s in listeners if s.person_id]
groups    = {lang: [L...] for listeners whose lang != side.lang}       # one A (+B) call per distinct target language
same      = listeners whose lang == side.lang                          # no MT; caption = src_text
for lang, Ls in groups:  (in parallel: asyncio.gather(to_thread(...)))
    tr = world.translator(lang)                                        # Translator over view.kin, linker for side.lang
    roster = world.roster([L.identity for L in Ls], side.identity)
    res[lang] = tr.translate_speech(text, side.person, Ls[0].person if len(Ls)==1 else None, history[lang], (),
                                    None, lang, extra_spans=spans, roster=roster)
persist ONE Utterance(lang=side.lang, audience, translations={lang: tr}, translation=first, listener_id=first listener)
for L in listeners:
    payload_L = transcript with translation = res[L.lang] (null for same-language), grounded_spans re-rendered by
                world.render(L.identity, node_id) (invisible nodes -> surface text, node_id null), linker_spans same rule
    send to L only
send the speaker their own transcript (translation null, target_lang = own)
for lang, Ls in groups: TTS task per language: async with each L.tts_lock: audio_start, stream bytes to every
                        wants_audio L in Ls, audio_end; tasks kept in bg_tasks (never awaited inline)
for lang: B future -> enrich to that language's listeners; new_people -> world.asks(...) -> deliver
sends = world.on_translated(side.identity, utterance_id, text, {lang: tr}, audience) -> deliver  (bridges, storylines, evidence, extraction)
latency event to every side
```

- History becomes per target language: `history[lang]: list[(speaker slug, src, translation)]`, last 6.
- `deliver(identity, msg)` is `_safe_send` to that side; the delivery guard runs inside `LiveWorld` before it returns.
- Every stage records into `latencies`: `scan_ms` (on_final), `a_ms`/`mt_ms` per language (`mt_ms_<lang>`), `b_ms`,
  `tts_first_byte_ms`, `cards_ms` (on_translated), `total_ms`.

### 8.4 Translator (`backend/app/mt/translate.py`, additive)

- `Translator(graph, llm=None, lang: str | None = None)`: `lang` selects the linker/kin table for the speaker's
  language (default `graph.heritage_lang`, as today).
- `translate_speech(..., target_lang="en", extra_spans=(), roster: str | None = None)`. `roster is None` keeps
  today's prompt byte-identical. A given roster replaces the FAMILY ROSTER block; cache key becomes
  `f"kin-{family_id}-{target_lang}-{sha1(roster)[:10]}"`. `listener=None` adds one line: "Several listeners: use names,
  never 'your'." Unknown speaker/listener slugs use neutral naming instead of raising `KeyError`.
- `extra_spans` (dicts with start/end/source/node_id/type/rendered) are merged with linker spans before the prompt and
  `_reconcile`.
- Target script fix: `f"natural spoken {tl}, {tl} script"` where `tl` comes from `MUSE_LANGUAGES`. For Tamil the text is
  byte-identical ("Tamil script").
- `Linker(graph, lang=None)` and `keyterms()` including `Node.name` (`graph/linker.py`).
- `CardsOut.new_people: list[NewPerson] = []` (`mt/schemas.py`); B's task text asks for unresolved names.
  With a roster, `TranslateResult.cards` resolves to `(cards, b_ms, new_people: list[NewPerson])`; without, to
  `(cards, b_ms)`. The pipeline reads `new_people` from index 2.
- `get_translator(family_id)` is unchanged for legacy and eval.

### 8.5 `LiveWorld` (`backend/app/world/live.py`): the one object the pipeline talks to

```python
Sends = dict[str, list[dict]]            # identity -> server->client messages

@dataclass(frozen=True)
class FinalResult: sends: Sends; spans: list[dict]

class LiveWorld:
    def __init__(self, call_id: int, space_id: int, emit: Callable[[str, dict], Awaitable[None]], loop: asyncio.AbstractEventLoop)
    def join(self, identity: str, person_id: int, lang: str) -> None          # blocking: rebuild view, load kcache, prewarm
    def leave(self, identity: str) -> None
    def on_partial(self, speaker: str, text: str) -> Sends
    def on_final(self, speaker: str, text: str) -> FinalResult
    def on_translated(self, speaker: str, utterance_id: int, text: str, translations: dict[str, str], audience: list[int]) -> Sends
    def asks(self, speaker: str, listeners: list[str], new_people: list) -> Sends
    def feedback(self, listener: str, key: str, action: str) -> None          # know|dismiss|remember
    def render(self, listener: str, node_id: str) -> str | None
    def roster(self, listeners: list[str], speaker: str) -> str
    def translator(self, lang: str) -> Translator                             # cached per lang
    def keyterms(self, speaker: str) -> list[str]
    def refresh(self) -> None                                                 # rebuild view in the world pool, swap, keep kcache
    def close(self) -> None                                                   # final extraction, flush knowledge
```

Internals: `view`, `index` (AliasIndex over `view.index_forms()`), `kw` (keyword index over `view.fact_forms()`),
`kcache`, `sent: frozenset[(identity, key)]`, `pending: dict[(identity, key), PendingCard]` (sent on a partial, waiting
for the final), `last_hits: dict[speaker, frozenset[(start, id)]]` (stability gate), `recent: list[(speaker, hits)]`
(last 6 finals for salience). Card selection lives in `world/cards.py` (pure functions over the view and kcache).
Localization and extraction jobs live in `world/live_jobs.py` (`LiveJobs`, a mixin LiveWorld inherits).

- **on_partial**: scan; a hit is stable when `(start, id)` was in the previous partial of this speaker; for each
  listener != speaker: `gaps(...)` -> items not in `sent`; guard; record in `sent` and `pending`; send `glance` with
  `partial: true`.
- **on_final**: scan the final; send gap cards not yet sent (no stability needed); for each `pending` card whose
  `(start,id)` hit is absent from the final: `glance_retract {keys}` and drop it; confirmed cards get `shown` evidence
  and a `card_log(final=True)` row; then `heard`/`said` evidence for confirmed mentions; return spans for MT.
- **on_translated**: bridges and storyline cards per listener (5, 6.5); disclosure fast path; extraction trigger count;
  knowledge flush scheduled on `_WORLD_POOL`.
- **Localization**: at join of a listener whose lang != "en", one background `LocalizeOut{items:[{key, body}]}` call
  for the top 30 card bodies in their view, cached by `(key, lang, sha1(body))`. A miss sends English and follows with
  `glance_update {key, body}` when a lazy single-card localization lands. Kin terms render in the listener's table
  language already.

### 8.6 Cards per listener (`backend/app/world/cards.py`, pure)

```python
def gaps(view, kcache, listener: int, speaker: int, hits: list[Hit], lex: list[Match], now) -> list[Card]
def bridges(view, kcache, listener: int, speaker: int, texts: list[str], hits, now, log: CardLogView) -> list[Card]
def storylines(view, kcache, listener: int, speaker: int, kw_hits, hits, now) -> list[Card]
def deliver_ok(view, card: Card, listener: int, speaker: int, mentioned: frozenset[int], now) -> bool   # the guard (D13)

@dataclass(frozen=True)
class Card: key: str; kind: str; item: dict; fact_ids: tuple[int, ...]; payload: dict   # payload = GlanceItem JSON (9.1)
```

- who/what: entity visible to L or rendered through the speaker context, and `decide(...) in {"new","reminder"}`.
  Key `who:{slug}` / `what:{slug}`, `gap` = the decision.
- term/saying: the existing `cards.matcher` + lexicon of the **speaker's** language (`load_lexicon(side.lang)`), only
  when `L.lang != speaker.lang`. Key `lex:{lang}:{key}`.
- The speaker never gets cards about their own words.
- `deliver_ok`: every id in `card.fact_ids` must be `usable` for L with speaker S; otherwise log
  `"guard dropped %s for %s"` and drop. The eval counts drops; the engine is expected to produce 0.

### 8.7 LiveKit (`backend/app/api/rtc.py`, `backend/app/rtc/agent.py`)

- `POST /api/rtc/join` accepts the legacy body `{family_id, role, call_id?}` unchanged, or the world body
  `{call_id?: int}` with header `X-KIN-User`. World: creates `Call(mode="world", family_id=space, transport="livekit")`
  when `call_id` is missing, else checks the call is `mode="world"`; upserts `CallParticipant`; identity `p{person_id}`;
  token metadata `{"person": slug, "person_id": id, "lang": lang, "name": name}`.
- `RoomAgent._join`: metadata with `person_id` -> `session.join(p.identity, person, leg.send_json, leg.send_bytes,
  lang=meta["lang"], person_id=meta["person_id"])`; legacy role metadata unchanged. The leg key used for `on_audio` and
  `leave` is the session identity (`p.identity` for world, the role for legacy). The agent subscribes to audio only
  (existing `track.kind` check).
- Mobile (`mobile/src/call.ts`): publish camera and mic (`setCameraEnabled(true)` and `setMicrophoneEnabled(true)`
  inside the tap handler so iOS audio unlock stays synchronous; camera can be toggled off). `routeTrack(trackName, from,
  me, kind)` returns `'peer-video'` for a remote non-agent video track; tiles grid for N peers; ducking applies to every
  peer audio track while `kin-to-<me>` plays. `autoSubscribe:false` stays. **VERIFY** `setCameraEnabled` and video
  `TrackPublication.setSubscribed` in livekit-client 2.22.4 before coding; log in DECISIONS.

### 8.8 Legacy paths

Kept unchanged: `/ws/call` (old frontend, overlay), phone merge (`audio/buddy.py`, `/ws/watch`, `/phone`), Twilio Relay,
legacy `/api/rtc/join` body, `live_glance`, `GlanceEngine`, `POST /api/cards/glance`. Their tests are not edited. The
legacy `CallSession` methods keep today's semantics because a role string is a valid identity.

---

## 9. Contracts (exact JSON)

Pydantic models for every shape below live in `backend/app/world/contracts.py`; `mobile/src/contracts.ts` mirrors them.

### 9.1 Server -> client (LiveKit data, topic `kin`, `destination_identities=[identity]`)

```jsonc
{"type":"joined","call_id":12,"identity":"p3","person":"p_arjun_3","name":"Arjun","lang":"en","role":"participant",
 "peer_present":true,"participants":[{"identity":"p5","person":"p_mei_5","name":"Mei","lang":"zh"}],
 "kin":{"on":true,"paused_by":null}}
{"type":"participants","participants":[{"identity":"p5","person":"p_mei_5","name":"Mei","lang":"zh"}]}
{"type":"kin_status","on":false,"paused_by":{"person":"p_priya_4","name":"Priya"}}
{"type":"partial","speaker":"p5","person":"p_mei_5","role":"participant","lang":"zh","text":"我和林去"}
{"type":"glance","speaker":"p5","role":"participant","partial":true,"items":[GlanceItem]}
{"type":"glance_retract","keys":["who:p_lin_17"]}
{"type":"glance_update","key":"who:p_lin_17","body":"梅在复旦攀岩墙认识的朋友"}
{"type":"transcript","call_id":12,"utterance_id":91,"speaker":"p_mei_5","speaker_identity":"p5","role":"participant",
 "listener":"p_arjun_3","src_text":"我和林去攀岩了","src_lang":"zh","src_lang_tags":[],"target_lang":"en","heritage_lang":"zh",
 "translation":"I went climbing with Lin.",
 "grounded_spans":[{"source":"林","rendered":"Mei's friend Lin (from the Fudan climbing wall)","node_id":"p_lin_17"}],
 "pragmatics_cards":[],"passthrough":[],"confidence":0.9,
 "linker_spans":[{"start":2,"end":3,"source":"林","node_id":"p_lin_17","type":"person","confidence":0.95,"rendered":"...","candidates":[],"method":"alias"}],
 "latencies":{"scan_ms":0.4,"a_ms":1850,"mt_ms":1862},"error":null}
{"type":"enrich","utterance_id":91,"pragmatics_cards":[],"b_ms":2100}
{"type":"audio_start","utterance_id":91,"lang":"en"}  {"type":"audio_end","utterance_id":91}
{"type":"latency","utterance_id":91,"latencies":{"tts_first_byte_ms":310,"cards_ms":1.2,"total_ms":2400}}
{"type":"status","asr":"ok|unavailable|ended","detail":""}  {"type":"error","stage":"mt|tts|pipeline","message":""}
```

`translation` is `null` when the listener shares the speaker's language. GlanceItem (a superset of today's item; old
clients ignore unknown kinds):

```jsonc
{"key":"who:p_lin_17",           // who:<slug> | what:<slug> | bridge:<fact_id> | story:<storyline_id> | ask:<norm> | lex:<lang>:<k>
 "kind":"who|what|term|saying|ask|bridge|storyline",
 "title":"Lin","native":"林","body":"Mei's friend from the Fudan climbing wall, first mentioned Sep 14",
 "category":"person","image_url":"","image_credit":"","source_url":"",
 "node_id":"p_lin_17","gap":"new|reminder",                                        // who/what
 "term":"Lin","guess":"Lin","suggestions":[{"owner":"p_mei_5","relation":"friend","label":"Mei's friend"}],  // ask
 "target":"p_mei_5","private":true,                                                // bridge
 "storyline_id":3,"states":[{"label":"applied","at":"2026-09-02","known":true},{"label":"second round","at":"2026-10-10","known":false}]}
```

`fact_ids` are never sent to clients; only `card_log` keeps them.

### 9.2 REST (new). All world routes need `X-KIN-User` (401 without, 403 for someone else's data); the KIN key gate still applies.

| Method and path | Body / query | Response |
|---|---|---|
| `POST /api/users` (no X-KIN-User) | `{name, lang, phone?}` | `{user_id, person_id, person, space_id, token, sms_number}` (`token` shown once) |
| `GET /api/me` | | `{user_id, person_id, person, name, lang, phone}` |
| `PATCH /api/me` | `{name?, lang?, phone?}` | same as GET |
| `DELETE /api/me` | | `{deleted:true, facts:n, utterances:n}` |
| `GET /api/contacts` | | `[{person, name, lang, render, circle:"family|friends|group"}]` (users I share a call, tie or edge with) |
| `GET /api/world` | | `{me, people:[{id, person, name, render, lang, is_user, circle}], ties:[{src, dst, kind, context}], edges:[{src, dst, relation}], groups:[{id, name, members}], things:[{id, slug, kind, name, owner}], storylines:[{id, title, status, states:[{label, at}]}]}` (visible only) |
| `GET /api/world/relations?lang=` | | `{social:[{kind, label}], kin:[{path, label}]}` |
| `POST /api/world/place` | `{name?, person?, owner, relation, context?, call_id?}` | `{id, person, name, render}` |
| `GET /api/me/facts` | | `{about_me:[Fact], i_said:[Fact]}` with `Fact = {id, text, subject, speaker, source_kind, said_at, status, sensitive_kind, pinned, expires_at, heard_by:[{person, name, via}]}` |
| `PATCH /api/me/facts/{id}` | `{text?, status?, pinned?, remembered?}` | `Fact` (subject or speaker only; `pinned`/`remembered` also audience) |
| `DELETE /api/me/facts/{id}` | | `{deleted:true}` (subject or speaker only) |
| `DELETE /api/me/world/people/{slug}` | | `{deleted_facts:n, person_deleted:bool}` (third parties only, facts I said) |
| `POST /api/calls/{id}/pause` | `{paused:bool}` | `{on, paused_by}` (participants only) |
| `POST /api/calls/{id}/feedback` | `{key, action:"know|dismiss|remember"}` | `{ok:true}` |
| `POST /api/calls/{id}/text` | `{text}` | `{ok:true}` (typed input for LiveKit clients; demo insurance) |
| `POST /api/calls/{id}/voice` | `{on:bool}` | `{on}` (pause, feedback, text and voice return 409 until the caller has a joined side) |
| `GET /api/calls/{id}/participants` | | `[{person, identity, lang, joined_at, left_at}]` |
| `POST /api/rtc/join` | world `{call_id?}` + X-KIN-User, or legacy body | `{call_id, room, token, url, identity, person, name, lang, participants}` / legacy unchanged |
| `POST /twilio/sms` | Twilio form | TwiML |
| `POST /api/dev/sms` | `{from, body}` | `{reply, message_id, facts:[{id, text}]}` |
| `POST /api/dev/clock` | `{offset_days}` | `{now}` |
| `POST /api/dev/apply` | `{call_id?, speaker:slug, audience:[slug], update: WorldUpdateOut}` | `{facts:[id], entities:[{ref, id, slug}]}` (same `apply_update` path; validator runs with each fact citing line 0 by `speaker`; a tie with no tie fact is synthesized, since one person speaks) |

Dev routes return 404 when `settings.dev_endpoints` is false.

---

## 10. Privacy enforcement points

| Rule (PRODUCT.md) | Enforced in | Test |
|---|---|---|
| Everyone sees KIN is on; anyone can pause | `CallSession.join` sends `kin`; `set_paused` + `POST /api/calls/{id}/pause` broadcast `kin_status`; `on_audio`/`on_text` drop input | `test_group_call.py`: no utterance, fact or knowledge row while paused; every leg gets `kin_status` |
| Audio processed and discarded | No audio sink in the world path; `audio_url` unused | same test checks no new files under `media/` |
| Bridges only use your facts | `visibility.bridge_candidate` (`subject == speaker == L`) | `test_cg_cards.py` property test over random views: no non-self bridge |
| Never repeat what someone else told you | `disclosable` limits cross-world content to the speaker's own facts; extraction validator ties a user's facts to that user's lines | `test_visibility_rules.py`, `test_extract_apply.py` |
| Third parties: only what was said, only to hearers, expire unless pinned | `fact_visible` (audience + `expired`); `privacy.sweep_expired(s, now)` at startup, at call end and hourly: hard-deletes expired unpinned third-party facts and orphaned third-party people | `test_visibility_rules.py` with the clock past 120 days |
| Sensitive = topic word unless remembered | validator/apply reduce text; `content_ok` excludes them from cards, rosters and bridges; `remembered` via PATCH | `test_extract_apply.py` |
| Cards and prompts only use visible facts | `WorldView.roster` (intersection), per-listener `render`, `cards.deliver_ok` guard on every card, `card_log` | `test_group_call.py` with a fake world; eval hard-fail counters |
| You own your world; deleted means gone | `privacy.delete_fact`, `delete_person`, `delete_account`; then `LiveWorld.refresh()` on active calls and `reset_translator_cache()` | `test_delete.py`: after delete, a scan of every table (and JSON columns `audience`, `fact_ids`, `participants`) finds no reference to the id or its text |
| SMS private to its author | `shareable=False`, audience = author (+`told`), body cleared after parse, no route exposes another user's messages | `test_sms.py` |
| Never reads message histories; no engagement nudges | no such code; SMS prompt forbids advice; cards only in a live session | n/a |
| Watchers | world calls send nothing to `/ws/watch` | `test_group_call.py` |
| Legacy leaks | `memory/service.py`: family-scoped `_transcript_text`, no hard-coded slugs, unique slugs; `fade/service._learner_id` family-scoped; connector stays demo-family scoped and never reads world tables | `test_memory_connector.py` |

Delete order (`privacy.delete_person(s, person_id)`, one transaction; CASCADE covers the new tables but the order is
explicit so the code does not depend on it): knowledge (knower or item person), card_log (listener, or fact ids
containing the person's facts), fact_audience, fact_refs (ref person), storyline_states then storylines owned,
facts (subject or speaker), ties, group_members, edges, aliases, utterances (`speaker_id = P`: delete; `listener_id =
P`: set NULL; remove P from `audience`), messages, call_participants, mastery, consents, glossary `speaker_id` set NULL,
users, people. `delete_fact` also redacts the source utterance's `src_text`/`translations` when no other fact cites it.

---

## 11. Evaluation

- **Keep**: `python -m eval.run_eval [--mock]` untouched. Gate for every wave: `--mock --limit 20 --out /tmp/e.md`
  exits 0, and a full `--mock` run's linker-only row equals the pin in the header of this file.
- **Scenarios** (`backend/eval/common_ground/scenarios.jsonl`, schema in `backend/eval/common_ground/schemas.py`):

```jsonc
{"id":"lin_six_weeks","tags":["gap","reminder","group","cjk","bridge"],
 "people":[{"key":"mei","name":"Mei","lang":"zh","user":true,"forms":["Mei","美"]},
           {"key":"arjun","name":"Arjun","lang":"en","user":true},{"key":"priya","name":"Priya","lang":"en","user":true},
           {"key":"lin","name":"Lin","user":false,"forms":["林","Lin","Lynn"]}],
 "ties":[{"a":"mei","b":"lin","kind":"friend","context":"from the Fudan climbing wall","day":0,"said_by":"mei","heard_by":["arjun"]},
         {"a":"priya","b":"lin","kind":"friend","context":"","day":30,"said_by":"priya","heard_by":[]}],
 "facts":[{"key":"boulder","subject":"arjun","speaker":"arjun","predicate":"started","text":"started bouldering",
           "keys":[["bouldering","climbing","climb","攀岩","抱石"]],"day":36,"source":"sms","audience":["arjun"],"told":["priya"],
           "sensitive_kind":"","storyline":null}],
 "evidence":[{"knower":"arjun","item":{"kind":"person","key":"lin"},"ev":"heard","day":0}],
 "probe":{"day":42,"participants":["mei","arjun","priya"],"speaker":"mei","text":"我和林去攀岩了",
          "partials":["我和林","我和林去攀岩"],"translations":{"en":"I went climbing with Lin."}},
 "expect":{"arjun":{"cards":[{"kind":"who","key":"lin","gap":"reminder"},{"kind":"bridge","key":"boulder"}]},
           "priya":{"cards":[]},"mei":{"cards":[]}}}
```

  About 30 planted minimal-pair scenarios: never heard; heard 6 days; heard 42 days; heard 3 times spaced over 60 days;
  said it yourself; shown yesterday; asked last time; tie owner; group member; co-participant; cross-circle (Paatti and
  Mei, with and without Arjun's own "lives in Shanghai"); sensitive; third party expired; pinned; paused; same-language
  friends (no MT, cards still on); 林 vs 林檎; Lin/Lynn/Lín; Thai unspaced; two Lins (ambiguous -> ask); Tamil kin word;
  contradiction; storyline behind vs current; bridge irrelevant topic; bridge told; bridge rate limit and next-day repeat;
  SMS-only fact never shown to others; non-self fact about the listener said by someone else (never a bridge).
- **Runner** (`backend/eval/run_cg.py [--limit N] [--out path] [--sweep]`): fresh temp SQLite per scenario; rows written
  through `world.apply`/store helpers with `clock` offsets; builds a `LiveWorld` with a capture `emit`; drives
  `join` for participants, `on_partial` for each partial, `on_final`, then `on_translated` with `probe.translations`;
  collects per-listener sends. No LLM (no network); `--live-extract` (optional, cut-line) runs real extraction on line text.
- **Metrics** (`eval/common_ground/results.md`; never overwrite `eval/results.md`):
  gap precision/recall over (listener, key) for who/what, gap-kind accuracy (new vs reminder), bridge precision and
  recall, storyline P/R, threshold sweep (`FORGOT` in 0.20..0.50 step 0.05) as a P/R table, `on_partial` p50/p95 per
  listener on the scenarios and on a synthetic 500-person / 1500-alias world, and **hard-fail counters that must be 0**:
  non-self bridge, bridge to someone in the audience, card citing a fact not usable for its listener (guard drops),
  SMS fact in another listener's card. The runner exits non-zero when any counter is above 0 or p95 > 10 ms.
- `tests/test_cg_eval.py` runs `python -m eval.run_cg --limit 10 --out <tmp>` as a subprocess and asserts exit 0 and
  the table headers.

---

## 12. Keep, refactor, retire

| Code | Decision | Reason |
|---|---|---|
| `llm.py`, ASR adapters, `tts.py`, `rtc/agent.py` mechanics, `routing.ts`, `call.ts` plumbing | Keep | Already per-identity and robust |
| `graph/kinship.py` | Keep + `person_ids` filter | Kin math is the grounding core and the Paatti beat |
| `graph/linker.py` | Keep; `lang` param, `keyterms` includes names | Eval pins it; runs only on finals |
| `graph/builder.py` | Keep; used by `place` for kin | Placeholder logic works with `anchor=` |
| `cards/matcher.py`, `lexicon.py` | Keep; lexicon by speaker language | Fast, tested |
| `cards/glance.py` | Keep for legacy calls only | World cards come from `world/cards.py` |
| `mt/translate.py`, `mt/schemas.py` | Additive changes (8.4) | Eval stability |
| `audio/pipeline.py` | Refactor: identity keys, world branch, pause, per-listener sends, TTS tasks | The core of the pivot |
| `memory/service.py` | Keep for legacy end/approve; fix leaks and slugs | Live bugs today |
| `fade/*`, `api/fade.py` | Keep as the optional legacy mode; off in world calls | `test_bkt`/`test_fade` pin it |
| `api/connector.py` | Keep, demo-family scoped, never reads world tables | Read-only legacy surface |
| `buddy.py`, `twilio.py`, `twilio_bridge.py`, `direction.py`, overlay, `phone.html` | Keep as legacy "bring KIN into any call" | Spec keeps them in the repo |
| `app/audio/agent.py` | Delete | Dead stub with stale docs |
| `frontend/` | Retire (left in repo, removed from README run steps) | Hard-codes seed slugs |
| `cards/images.py` | Keep, off in world calls | Shelved per spec |
| mobile `Join.tsx`, `Setup.tsx`, grandparent/grandchild views | Replace | Same app for everyone |
| `Consent`, `KinTerm` reads, `embeddings_provider` | Leave in place, unused | Tests pin seeding |

---

## 13. Implementation waves

Rules: one shared working tree; no two tasks in a wave own the same file; a task edits only files it owns (new test
files included). Each task reports its DECISIONS lines in its final message; only task 4C writes `docs/DECISIONS.md`.
Gate for every backend task: `cd backend && .venv/bin/python -m pytest -q` green and
`.venv/bin/python -m eval.run_eval --mock --limit 20 --out /tmp/e.md` exits 0. Mobile tasks: `cd mobile && npm test`.
Sizes: S <= 150 changed lines, M <= 400, L <= 800.

| Wave | Task | Owns | Depends | Size |
|---|---|---|---|---|
| 1 | 1A Schema, pragmas, users helpers | `backend/app/db/models.py`, `backend/app/db/session.py`, `backend/app/world/users.py`, `backend/tests/test_world_schema.py` | none | M |
| 1 | 1B Contracts, stubs, router registration | `backend/app/world/__init__.py`, `backend/app/world/contracts.py`, `backend/app/world/live.py` (stub), `backend/app/api/users.py`, `backend/app/api/world.py`, `backend/app/api/dev.py`, `backend/app/api/sms.py` (stubs), `backend/app/main.py`, `backend/tests/test_contracts.py`, `mobile/src/contracts.ts` | none | M |
| 1 | 1C Knowledge math, visibility, clock, config | `backend/app/world/knowledge.py`, `backend/app/world/visibility.py`, `backend/app/world/clock.py`, `backend/app/config.py`, `backend/tests/test_knowledge.py`, `backend/tests/test_visibility_rules.py` | none | M |
| 1 | 1D Cross-script matcher | `backend/app/world/match.py`, `backend/tests/test_match.py` | none | M |
| 1 | 1E CG scenario data | `backend/eval/common_ground/__init__.py`, `backend/eval/common_ground/schemas.py`, `backend/eval/common_ground/scenarios.jsonl`, `backend/tests/test_cg_testset.py` | none | M |
| 2 | 2A WorldView and render | `backend/app/world/view.py`, `backend/app/graph/kinship.py`, `backend/tests/test_world_view.py` | 1A, 1C, 1D | L |
| 2 | 2B Privacy ops and legacy leaks | `backend/app/world/privacy.py`, `backend/app/memory/service.py`, `backend/app/fade/service.py`, `backend/tests/test_delete.py`, `backend/tests/test_memory_connector.py` | 1A, 1C | M |
| 2 | 2C Extraction and apply | `backend/app/world/extract.py`, `backend/app/world/apply.py`, `backend/tests/test_extract_apply.py` | 1A, 1B, 1C | L |
| 2 | 2D Translator and linker | `backend/app/mt/translate.py`, `backend/app/mt/schemas.py`, `backend/app/graph/linker.py`, `backend/tests/test_translate_world.py` | 1B | M |
| 2 | 2E Mobile app shell and video | `mobile/src/api.ts`, `mobile/src/App.tsx`, `mobile/src/Home.tsx`, `mobile/src/Signup.tsx`, `mobile/src/links.ts`, `mobile/src/Join.tsx`, `mobile/src/Setup.tsx`, `mobile/src/call.ts`, `mobile/src/routing.ts`, `mobile/src/Tiles.tsx`, `mobile/test/links.test.ts`, `mobile/test/routing.test.ts` | 1B | L |
| 3 | 3A LiveWorld and card engine | `backend/app/world/live.py`, `backend/app/world/cards.py`, `backend/tests/test_cg_cards.py`, `backend/tests/test_live_world.py` | 2A, 2C, 2D | L |
| 3 | 3B N-party pipeline | `backend/app/audio/pipeline.py`, `backend/app/api/calls.py`, `backend/tests/test_group_call.py` | 2D, 1B | L |
| 3 | 3C REST, dev and SMS | `backend/app/api/users.py`, `backend/app/api/world.py`, `backend/app/api/dev.py`, `backend/app/api/sms.py`, `backend/app/world/sms.py`, `backend/tests/test_world_api.py`, `backend/tests/test_sms.py` | 2A, 2B, 2C | L |
| 3 | 3D RTC world join | `backend/app/api/rtc.py`, `backend/app/rtc/agent.py`, `backend/tests/test_rtc_world.py` | 1A, 1B | M |
| 4 | 4A CG eval harness | `backend/eval/run_cg.py`, `backend/tests/test_cg_eval.py` | 3A, 1E | M |
| 4 | 4B Mobile call UI and cards | `mobile/src/Call.tsx`, `mobile/src/cards.ts`, `mobile/src/Rail.tsx`, `mobile/src/style.css`, `mobile/test/cards.test.ts` | 2E, 1B | L |
| 4 | 4C Decisions, demo driver, cleanup | `docs/DECISIONS.md`, `docs/DEMO.md`, `scripts/demo_common_ground.py`, `backend/app/audio/agent.py` (delete), `README.md` | waves 1-3 | M |

Same-wave coupling is only through interfaces fixed in this file: 3B tests use a fake `LiveWorld` with the 8.5
signatures; 3C's pause/feedback/text routes are in 3B's `api/calls.py`; 3D's tests do not run a `CallSession`.

After wave 3 the orchestrator runs one live check (`python -m eval.run_eval` with a key, and a 3-browser LiveKit call
on `livekit-server --dev`) and passes the numbers to 4C.

---

## 14. Risks and cut-line

Risks:

1. **ASR for the headline sentence**: whether Muse returns 林 or "Lin", and whether non-Latin `keywords` are accepted,
   is unverified. Aliases hold both forms; typed text (`POST /api/calls/{id}/text`) is the backup.
2. **Call 1 extraction quality**: `/api/dev/apply` plants the same `WorldUpdateOut` through the same apply path.
3. **Group MT latency**: one A per distinct language (p50 about 1.9 s) plus about 3.5 s of Muse endpointing. Cards on
   stable partials hide it.
4. **Single-char CJK names**: cue rules and longest match; ambiguous mentions ask instead of guessing; 林檎 negative in eval.
5. **Pipeline refactor touches four transports**: legacy code paths left intact behind `if self.world`.
6. **Privacy regressions in a read path that skips `WorldView`**: the guard, section 10 tests and eval counters.
7. **SQLite contention**: WAL, short sessions, one knowledge flush per final.
8. **LiveKit video API shapes**: VERIFY in 2E before coding.
9. **Kin tables for 24 languages are unverified drafts**: demo kin claims only in Tamil.
10. **Old `kin.db`**: delete once.
11. **Tokens are bearer secrets in localStorage with no login**: stated hackathon limit.

Cut-line, demo-critical (in build order): 1A, 1B, 1C, 1D, 2A, 2C, 2D, 2E (audio + N peers), 3A (who/reminder +
bridges), 3B, 3C (users, place, dev clock, dev apply, dev SMS), 3D, 4B (rail with who/bridge/ask, KIN-on banner,
pause), 4C demo driver. Then 2B, 1E + 4A for the Devpost numbers.

Cut first, in this order: storyline cards (schema stays); contradiction handling beyond self-report supersede; real
Twilio inbound (dev endpoint stays); localized card bodies beyond Tamil and Chinese; English relational anaphora;
`--live-extract` eval mode; account-deletion UI (API stays); bridge rerank; video tiles last (the audio call works
without them).
