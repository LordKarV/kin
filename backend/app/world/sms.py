"""SMS ingest (docs/ARCHITECTURE.md section 7): one text from a user about their own life -> private facts in their world.

Every fact is the author's own (subject = speaker = author), never shareable, heard only by the author plus the people
the author says they told. The body is cleared once parsed. Also holds two small helpers the world REST routes share:
writing knowledge evidence and refreshing live calls after a world write.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import models as m
from ..db.session import session_scope
from ..llm import get_llm
from . import clock, knowledge
from .apply import ApplyCtx, Evidence, apply_update
from .contracts import FactOut, SmsFact, SmsOut, WorldUpdateOut
from .extract import Line, Participant, own_context, validate, validate_ctx
from .match import AliasIndex
from .view import WorldView

log = logging.getLogger("kin.world.sms")

BUDGET_S = 8.0  # section 7: reply within the Twilio webhook window (about 15 s, VERIFY)
MAX_BODY = 1600
ACK_MAX = 120
FALLBACK = "Got it."
UNKNOWN_REPLY = "This number isn't linked to KIN yet. Add it in the app under You."
SLOW_REPLY = "Slow down a little."
PREDICATES = frozenset({"did", "started", "plans", "state", "attribute", "lives_in", "from", "works_at", "studies_at"})

_PARSE = ThreadPoolExecutor(max_workers=4, thread_name_prefix="kin-sms")
_FINISH = ThreadPoolExecutor(max_workers=2, thread_name_prefix="kin-sms-retry")  # separate: it waits on _PARSE

SYSTEM = """You read one text message a person sent to KIN about their own life. Return JSON for the schema.

facts: one item per piece of news about the AUTHOR only. Leave out news about anyone else.
  predicate: did|started|plans|state|attribute|lives_in|from|works_at|studies_at.
  text_en: short canonical English without the author's name ("started bouldering", "got the internship").
  keys: concept groups, each a list of forms in English and in every LANGUAGES language ([["bouldering","climbing","攀岩"]]).
  sensitive_kind: health, money or conflict when the news is about one of those, else "".
  storyline: for an ongoing thread (job search, a move), else null. existing_id from OWN STORYLINES or null, title,
  state_label ("applied", "second round", "offer accepted"), resolved when the thread is over.
  told: names of people the author says already know this news ("told Priya" -> ["Priya"]), else [].
ack: at most 120 characters, restates the news back briefly. No advice, no questions, no follow-ups.
Only state what the message says. Use "" / null / [] for none."""


# ---------------------------------------------------------------------------------------------------------------------
# shared helpers (also used by api/world.py, api/dev.py)


def write_evidence(s: Session, evidence: Iterable[Evidence], t: datetime) -> None:
    """Fold evidence into knowledge rows (section 4). Live calls keep their own cache; this is the out-of-call path."""
    for knower, kind, item_id, ev in evidence:
        row = s.scalars(select(m.Knowledge).where(m.Knowledge.knower_id == knower, m.Knowledge.item_kind == kind,
                                                  m.Knowledge.item_id == item_id)).first()
        st = None if row is None else knowledge.State(
            row.p, row.half_life_days, row.first_at, row.last_at, row.last_day, row.n_heard, row.n_shown, row.n_said,
            row.n_confirmed, row.n_asked)
        try:
            new = knowledge.update(st, ev, t)
        except KeyError:
            log.error("unknown evidence %r for knower %s item %s:%s", ev, knower, kind, item_id)
            continue
        if row is None:
            row = m.Knowledge(knower_id=knower, item_kind=kind, item_id=item_id)
            s.add(row)
        for col in ("p", "half_life_days", "first_at", "last_at", "last_day", "n_heard", "n_shown", "n_said",
                    "n_confirmed", "n_asked"):
            setattr(row, col, getattr(new, col))
        s.flush()


def refresh_calls(space_id: int | None = None, person_id: int | None = None) -> int:
    """LiveWorld.refresh() on every active world call of the space, or with the person in it. Blocking: call it from
    a worker thread (sync route or asyncio.to_thread). Returns how many calls were refreshed."""
    from ..audio.pipeline import registry  # lazy: the pipeline pulls ASR/TTS
    n = 0
    for cs in registry.active():
        world = getattr(cs, "world", None)
        if world is None:
            continue
        if space_id is not None and cs.family_id != space_id:
            continue
        if person_id is not None and f"p{person_id}" not in list(cs.sides):  # D3: world identities are p<person_id>
            continue
        try:
            world.refresh()
            n += 1
        except Exception:  # noqa: BLE001  one broken call must not fail the write that triggered it
            log.exception("LiveWorld.refresh failed for call %s", cs.call_id)
    return n


# ---------------------------------------------------------------------------------------------------------------------
# ingest


@dataclass(frozen=True)
class _Ctx:
    """Everything the parse and the store need, read once from the DB (safe to hand to a background thread)."""
    space_id: int
    author: int
    lang: str
    system: str
    user: str
    people: AliasIndex  # people visible to the author, the author excluded
    vctx: object  # extract.ValidateCtx for a one-line window by the author


def _context(s: Session, person: m.Person, lang: str, body: str, now: datetime) -> _Ctx:
    view = WorldView.build(s, person.family_id, [person.id], now)
    visible = [pid for pid in view.people if pid != person.id and view.visible(person.id, "person", pid)]
    forms = [(f, "person", pid) for pid in visible for f in
             (view.people[pid].name, view.people[pid].lang_name, *(a for a, _l in view.people[pid].aliases)) if f]
    langs = list(dict.fromkeys([lang, "en", *(view.people[p].lang for p in visible if view.people[p].lang)]))
    own = own_context(s, person.id)
    lines = [f"AUTHOR: {person.display_name} ({lang})", "OWN STORYLINES (id | title | latest state)"]
    lines += [f"{i} | {title} | {label}" for i, title, label in own.storylines] or ["(none)"]
    lines += ["LANGUAGES: " + ", ".join(langs), "", "MESSAGE:", body]
    window = [Line(0, person.id, lang, "")]
    vctx = validate_ctx(window, [Participant(person.id, person.slug, person.display_name, lang)], {person.id: own}, {})
    return _Ctx(person.family_id, person.id, lang, SYSTEM, "\n".join(lines), AliasIndex(forms), vctx)


def _parse(ctx: _Ctx) -> SmsOut:
    return get_llm().structured(SmsOut, ctx.system, ctx.user, reasoning_effort="minimal", max_completion_tokens=2000,
                                prompt_cache_key="kin-sms")


def _resolve_told(ctx: _Ctx, name: str) -> int | None:
    """One exact person hit over the author's visible people, else None (never guess between two)."""
    name = name.strip()
    # Whole-name hits only: "Priya's mom" or "Priya Sharma" must not resolve to Priya.
    ids = {i for h in ctx.people.scan(name, ctx.lang) if h.exact and h.start == 0 and h.end == len(name) for i in h.ids}
    if len(ids) != 1:
        log.info("sms told name %r resolved to %d people; skipped", name, len(ids))
        return None
    return ids.pop()


def _about_other(ctx: _Ctx, f: SmsFact) -> bool:
    """A fact whose text opens with someone else's name ("Priya got the internship") is not the author's news. Exact,
    capitalized hits only: the prompt writes text_en without the author's name, so "will start a job" is not Will."""
    return f.text_en[:1].isupper() and any(h.start == 0 and h.exact for h in ctx.people.scan(f.text_en, "en"))


def _store(s: Session, ctx: _Ctx, msg: m.Message, out: SmsOut, now: datetime) -> list[dict]:
    """Validate and write the parsed facts; clear the body. Returns [{id, text}]."""
    facts: list[dict] = []
    evidence: list[Evidence] = []
    apply_ctx = ApplyCtx(ctx.space_id, None, msg.id, {0: ctx.author}, {0: []}, {}, now, source_kind="message",
                         shareable=False)
    for sf in out.facts:
        if sf.predicate not in PREDICATES or not sf.text_en.strip() or _about_other(ctx, sf):
            log.warning("sms fact dropped (predicate %r or not about the author): %r", sf.predicate, sf.text_en[:60])
            continue
        fo = FactOut(subject="speaker", predicate=sf.predicate, text_en=sf.text_en.strip(), text_src="", keys=sf.keys,
                     refs=[], lines=[0], sensitive_kind=sf.sensitive_kind, same_as=None, contradicts=None,
                     storyline=sf.storyline)
        clean, _dropped = validate(WorldUpdateOut(entities=[], ties=[], facts=[fo]), ctx.vctx)
        if not clean.facts:
            continue
        res = apply_update(s, clean, apply_ctx)
        evidence += res.evidence
        told = {t for t in (_resolve_told(ctx, n) for n in sf.told) if t is not None and t != ctx.author}
        for fid in res.facts:
            for pid in sorted(told):
                s.add(m.FactAudience(fact_id=fid, person_id=pid, via="told", at=now))
                evidence.append((pid, "fact", fid, "heard"))
            f = s.get(m.Fact, fid)
            facts.append({"id": fid, "text": f.text})
    s.flush()
    write_evidence(s, evidence, now)
    msg.body, msg.status, msg.fact_ids = "", "parsed", [f["id"] for f in facts]
    return facts


def _ack(out: SmsOut) -> str:
    return (out.ack.strip() or FALLBACK)[:ACK_MAX]


def ingest(s: Session, user: m.User, body: str, sid: str | None = None,
           budget_s: float = BUDGET_S) -> tuple[str, int, list[dict]]:
    """Save the Message, parse it within budget_s, write the facts. Returns (reply, message_id, [{id, text}]).
    Commits (the Message must exist before a background finisher reads it). On a slow or failed parse the reply is
    "Got it." and the parse finishes in the background with one retry. Raises IntegrityError on a duplicate sid."""
    person = s.get(m.Person, user.person_id)
    now = clock.now()
    body = body[:MAX_BODY]
    msg = m.Message(family_id=person.family_id, author_id=person.id, body=body, from_number=user.phone or "",
                    provider_sid=sid, received_at=now)
    s.add(msg)
    s.commit()
    ctx = _context(s, person, user.lang, body, now)
    fut = _PARSE.submit(_parse, ctx)
    try:
        out = fut.result(timeout=budget_s)
    except FuturesTimeout:
        log.warning("sms parse for message %s over %.1f s; replying %r and finishing in the background", msg.id,
                    budget_s, FALLBACK)
        return _defer(s, msg, ctx, fut, now)
    except Exception as e:  # noqa: BLE001  StructuredOutputError, openai.APIError, ...: logged, retried once
        log.error("sms parse for message %s failed: %s: %s", msg.id, type(e).__name__, e)
        return _defer(s, msg, ctx, None, now)
    reply = _ack(out)
    try:
        msg.reply = reply
        facts = _store(s, ctx, msg, out, now)
        s.commit()
    except Exception:  # noqa: BLE001  a store bug must not leave the raw body behind (section 7)
        log.exception("sms store for message %s failed; retrying in the background", msg.id)
        s.rollback()
        return _defer(s, s.get(m.Message, msg.id), ctx, None, now)
    refresh_calls(person_id=person.id)
    return reply, msg.id, facts


def _defer(s: Session, msg: m.Message, ctx: _Ctx, fut, now: datetime) -> tuple[str, int, list[dict]]:
    msg.reply = FALLBACK
    s.commit()
    _FINISH.submit(_finish_later, msg.id, ctx, fut, now)
    return FALLBACK, msg.id, []


def _finish_later(msg_id: int, ctx: _Ctx, fut, now: datetime) -> None:
    """Wait for the in-flight parse (if any); on failure retry once; then store, or mark the message failed."""
    out = None
    for attempt in ((lambda: fut.result()) if fut is not None else None, lambda: _parse(ctx)):
        if attempt is None:
            continue
        try:
            out = attempt()
            break
        except Exception as e:  # noqa: BLE001
            log.error("sms background parse for message %s failed: %s: %s", msg_id, type(e).__name__, e)
    if out is not None:
        try:
            with session_scope() as s:
                msg = s.get(m.Message, msg_id)
                if msg is None:  # the author deleted their account meanwhile
                    return
                _store(s, ctx, msg, out, now)
            refresh_calls(person_id=ctx.author)
            return
        except Exception:  # noqa: BLE001  background thread: nothing above us would log it
            log.exception("sms background store for message %s failed", msg_id)
    _fail(msg_id, "parse failed after one retry" if out is None else "store failed")


def _fail(msg_id: int, error: str) -> None:
    """Mark the message failed and drop the raw text: nothing will parse it again, so it must not linger (section 7)."""
    try:
        with session_scope() as s:
            msg = s.get(m.Message, msg_id)
            if msg is not None:
                msg.status, msg.error, msg.body = "failed", error, ""
    except Exception:  # noqa: BLE001
        log.exception("could not mark sms message %s failed", msg_id)
