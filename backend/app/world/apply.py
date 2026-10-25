"""Write a validated WorldUpdateOut into the world graph (docs/ARCHITECTURE.md 6.3, 6.4) and place people from
"Who is X?" answers (2.5). Pure DB writes plus returned evidence; never calls the LLM. The caller commits and applies
the evidence to its knowledge cache.
"""
from __future__ import annotations

import logging
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import models as m
from ..graph import builder
from ..graph.kin_tables import SCRIPT
from . import clock
from .contracts import EntityOut, FactOut, WorldUpdateOut
from .extract import ENTITY_TABLE, SENSITIVE, TIE_KINDS, clean_forms, reduce_sensitive
from .match import fold, script_of
from .users import _fold

log = logging.getLogger("kin.world.apply")

PREFIX = {"person": "p", "place": "pl", "event": "ev", "thing": "th", "group": "g", "storyline": "s"}
TERMINAL = frozenset({"offer accepted", "accepted", "done", "moved", "finished", "ended"})
TITLE_MATCH = 70
SHARED_CONCEPTS = 2

Evidence = tuple[int, str, int, str]  # (knower, item kind, item id, ev)


@dataclass(frozen=True)
class ApplyCtx:
    space_id: int
    call_id: int | None
    message_id: int | None
    speaker_of_line: dict[int, int]
    audience_of_line: dict[int, list[int]]  # speaker excluded
    utterance_of_line: dict[int, int]
    now: datetime
    source_kind: str = "call"  # call|message|card|setup
    shareable: bool = True


@dataclass(frozen=True)
class ApplyResult:
    facts: list[int] = field(default_factory=list)
    entities: dict[str, int] = field(default_factory=dict)  # ref -> row id
    evidence: list[Evidence] = field(default_factory=list)


def world_slug(prefix: str, name: str, row_id: int) -> str:
    """Section 1.1: prefix_<ascii fold>_<id>; an all-CJK name gives prefix_<id>."""
    folded = _fold(name)
    return f"{prefix}_{folded}_{row_id}" if folded else f"{prefix}_{row_id}"


def form_lang(form: str, prefer: Iterable[str]) -> str:
    """The form's language from its script: a preferred language whose script matches, else any, else en for Latin."""
    letters = [c for c in form if c.isalpha()]
    if not letters or all(script_of(c) == "latin" for c in letters):
        return "en"
    codes = list(dict.fromkeys([*prefer, *SCRIPT]))
    return next((c for c in codes if c in SCRIPT and re.search(SCRIPT[c], form)), "")


def _aware(t: datetime | None) -> datetime | None:
    return t if t is None or t.tzinfo else t.replace(tzinfo=timezone.utc)


def _by_slug(s: Session, space_id: int, slug: str) -> tuple[str, int] | None:
    for table, model in (("person", m.Person), ("thing", m.Thing), ("group", m.Group)):
        rid = s.scalar(select(model.id).where(model.family_id == space_id, model.slug == slug))
        if rid is not None:
            return table, rid
    return None


def _is_user(s: Session, person_id: int) -> bool:
    return s.scalar(select(m.User.id).where(m.User.person_id == person_id)) is not None


def _user_lang(s: Session, person_id: int) -> str:
    return s.scalar(select(m.User.lang).where(m.User.person_id == person_id)) or ""


# ---------------------------------------------------------------------------------------------------------------------
# entities


def _new_person(s: Session, space_id: int, name: str, native: str = "") -> m.Person:
    p = m.Person(family_id=space_id, slug=f"tmp_{secrets.token_hex(8)}", display_name=name, lang_name=native)
    s.add(p)
    s.flush()
    p.slug = world_slug("p", name, p.id)
    s.flush()
    return p


def _add_person_forms(s: Session, person: m.Person, forms: list[str], prefer: list[str], kind: str) -> None:
    have = {fold(a.alias)[0] for a in person.aliases}
    for f in forms:
        if fold(f)[0] not in have:
            have.add(fold(f)[0])
            person.aliases.append(m.Alias(alias=f, lang=form_lang(f, prefer), kind=kind))


def _entity(s: Session, ctx: ApplyCtx, e: EntityOut, prefer: list[str]) -> tuple[str, int]:
    table = ENTITY_TABLE[e.kind]
    forms = clean_forms([e.name, e.native, *e.forms])
    if e.existing_id is not None:
        if table == "person":
            person = s.get(m.Person, e.existing_id)
            _add_person_forms(s, person, forms, prefer, "asr")  # known name heard in a new script (3.3)
        elif table == "thing":
            thing = s.get(m.Thing, e.existing_id)
            thing.aliases = list(dict.fromkeys([*(thing.aliases or []), *forms]))
        return table, e.existing_id
    if table == "person":
        person = _new_person(s, ctx.space_id, e.name, e.native)
        _add_person_forms(s, person, forms, prefer, "translit")
        s.flush()
        return "person", person.id
    model = m.Thing(family_id=ctx.space_id, slug="tmp", kind=e.kind, name=e.name, lang_name=e.native,
                    aliases=forms) if table == "thing" else m.Group(family_id=ctx.space_id, slug="tmp", name=e.name,
                                                                     lang_name=e.native)
    model.slug = f"tmp_{secrets.token_hex(8)}"  # the slug needs the id: rename after flush
    s.add(model)
    s.flush()
    model.slug = world_slug(PREFIX[e.kind], e.name, model.id)
    s.flush()
    return table, model.id


# ---------------------------------------------------------------------------------------------------------------------
# facts


def _audience(s: Session, fact_id: int, speaker: int | None, heard: Iterable[int], at: datetime, call_id: int | None,
              speaker_via: str) -> None:
    """FactAudience rows; existing rows are kept (merge, never downgrade)."""
    have = set(s.scalars(select(m.FactAudience.person_id).where(m.FactAudience.fact_id == fact_id)))
    rows = ([(speaker, speaker_via)] if speaker is not None else []) + [(p, "heard") for p in heard]
    for pid, via in rows:
        if pid not in have:
            have.add(pid)
            s.add(m.FactAudience(fact_id=fact_id, person_id=pid, via=via, at=at, call_id=call_id))


def _said_at(s: Session, ctx: ApplyCtx, lines: list[int]) -> datetime:
    uid = ctx.utterance_of_line.get(lines[0])
    u = s.get(m.Utterance, uid) if uid is not None else None
    return _aware(u.created_at) if u is not None and u.created_at else ctx.now


def _mark_sensitive(s: Session, ctx: ApplyCtx, lines: list[int], topic: str) -> None:
    for n in lines:
        uid = ctx.utterance_of_line.get(n)
        u = s.get(m.Utterance, uid) if uid is not None else None
        if u is not None and not u.sensitive_topic:
            u.sensitive_topic = topic


def _evidence(fact_id: int, speaker: int, heard: list[int], refs: list[tuple[str, int]], speaker_ev: str) -> list[Evidence]:
    items = [("fact", fact_id), *refs]
    return [(speaker, k, i, speaker_ev) for k, i in items] + [(p, k, i, "heard") for p in heard for k, i in items]


def apply_update(s: Session, update: WorldUpdateOut, ctx: ApplyCtx) -> ApplyResult:
    """Write entities, facts (with audience and refs), ties and storyline states. `update` must come from
    extract.validate; sensitive reduction is re-applied here because it is a hard privacy rule."""
    ttl = timedelta(days=get_settings().third_party_ttl_days)
    speaker_via = "authored" if ctx.source_kind == "message" else "said"
    speakers = sorted(set(ctx.speaker_of_line.values()))
    prefer = list(dict.fromkeys(_user_lang(s, p) for p in speakers)) + ["zh"]
    created = {e.ref: _entity(s, ctx, e, prefer) for e in update.entities}
    new_rows = {created[e.ref] for e in update.entities if e.existing_id is None}

    def resolve(token: str, speaker: int) -> tuple[str, int] | None:
        if token == "speaker":
            return "person", speaker
        return created.get(token) or _by_slug(s, ctx.space_id, token)

    fact_ids: list[int] = []
    evidence: list[Evidence] = []
    tie_fact: dict[tuple[tuple[str, int], tuple[str, int]], int] = {}
    for fo in update.facts:
        fo = reduce_sensitive(fo)
        speaker = ctx.speaker_of_line[fo.lines[0]]
        heard = sorted({p for n in fo.lines for p in ctx.audience_of_line.get(n, []) if p != speaker})
        subj = resolve(fo.subject, speaker)
        refs = [r for r in (resolve(t, speaker) for t in fo.refs) if r is not None]
        is_user = _is_user(s, subj[1])
        if is_user and subj[1] != speaker:  # 6.2 again with the DB: the prompt may not have flagged every user
            log.warning("dropped fact about user %s cited from speaker %s's lines", subj[1], speaker)
            continue
        said_at = _said_at(s, ctx, fo.lines)
        if fo.same_as is not None and s.get(m.Fact, fo.same_as) is not None:
            _audience(s, fo.same_as, speaker, heard, said_at, ctx.call_id, speaker_via)
            fact_ids.append(fo.same_as)
            evidence += _evidence(fo.same_as, speaker, heard, refs, speaker_via)
            continue
        third = not is_user
        f = m.Fact(family_id=ctx.space_id, subject_id=subj[1], speaker_id=speaker, predicate=fo.predicate[:16],
                   text=fo.text_en[:400], text_src=fo.text_src[:400], lang=_user_lang(s, speaker), keys=fo.keys,
                   source_kind=ctx.source_kind, call_id=ctx.call_id, utterance_id=ctx.utterance_of_line.get(fo.lines[0]),
                   message_id=ctx.message_id, said_at=said_at, sensitive_kind=fo.sensitive_kind if fo.sensitive_kind in SENSITIVE else "",
                   shareable=ctx.shareable, third_party=third, expires_at=said_at + ttl if third else None)
        s.add(f)
        s.flush()
        _audience(s, f.id, speaker, heard, said_at, ctx.call_id, speaker_via)
        for kind, rid in dict.fromkeys(refs):
            s.add(m.FactRef(fact_id=f.id, kind=kind, ref_id=rid))
        if f.sensitive_kind:
            _mark_sensitive(s, ctx, fo.lines, f.sensitive_kind)
        if fo.predicate == "tie":
            for r in refs:
                tie_fact.setdefault((subj, r), f.id)
        fact_ids.append(f.id)
        evidence += _evidence(f.id, speaker, heard, refs, speaker_via)
        if fo.storyline is not None or fo.contradicts is not None:
            evidence += _storyline(s, ctx, f, fo, speaker, heard, speaker_via)
        _own_things(s, f, [r for r in refs if r in new_rows])
    for t in update.ties:
        _tie(s, ctx, t.kind, t.context, tie_fact, resolve, speakers, t.a, t.b)
    s.flush()
    return ApplyResult(fact_ids, {ref: rid for ref, (_, rid) in created.items()}, evidence)


def _own_things(s: Session, f: m.Fact, refs: list[tuple[str, int]]) -> None:
    """A thing/group created in this update belongs to the world of the first fact that mentions it. Existing rows
    are never re-owned: Thing.fact_id cascades, so a shared row would die with that fact."""
    for kind, rid in refs:
        row = s.get(m.Thing, rid) if kind == "thing" else s.get(m.Group, rid) if kind == "group" else None
        if row is None or row.fact_id is not None:
            continue
        row.fact_id = f.id
        if kind == "thing" and row.owner_id is None:
            row.owner_id = f.subject_id


def _tie(s: Session, ctx: ApplyCtx, kind: str, context: str, tie_fact: dict, resolve, speakers: list[int],
         a_tok: str, b_tok: str) -> None:
    for sp in speakers:  # the validator guaranteed a matching tie fact for one of them
        a, b = resolve(a_tok, sp), resolve(b_tok, sp)
        fid = tie_fact.get((a, b))
        if fid is None:
            continue
        if b[0] == "group":
            if s.scalar(select(m.GroupMember.id).where(m.GroupMember.group_id == b[1], m.GroupMember.person_id == a[1])) is None:
                s.add(m.GroupMember(group_id=b[1], person_id=a[1], fact_id=fid))
            return
        exists = s.scalar(select(m.Tie.id).where(m.Tie.src_person == a[1], m.Tie.dst_person == b[1], m.Tie.status == "active"))
        if exists is None:
            s.add(m.Tie(family_id=ctx.space_id, src_person=a[1], dst_person=b[1],
                        kind=kind if kind in TIE_KINDS else "knows", context=context[:160], fact_id=fid, created_at=ctx.now))
        return
    log.warning("tie %s->%s skipped: no tie fact written", a_tok, b_tok)


# ---------------------------------------------------------------------------------------------------------------------
# storylines (6.4)


def _concepts(keys: list) -> list[set[str]]:
    return [{fold(str(f))[0].strip() for f in g if str(f).strip()} for g in keys or []]


def shared_concepts(a: list, b: list) -> int:
    gb = _concepts(b)
    return sum(1 for g in _concepts(a) if any(g & h for h in gb))


def _find_storyline(s: Session, ctx: ApplyCtx, owner: int, title: str, keys: list) -> m.Storyline | None:
    for st in s.scalars(select(m.Storyline).where(m.Storyline.family_id == ctx.space_id, m.Storyline.owner_id == owner)):
        if fuzz.token_set_ratio(title.lower(), st.title.lower()) >= TITLE_MATCH or shared_concepts(keys, st.keys) >= SHARED_CONCEPTS:
            return st
    return None


def _states(s: Session, story_id: int) -> list[m.StorylineState]:
    return list(s.scalars(select(m.StorylineState).where(m.StorylineState.storyline_id == story_id).order_by(m.StorylineState.seq)))


def _storyline(s: Session, ctx: ApplyCtx, f: m.Fact, fo: FactOut, speaker: int, heard: list[int], speaker_via: str) -> list[Evidence]:
    evidence: list[Evidence] = []
    story = None
    so = fo.storyline
    if so is not None:
        story = s.get(m.Storyline, so.existing_id) if so.existing_id is not None else None
        if story is None or story.owner_id != f.subject_id:
            story = _find_storyline(s, ctx, f.subject_id, so.title, fo.keys)
        if story is None:
            story = m.Storyline(family_id=ctx.space_id, slug="tmp", owner_id=f.subject_id, title=so.title[:120] or f.text[:120],
                                keys=fo.keys, created_at=ctx.now, updated_at=ctx.now)
            s.add(story)
            s.flush()
            story.slug = world_slug("s", story.title, story.id)
        states = _states(s, story.id)
        label = (so.state_label or f.text)[:80]
        state = m.StorylineState(storyline_id=story.id, seq=(states[-1].seq + 1) if states else 1, label=label,
                                 fact_id=f.id, at=f.said_at)
        s.add(state)
        s.flush()
        f.storyline_id = story.id
        story.updated_at = ctx.now
        if speaker == story.owner_id:  # progression: the owner's self-report supersedes their older states
            for old in states:
                if old.status == "active" and _aware(old.at) <= f.said_at:
                    old.status = "superseded"
                    _supersede(s, old.fact_id, f.id)
        if so.resolved or label.strip().lower() in TERMINAL:
            story.status, f.status = "resolved", "resolved"
        evidence += [(speaker, "state", state.id, speaker_via)] + [(p, "state", state.id, "heard") for p in heard]
    if fo.contradicts is not None:
        _contradict(s, f, fo.contradicts, speaker, story)
    s.flush()
    return evidence


def _supersede(s: Session, old_fact_id: int, new_fact_id: int) -> None:
    old = s.get(m.Fact, old_fact_id)
    if old is not None and old.id != new_fact_id and old.status in ("active", "contradicted"):
        old.status, old.superseded_by = "superseded", new_fact_id


def _contradict(s: Session, f: m.Fact, other_id: int, speaker: int, story: m.Storyline | None) -> None:
    other = s.get(m.Fact, other_id)
    if other is None:
        return
    if speaker == other.subject_id:  # people update their own news
        _supersede(s, other.id, f.id)
        for st in s.scalars(select(m.StorylineState).where(m.StorylineState.fact_id == other.id)):
            st.status = "superseded"
        return
    other.status = f.status = "contradicted"
    for st in s.scalars(select(m.StorylineState).where(m.StorylineState.fact_id.in_([other.id, f.id]))):
        st.status = "contradicted"
    for sid in {story.id if story else None, other.storyline_id, f.storyline_id} - {None}:
        s.get(m.Storyline, sid).unresolved = True


# ---------------------------------------------------------------------------------------------------------------------
# "Who is X?" answers (2.5)


def _find_person(s: Session, space_id: int, name: str) -> m.Person | None:
    key = fold(name)[0].strip()
    if not key:
        return None
    for p in s.scalars(select(m.Person).where(m.Person.family_id == space_id)):
        forms = [p.display_name, p.lang_name, *(a.alias for a in p.aliases)]
        if any(f and fold(f)[0].strip() == key for f in forms):
            return p  # ponytail: first name match wins; two people with one name need the slug from the ask card
    return None


def _card_fact(s: Session, space_id: int, me: int, subject: int, text: str, at: datetime, call_id: int | None,
               told: Iterable[int], call_audience: Iterable[int]) -> m.Fact:
    third = not _is_user(s, subject)
    f = m.Fact(family_id=space_id, subject_id=subject, speaker_id=me, predicate="tie", text=text[:400], lang="en",
               source_kind="card", call_id=call_id, said_at=at, third_party=third,
               expires_at=at + timedelta(days=get_settings().third_party_ttl_days) if third else None)
    s.add(f)
    s.flush()
    s.add(m.FactAudience(fact_id=f.id, person_id=me, via="card", at=at, call_id=call_id))
    seen = {me}
    for pid, via in [*((p, "told") for p in told), *((p, "heard") for p in call_audience)]:
        if pid not in seen:
            seen.add(pid)
            s.add(m.FactAudience(fact_id=f.id, person_id=pid, via=via, at=at, call_id=call_id))
    return f


def place_person(s: Session, space_id: int, me: int, name: str, owner: int, relation: str, context: str = "",
                 call_audience: Iterable[int] = (), *, person: str | None = None, now: datetime | None = None,
                 call_id: int | None = None) -> tuple[m.Person, list[Evidence]]:
    """Put a person into `owner`'s world: a social Tie, or a kin path through link_kin (PlaceIn: name?, person?).
    `person` is an existing slug and must exist; otherwise `name` is matched, and only a name creates a new Person.
    Returns (person, 'confirmed' evidence for `me`). Raises LookupError for an unknown slug, ValueError for an
    unknown relation or a missing name."""
    now = now or clock.now()
    name = name.strip()
    if person is not None:
        found = s.scalars(select(m.Person).where(m.Person.family_id == space_id, m.Person.slug == person)).first()
        if found is None:
            raise LookupError(f"no person {person!r} in space {space_id}")
    else:
        found = _find_person(s, space_id, name)
    person = found
    if relation in TIE_KINDS:
        if person is None:
            if not name:
                raise ValueError("a new person needs a name")
            person = _new_person(s, space_id, name)
            person.aliases.append(m.Alias(alias=person.display_name, lang=form_lang(person.display_name, []), kind="name"))
        owner_p = s.get(m.Person, owner)
        text = f"{person.display_name} is {owner_p.display_name}'s {relation.replace('_', ' ')}" + (f" {context}" if context else "")
        f = _card_fact(s, space_id, me, owner, text, now, call_id, (owner, person.id), call_audience)
        s.add(m.FactRef(fact_id=f.id, kind="person", ref_id=person.id))
        s.add(m.Tie(family_id=space_id, src_person=owner, dst_person=person.id, kind=relation, context=context[:160],
                    fact_id=f.id, created_at=now))
        s.flush()
        return person, [(me, "person", person.id, "confirmed")]
    return link_kin(s, space_id, owner, relation, person.id if person else None, me=me, name=name,
                    call_audience=call_audience, now=now, call_id=call_id)


def link_kin(s: Session, space_id: int, anchor_id: int, path: str, person_id: int | None, *, me: int, name: str = "",
             call_audience: Iterable[int] = (), now: datetime | None = None, call_id: int | None = None
             ) -> tuple[m.Person, list[Evidence]]:
    """Attach `person_id` at kin `path` from the anchor, creating builder placeholders ("Mom") for missing middle
    steps. A person that does not exist yet goes through builder.add_relative unchanged. Every edge created here gets
    a card Fact whose audience is me, the endpoints and the call audience."""
    now = now or clock.now()
    if not path or not builder._valid(path):
        raise ValueError(f"unsupported relation: {path!r}")
    anchor = s.get(m.Person, anchor_id)
    fam = s.get(m.Family, space_id)
    before = set(s.scalars(select(m.Edge.id).where(m.Edge.family_id == space_id)))
    if person_id is None:
        if not name:
            raise ValueError("a new relative needs a name")
        person = builder.add_relative(s, space_id, path, name, anchor=anchor.slug)
    else:
        person = s.get(m.Person, person_id)
        cur = anchor
        steps = path.split(".")
        for i, step in enumerate(steps):
            last = i == len(steps) - 1
            found = builder._existing(s, space_id, cur.id, step)
            if last:
                if found != person.id:  # ponytail: an unnamed placeholder already at the last step stays; merge it if that shows up
                    builder._attach(s, fam, cur, person, step, "")
                break
            if found is None:
                gender, how = builder.STEPS[step]
                birth = cur.birth_year_approx and cur.birth_year_approx - builder.GENERATION.get(how, 0) * builder.GENERATION_YEARS
                new = builder._person(s, fam, builder.WORD.get(step, step), gender, birth, placeholder=True)
                builder._attach(s, fam, cur, new, step, "")
                cur = new
            else:
                cur = s.get(m.Person, found)
    new_edges = [e for e in s.scalars(select(m.Edge).where(m.Edge.family_id == space_id)) if e.id not in before]
    if new_edges:
        text = f"{person.display_name} is {anchor.display_name}'s {builder.path_label(path)[0].lower()}{builder.path_label(path)[1:]}"
        f = _card_fact(s, space_id, me, anchor.id, text, now, call_id, (anchor.id, person.id), call_audience)
        s.add(m.FactRef(fact_id=f.id, kind="person", ref_id=person.id))
        for e in new_edges:
            e.fact_id = f.id  # a NULL fact_id would make the edge visible to the whole space
        s.flush()
    return person, [(me, "person", person.id, "confirmed")]
