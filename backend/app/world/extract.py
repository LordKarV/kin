"""World extraction: prompt, LLM call and validator (docs/ARCHITECTURE.md 6.1, 6.2).

The prompt is privacy-scoped: each speaker's section holds only that speaker's own facts and the entities visible to
that speaker. The validator drops anything it cannot tie to the right speaker's lines; it never repairs a guess.
`apply.apply_update` writes the clean update.
"""
from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable

import openai
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..cards.lexicon import _mixed_script
from ..db import models as m
from ..llm import LLM, StructuredOutputError, get_llm
from .contracts import EntityOut, FactOut, TieOut, WorldUpdateOut
from .match import script_of

log = logging.getLogger("kin.world.extract")

MAX_CANDIDATES = 60
MAX_OWN_FACTS = 60
MAX_FORMS = 8
SENSITIVE = ("health", "money", "conflict")
TIE_KINDS = frozenset({"friend", "close_friend", "partner", "roommate", "classmate", "coworker", "teammate", "knows"})
ENTITY_TABLE = {"person": "person", "place": "thing", "event": "thing", "thing": "thing", "group": "group"}


@dataclass(frozen=True)
class Line:
    n: int  # line number the model cites
    speaker_id: int
    lang: str
    text: str


@dataclass(frozen=True)
class Participant:
    id: int
    slug: str
    name: str
    lang: str


@dataclass(frozen=True)
class Own:
    """One speaker's own context: facts they said (id, text) and storylines (id, title, latest state label)."""
    facts: tuple[tuple[int, str], ...] = ()
    storylines: tuple[tuple[int, str, str], ...] = ()


@dataclass(frozen=True)
class Candidate:
    kind: str  # person|thing|group (table, not EntityOut.kind)
    id: int
    slug: str
    name: str
    is_user: bool  # required: a forgotten flag would let a fact about a user through from someone else's lines
    forms: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidateCtx:
    speaker_of_line: dict[int, int]
    users: frozenset[int]  # person ids with a users row
    slugs: dict[str, tuple[str, int]]  # slug -> (table kind, id) for participants and candidates
    candidates: frozenset[tuple[str, int]]  # (table kind, id) the prompt offered
    fact_speaker: dict[int, int]  # own fact id -> its speaker
    storyline_speakers: dict[int, frozenset[int]] = field(default_factory=dict)  # storyline id -> speakers offered it
    names: dict[tuple[str, int], str] = field(default_factory=dict)  # (table kind, id) -> display name
    # speaker -> the known rows build_prompt offered that speaker (their KNOWN ENTITIES plus the participants)
    by_speaker: dict[int, frozenset[tuple[str, int]]] = field(default_factory=dict)


# ---------------------------------------------------------------------------------------------------------------------
# prompt

SYSTEM = """You update a shared world graph from a call transcript. Return JSON for the schema.

entities: people, places, events, things and groups mentioned in the lines. ref is a short local id ("e1").
  existing_id: the id of a KNOWN ENTITY of the same kind when the line refers to it, else null. Never invent ids.
  name: English or romanized name. native: the name in the script it was said in ("" if Latin).
  forms: up to 8 spellings, one script each: native, romanization (pinyin, romaji, RTGS, ISO-15919), the common
  English spelling, and the name written in each language listed under LANGUAGES.
ties: social relations. "b is a's <kind>", kind one of friend, close_friend, partner, roommate, classmate, coworker,
  teammate, knows. a/b: an entity ref, "speaker", or a person slug. Every tie needs a fact with predicate "tie",
  subject a, refs [b] that cites its lines.
facts: one claim each. subject: a person (entity ref, "speaker" for the person who said the cited lines, or a slug).
  predicate: tie|lives_in|from|works_at|studies_at|did|started|plans|state|attribute|mention.
  text_en: short canonical English ("started bouldering"). text_src: the original-language span.
  keys: concept groups, each a list of forms in English and in every LANGUAGES language ([["climbing","攀岩"]]).
  refs: entity refs or slugs the fact mentions. lines: the line numbers it comes from, all said by ONE speaker.
  A fact about a user may only come from that user's own lines.
  sensitive_kind: health, money or conflict when the fact is about one of those, else "".
  same_as: id of one of THIS speaker's own facts that says the same thing, else null.
  contradicts: id of one of THIS speaker's own facts that this one contradicts, else null.
  storyline: for an ongoing thread (job search, a move, an illness), else null. existing_id from the speaker's own
  storylines, title, state_label ("applied", "second round", "offer accepted"), resolved when the thread is over.
Only state what the lines say. Leave out anything you are unsure about. Use "" / null / [] for none."""


def build_prompt(window_lines: list[Line], participants: list[Participant], own_facts_by_speaker: dict[int, Own],
                 candidates: dict[int, list[Candidate]], langs: Iterable[str]) -> tuple[str, str]:
    """(system, user). Stable prefix first (participants, per-speaker context, languages), utterances last."""
    out = ["PARTICIPANTS (id | slug | name | lang)"]
    out += [f"{p.id} | {p.slug} | {p.name} | {p.lang}" for p in participants]
    names = {p.id: p.name for p in participants}
    for sid in sorted({ln.speaker_id for ln in window_lines}):
        own = own_facts_by_speaker.get(sid, Own())
        out.append(f"\nSPEAKER {sid} ({names.get(sid, sid)}): OWN FACTS (id | text)")
        out += [f"{fid} | {text}" for fid, text in own.facts[:MAX_OWN_FACTS]] or ["(none)"]
        out.append(f"SPEAKER {sid}: OWN STORYLINES (id | title | latest state)")
        out += [f"{st_id} | {title} | {label}" for st_id, title, label in own.storylines] or ["(none)"]
        out.append(f"SPEAKER {sid}: KNOWN ENTITIES (id | kind | slug | name | forms)")
        out += [f"{c.id} | {c.kind} | {c.slug} | {c.name} | {', '.join(c.forms)}"
                for c in candidates.get(sid, [])[:MAX_CANDIDATES]] or ["(none)"]
    out.append("\nLANGUAGES: " + ", ".join(dict.fromkeys(langs)))
    out.append("\nLINES (n | speaker id | lang | text)")
    out += [f"{ln.n} | {ln.speaker_id} | {ln.lang} | {ln.text}" for ln in window_lines]
    return SYSTEM, "\n".join(out)


def own_context(s: Session, person_id: int, limit: int = MAX_OWN_FACTS) -> Own:
    """Active facts this person said, and storylines they own or reported a state of."""
    facts = s.scalars(select(m.Fact).where(m.Fact.speaker_id == person_id, m.Fact.status == "active")
                      .order_by(m.Fact.said_at.desc()).limit(limit)).all()
    reported = select(m.StorylineState.storyline_id).join(m.Fact, m.Fact.id == m.StorylineState.fact_id).where(
        m.Fact.speaker_id == person_id)
    stories = s.scalars(select(m.Storyline).where((m.Storyline.owner_id == person_id) | m.Storyline.id.in_(reported))).all()
    out = []
    for st in stories:
        last = s.scalars(select(m.StorylineState).where(m.StorylineState.storyline_id == st.id)
                         .order_by(m.StorylineState.seq.desc()).limit(1)).first()
        out.append((st.id, st.title, last.label if last else ""))
    return Own(tuple((f.id, f.text) for f in facts), tuple(out))


def validate_ctx(window_lines: list[Line], participants: list[Participant], own_facts_by_speaker: dict[int, Own],
                 candidates: dict[int, list[Candidate]]) -> ValidateCtx:
    """The validator's view of exactly what build_prompt offered."""
    slugs = {p.slug: ("person", p.id) for p in participants}
    cands = {(c.kind, c.id) for cs in candidates.values() for c in cs[:MAX_CANDIDATES]}
    for cs in candidates.values():
        slugs.update({c.slug: (c.kind, c.id) for c in cs[:MAX_CANDIDATES]})
    users = {p.id for p in participants} | {c.id for cs in candidates.values() for c in cs if c.is_user and c.kind == "person"}
    fact_speaker, story_speakers = {}, {}
    for sid, own in own_facts_by_speaker.items():
        fact_speaker.update({fid: sid for fid, _ in own.facts[:MAX_OWN_FACTS]})
        for st_id, _, _ in own.storylines:
            story_speakers[st_id] = story_speakers.get(st_id, frozenset()) | {sid}
    names = {("person", p.id): p.name for p in participants}
    names.update({(c.kind, c.id): c.name for cs in candidates.values() for c in cs[:MAX_CANDIDATES]})
    parts = frozenset(("person", p.id) for p in participants)
    by_speaker = {sid: parts | {(c.kind, c.id) for c in candidates.get(sid, [])[:MAX_CANDIDATES]}
                  for sid in {ln.speaker_id for ln in window_lines}}
    return ValidateCtx({ln.n: ln.speaker_id for ln in window_lines}, frozenset(users), slugs, frozenset(cands),
                       fact_speaker, story_speakers, names, by_speaker)


def run_extraction(llm: LLM | None, call_id: int | None, window_lines: list[Line], participants: list[Participant],
                   own_facts_by_speaker: dict[int, Own], candidates: dict[int, list[Candidate]],
                   langs: Iterable[str]) -> WorldUpdateOut | None:
    """One structured call. Any failure is logged and returns None: nothing is fabricated or retried here."""
    system, user = build_prompt(window_lines, participants, own_facts_by_speaker, candidates, langs)
    try:
        return (llm or get_llm()).structured(WorldUpdateOut, system, user, reasoning_effort="low",
                                             max_completion_tokens=4000, prompt_cache_key=f"kin-world-{call_id}")
    except (StructuredOutputError, openai.APIError, TimeoutError) as e:  # APIError covers timeouts and HTTP errors
        log.error("world extraction failed for call %s: %s: %s", call_id, type(e).__name__, e)
        return None


# ---------------------------------------------------------------------------------------------------------------------
# validator (6.2)


def resolve(token: str, speaker: int | None, refs: dict[str, EntityOut], ctx: ValidateCtx) -> tuple[str, int | str] | None:
    """A reference string -> ("person"|"thing"|"group", id) for known rows, ("new:<table>", ref) for a new entity."""
    if token == "speaker":
        return ("person", speaker) if speaker is not None else None
    if token in refs:
        e = refs[token]
        table = ENTITY_TABLE[e.kind]
        return (table, e.existing_id) if e.existing_id is not None else (f"new:{table}", token)
    return ctx.slugs.get(token)


def _is_person(r) -> bool:
    return r is not None and r[0] in ("person", "new:person")


def reduce_sensitive(f: FactOut) -> FactOut:
    """Topic word only (same rule as memory.service._reduce_sensitive): text = the kind, no source span, no keys,
    and a storyline titled and labelled with the topic word too (its title and label are shown in the world view)."""
    if not f.sensitive_kind:
        return f
    upd = {"text_en": f.sensitive_kind, "text_src": "", "keys": []}
    if f.storyline is not None:
        upd["storyline"] = f.storyline.model_copy(update={"title": f.sensitive_kind, "state_label": f.sensitive_kind})
    return f.model_copy(update=upd)


def _one_script(form: str) -> bool:
    """Base letters only: marks and modifier letters (ー, 々) carry no script of their own, and Latin with diacritics
    (Lín, Pāṭṭi) is still Latin. script_of catches Latin mixed with another script, which lexicon._mixed_script
    (non-ASCII only) misses. Known cost: Japanese kanji mixed with kana counts as two scripts."""
    letters = "".join(c for c in form if unicodedata.category(c) in ("Lu", "Ll", "Lt", "Lo"))
    return len({script_of(c) for c in letters}) <= 1 and not _mixed_script(letters)


def clean_forms(forms: Iterable[str]) -> list[str]:
    """One script per form, 1-40 chars, deduped, max 8 (3.3)."""
    out = [f.strip() for f in forms if 1 <= len(f.strip()) <= 40 and _one_script(f.strip())]
    return list(dict.fromkeys(out))[:MAX_FORMS]


def _check_entity(e: EntityOut, ctx: ValidateCtx, seen: set[str]) -> str | None:
    if not e.ref or e.ref in seen or e.ref == "speaker" or e.ref in ctx.slugs:
        return f"entity {e.ref!r}: missing, duplicate or shadowing ref"
    if e.existing_id is not None and (ENTITY_TABLE[e.kind], e.existing_id) not in ctx.candidates:
        return f"entity {e.ref!r}: existing_id {e.existing_id} not in the candidate list"
    if e.existing_id is None and not e.name.strip():
        return f"entity {e.ref!r}: new entity without a name"
    return None


def _check_fact(f: FactOut, refs: dict[str, EntityOut], ctx: ValidateCtx,
                introducer: dict[str, int]) -> tuple[str | None, FactOut]:
    """(reason or None, the fact reduced). `introducer` is updated for the new entities an accepted fact touches."""
    if not f.lines:
        return "cites no line", f
    if any(n not in ctx.speaker_of_line for n in f.lines):
        return f"cites a line outside the window {f.lines}", f
    speakers = {ctx.speaker_of_line[n] for n in f.lines}
    if len(speakers) != 1:
        return f"cites lines by several speakers {sorted(speakers)}", f
    speaker = speakers.pop()
    subj = resolve(f.subject, speaker, refs, ctx)
    if not _is_person(subj):
        return f"subject {f.subject!r} is not a known or new person", f
    if subj[0] == "person" and subj[1] in ctx.users and subj[1] != speaker:
        return f"fact about user {subj[1]} cited from speaker {speaker}'s lines", f
    if subj[0] == "new:person" and introducer.get(subj[1], speaker) != speaker:
        return f"third party {subj[1]!r} was introduced by speaker {introducer[subj[1]]}", f
    touched = [subj, *(resolve(r, speaker, refs, ctx) for r in f.refs)]
    if any(r is None for r in touched):
        return f"unknown ref in {f.refs}", f
    # Another speaker's KNOWN ENTITIES are private to them: linking to one would show it to this speaker and merge
    # two different people.
    offered = ctx.by_speaker.get(speaker, frozenset()) | {("person", speaker)}
    if any(not r[0].startswith("new:") and r not in offered for r in touched):
        return f"refs not offered to speaker {speaker}", f
    for name, fid in (("same_as", f.same_as), ("contradicts", f.contradicts)):
        if fid is not None and ctx.fact_speaker.get(fid) != speaker:
            return f"{name}={fid} is not one of speaker {speaker}'s own facts", f
    st = f.storyline
    if st is not None and st.existing_id is not None and speaker not in ctx.storyline_speakers.get(st.existing_id, ()):
        # the documented fallback (6.4 title match) handles a forgotten or wrong id; this is not a guess
        st = st.model_copy(update={"existing_id": None})
        f = f.model_copy(update={"storyline": st})
    for kind, ref in touched:
        if kind.startswith("new:"):
            introducer.setdefault(ref, speaker)
    return None, reduce_sensitive(f)


def _tie_fact(t: TieOut, facts: list[FactOut], refs: dict[str, EntityOut], ctx: ValidateCtx) -> FactOut | None:
    """The tie fact that carries this tie's provenance: predicate tie, subject a, b among its refs."""
    for f in facts:
        if f.predicate != "tie":
            continue
        sp = ctx.speaker_of_line[f.lines[0]]
        a, b = resolve(t.a, sp, refs, ctx), resolve(t.b, sp, refs, ctx)
        if a is not None and a == resolve(f.subject, sp, refs, ctx) and b in {resolve(r, sp, refs, ctx) for r in f.refs}:
            return f
    return None


def _synth_tie_fact(t: TieOut, speaker: int, refs: dict[str, EntityOut], ctx: ValidateCtx) -> FactOut | None:
    """6.3's tie Fact when the model sent a tie without one: subject a, refs [b], the speaker's first line."""
    a, b = resolve(t.a, speaker, refs, ctx), resolve(t.b, speaker, refs, ctx)
    if a is None or b is None:
        return None
    def name(r, token):
        return refs[r[1]].name if r[0].startswith("new:") else ctx.names.get(r, token)
    kind = t.kind if t.kind in TIE_KINDS else "knows"
    text = f"{name(b, t.b)} is {name(a, t.a)}'s {kind.replace('_', ' ')}" + (f" {t.context}" if t.context else "")
    line = min(n for n, sp in ctx.speaker_of_line.items() if sp == speaker)
    return FactOut(subject=t.a, predicate="tie", text_en=text, text_src="", keys=[], refs=[t.b], lines=[line],
                   sensitive_kind="", same_as=None, contradicts=None, storyline=None)


def _offered_entities(entities: list[EntityOut], facts: list[FactOut], dropped: list[str],
                      ctx: ValidateCtx) -> list[EntityOut]:
    """apply_update adds an existing entity's forms even when no fact cites it, so a known entity must have been
    offered to a speaker who said it: one whose accepted fact cites it (checked in _check_fact), or, when nothing
    cites it, every speaker in the window (whoever said it had it). Drops the rest, with a reason."""
    cited = {t for f in facts for t in (f.subject, *f.refs)}
    speakers = set(ctx.speaker_of_line.values())
    out = []
    for e in entities:
        key = (ENTITY_TABLE[e.kind], e.existing_id)
        if e.existing_id is None or e.ref in cited or all(key in ctx.by_speaker.get(sp, ()) for sp in speakers):
            out.append(e)
        else:
            dropped.append(f"entity {e.ref!r}: existing_id {e.existing_id} not offered to every speaker")
    return out


def validate(update: WorldUpdateOut, ctx: ValidateCtx) -> tuple[WorldUpdateOut, list[str]]:
    """Drop every item that breaks a 6.2 rule (and anything that depended on it). Returns (clean update, reasons)."""
    dropped: list[str] = []
    seen: set[str] = set()
    entities: list[EntityOut] = []
    for e in update.entities:
        why = _check_entity(e, ctx, seen)
        if why:
            dropped.append(why)
            continue
        seen.add(e.ref)
        entities.append(e.model_copy(update={"forms": clean_forms(e.forms)}))
    refs = {e.ref: e for e in entities}
    facts: list[FactOut] = []
    introducer: dict[str, int] = {}  # new entity ref -> speaker of the first fact about or mentioning it
    for i, f in enumerate(update.facts):
        why, f2 = _check_fact(f, refs, ctx, introducer)
        if why:
            dropped.append(f"fact #{i}: {why}")  # never the text: these are logged, and some were refused for privacy
        else:
            facts.append(f2)
    ties: list[TieOut] = []
    speakers = set(ctx.speaker_of_line.values())
    for t in update.ties:
        f = _tie_fact(t, facts, refs, ctx)
        synth = f is None and len(speakers) == 1  # one speaker: provenance is unambiguous (e.g. /api/dev/apply)
        if synth:
            f = _synth_tie_fact(t, next(iter(speakers)), refs, ctx)
        sp = ctx.speaker_of_line[f.lines[0]] if f else None
        ends = (resolve(t.a, sp, refs, ctx), resolve(t.b, sp, refs, ctx))
        if f is None or not _is_person(ends[0]) or ends[0] == ends[1] or ends[1] is None or ends[1][0] in ("thing", "new:thing"):
            dropped.append(f"tie {t.a}->{t.b}: no valid tie fact or bad endpoints")
            continue
        if synth:
            why, f = _check_fact(f, refs, ctx, introducer)
            if why:
                dropped.append(f"tie {t.a}->{t.b}: {why}")
                continue
            facts.append(f)
        ties.append(t if t.kind in TIE_KINDS else t.model_copy(update={"kind": "knows"}))
    entities = _offered_entities(entities, facts, dropped, ctx)
    for r in dropped:
        log.info("extraction dropped: %s", r)
    return WorldUpdateOut(entities=entities, ties=ties, facts=facts), dropped
