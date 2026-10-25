"""LiveWorld: the one object the call pipeline talks to (docs/ARCHITECTURE.md 8.5).

Partials stay in memory (D6): scan, stability gate, per-listener gaps, delivery guard. Finals confirm or retract
partial cards and write evidence into the knowledge cache; DB writes (knowledge flush, card_log, told rows) and
extraction run on `_WORLD_POOL`. Results that touch live state come back to the event loop via call_soon_threadsafe.
Card selection itself lives in world/cards.py.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import functools
import dataclasses
import hashlib
import json
import logging
import re
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Awaitable, Callable

import openai
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy import update as sql_update
from sqlalchemy.exc import SQLAlchemyError

from ..cards.lexicon import load_lexicon
from ..cards.matcher import Match, Matcher
from ..db import models as m
from ..db.session import session_scope
from ..graph.kin_tables import MUSE_LANGUAGES, load_table
from ..llm import StructuredOutputError, get_llm
from . import cards as C
from . import clock
from . import knowledge as kn
from .apply import ApplyCtx, ApplyResult, apply_update
from .contracts import LocalizeOut, NewPerson, SuggestionOut, WorldUpdateOut
from .extract import (ENTITY_TABLE, Candidate, Line, Participant, own_context, run_extraction, validate,
                      validate_ctx)
from .match import AliasIndex, Hit, fold, script_of
from .view import TIE_LABEL, WorldView

if TYPE_CHECKING:
    from ..mt.translate import Translator

log = logging.getLogger("kin.world.live")

Sends = dict[str, list[dict]]  # identity -> server->client messages

_POOL_PREFIX = "kin-world"
_WORLD_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix=_POOL_PREFIX)
# localization gets its own worker so a burst of misses never queues ahead of extraction, flushes or refresh()
_L10N_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kin-l10n")
AMBIGUITY_MARGIN = 1.0  # 3.4: top-two candidate scores closer than this = ambiguous
RECENT_LINES = 6
EXTRACT_EVERY = 4
EXTRACT_IDLE_S = 30.0
EXTRACT_OVERLAP = 3
LOCALIZE_TOP = 30
KEYTERMS_CAP = 100
LOG_WINDOW = C.BRIDGE_REPEAT
_LLM_ERRORS = (StructuredOutputError, openai.APIError, TimeoutError)
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

# 3.5, English only. Possessive word -> tie kind.
REL_KIND = {"friend": "friend", "roommate": "roommate", "boss": "coworker", "coworker": "coworker",
            "girlfriend": "partner", "boyfriend": "partner", "partner": "partner", "classmate": "classmate",
            "teammate": "teammate"}
_REL_RE = re.compile(r"\b(my|your|her|his|their)\s+(" + "|".join(REL_KIND) + r")\b", re.IGNORECASE)
_THE_RE = re.compile(r"\b(that|the)\s+([^\W\d_]+)", re.IGNORECASE)

LOCALIZE_SYSTEM = ("You localize short context cards shown during a live call. Translate each body into natural {lang} "
                   "({lang} script), as short as the English, keeping people's names as written. Return every key "
                   "unchanged with its translated body. Return JSON for the schema.")


@dataclass(frozen=True)
class FinalResult:
    sends: Sends
    spans: list[dict]


@dataclass(frozen=True)
class _Snap:
    """View plus its indexes, swapped as one object so readers never see a mixed pair."""
    view: WorldView
    index: AliasIndex  # entities (view.index_forms)
    kw: AliasIndex     # concept groups of facts and storylines, plus storyline titles
    by_slug: dict[str, tuple[str, int]]


@dataclass(frozen=True)
class _Pending:
    speaker: str
    card: C.Card


@dataclass(frozen=True)
class _Line:
    speaker: int
    lang: str
    text: str
    utterance_id: int | None
    audience: tuple[int, ...]


def _build(space_id: int, members: frozenset[int], now: datetime) -> _Snap:
    with session_scope() as s:
        v = WorldView.build(s, space_id, members, now)
    kw = v.fact_forms() + [(st.title, "storyline", st.id) for st in v.storylines.values() if st.title]
    slugs = {p.slug: ("person", p.id) for p in v.people.values()}
    slugs.update({t.slug: ("thing", t.id) for t in v.things.values()})
    slugs.update({g.slug: ("group", g.id) for g in v.groups.values()})
    return _Snap(v, AliasIndex(v.index_forms()), AliasIndex(kw), slugs)


def _sha(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()


def _latin(form: str) -> bool:
    letters = [c for c in form if c.isalpha()]
    return bool(letters) and all(script_of(c) == "latin" for c in letters)


def _on_pool() -> bool:
    return threading.current_thread().name.startswith(_POOL_PREFIX)


def _locked(fn: Callable) -> Callable:
    """The pipeline calls LiveWorld from the loop thread and from to_thread workers; every read-modify-write of live
    state (sent, pending, kcache, ...) runs under one lock. ponytail: one RLock per call, held ~1 ms in memory."""
    @functools.wraps(fn)
    def wrapper(self: "LiveWorld", *args, **kw):
        with self._state:
            return fn(self, *args, **kw)
    return wrapper


class LiveWorld:
    def __init__(self, call_id: int, space_id: int, emit: Callable[[str, dict], Awaitable[None]],
                 loop: asyncio.AbstractEventLoop) -> None:
        self.call_id = call_id
        self.space_id = space_id
        self.emit = emit
        self.loop = loop
        self.guard_drops = 0
        self.parts: dict[str, tuple[int, str]] = {}  # identity -> (person id, lang)
        self._ever: dict[str, tuple[int, str]] = {}  # everyone who joined: the call-end extraction needs them (6.1)
        self._state = threading.RLock()
        self._snap: _Snap | None = None
        self.kcache: dict[tuple[int, str, int], kn.State] = {}
        self._dirty: frozenset[tuple[int, str, int]] = frozenset()
        self.sent: frozenset[tuple[str, str]] = frozenset()
        self.pending: dict[tuple[str, str], _Pending] = {}
        self.delivered: dict[tuple[str, str], C.Card] = {}
        self.last_hits: dict[str, frozenset] = {}
        self.recent: list[tuple[int, list[Hit]]] = []  # last 6 finals: (speaker id, resolved hits)
        self._final_hits: dict[str, list[Hit]] = {}
        self._log_rows: tuple[C.LogRow, ...] = ()
        self._lines: list[_Line] = []
        self._extracted = 0  # index of the first line not yet sent to extraction
        self._extracting = False
        self._lock = threading.Lock()  # guards the extraction cursor only (pool threads and close)
        self._idle: asyncio.TimerHandle | None = None
        self._matchers: dict[str, Matcher] = {}
        self._translators: dict[str, "Translator"] = {}
        self._l10n: dict[tuple[str, str, str], str] = {}
        self._l10n_inflight: frozenset[tuple[str, str, str]] = frozenset()
        self._span_speaker: dict[str, int] = {}  # node slug -> speaker of the latest final that mentioned it (D9)
        self._told_aud: dict[int, frozenset[int]] = {}  # 5.6 told rows not yet in a rebuilt view
        self._jobs: set[concurrent.futures.Future] = set()
        self._tasks: set[asyncio.Task] = set()

    # ---- plumbing ---------------------------------------------------------------------------------------------------
    @property
    def view(self) -> WorldView | None:
        return self._snap.view if self._snap else None

    def _members(self) -> frozenset[int]:
        return frozenset(p for p, _l in self.parts.values())

    def _listeners(self, speaker: str) -> list[tuple[str, int, str]]:
        return [(i, p, lang) for i, (p, lang) in self.parts.items() if i != speaker]

    def _identity(self, pid: int) -> str | None:
        return next((i for i, (p, _l) in self.parts.items() if p == pid), None)

    def _submit(self, fn: Callable, *args) -> concurrent.futures.Future:
        fut = _WORLD_POOL.submit(fn, *args)
        self._jobs.add(fut)
        fut.add_done_callback(self._job_done)
        return fut

    def _job_done(self, fut: concurrent.futures.Future) -> None:
        self._jobs.discard(fut)
        if not fut.cancelled() and fut.exception() is not None:
            log.error("world job failed for call %s", self.call_id, exc_info=fut.exception())

    def _on_loop(self, fn: Callable, *args) -> None:
        try:
            self.loop.call_soon_threadsafe(fn, *args)
        except RuntimeError as e:  # loop closed: the call is over, live state no longer matters
            log.info("call %s: loop gone, dropped %s: %s", self.call_id, getattr(fn, "__name__", fn), e)

    def _send_later(self, identity: str, msg: dict) -> None:
        """emit from any thread; on the loop thread this schedules a task, elsewhere it hops onto the loop."""
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self.loop:
            task = self.loop.create_task(self.emit(identity, msg))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            return
        try:
            asyncio.run_coroutine_threadsafe(self.emit(identity, msg), self.loop)
        except RuntimeError as e:
            log.info("call %s: loop gone, late message for %s dropped: %s", self.call_id, identity, e)

    @_locked
    def _swap(self, snap: _Snap) -> None:
        """Swap in a rebuilt view, keeping told rows (5.6) whose async write the rebuild may have missed."""
        aud = snap.view.audience
        pend = {f: o for f, o in self._told_aud.items() if not o <= aud.get(f, frozenset())}
        if pend:
            aud = {**aud, **{f: aud.get(f, frozenset()) | o for f, o in pend.items()}}
            snap = replace(snap, view=replace(snap.view, audience=aud))
        self._told_aud = pend
        self._snap = snap
        self._translators = {}

    def _rebuild(self) -> _Snap:
        return _build(self.space_id, self._members(), clock.now())

    def _rebuild_swap(self) -> None:
        self._swap(self._rebuild())

    # ---- lifecycle --------------------------------------------------------------------------------------------------
    def join(self, identity: str, person_id: int, lang: str) -> None:
        """Blocking: rebuild the view, load this person's knowledge and recent bridge log, schedule localization."""
        with self._state:
            self.parts = {**self.parts, identity: (person_id, lang)}
            self._ever = {**self._ever, identity: (person_id, lang)}
        now = clock.now()
        try:
            snap = _build(self.space_id, self._members(), now)  # DB work outside the lock
            loaded = self._load(person_id, now)
        except SQLAlchemyError:
            log.exception("world join failed for call %s (%s); cards off until the next refresh", self.call_id,
                          identity)
            return
        with self._state:
            self._swap(snap)
            states, log_rows = loaded
            self.kcache = {**states, **self.kcache}  # the live cache wins over rows it has already moved past
            self._log_rows = self._log_rows + tuple(r for r in log_rows if r not in self._log_rows)
        if lang != "en":
            self._submit_l10n(self._prewarm, person_id, lang)

    def _load(self, pid: int, now: datetime) -> tuple[dict, tuple[C.LogRow, ...]]:
        with session_scope() as s:
            rows = s.scalars(select(m.Knowledge).where(m.Knowledge.knower_id == pid)).all()
            logs = s.scalars(select(m.CardLog).where(m.CardLog.listener_id == pid,
                                                     m.CardLog.kind.in_(("bridge", "told")),
                                                     m.CardLog.at >= now - LOG_WINDOW)).all()
            states = {(r.knower_id, r.item_kind, r.item_id): kn.State(
                r.p, r.half_life_days, r.first_at, r.last_at, r.last_day, r.n_heard, r.n_shown, r.n_said,
                r.n_confirmed, r.n_asked) for r in rows}
            log_rows = tuple(C.LogRow(r.call_id, r.listener_id, r.target_id, r.kind, r.key, r.at) for r in logs)
        return states, log_rows

    @_locked
    def leave(self, identity: str) -> None:
        if identity not in self.parts:
            return
        self.parts = {k: v for k, v in self.parts.items() if k != identity}
        self.pending = {k: p for k, p in self.pending.items() if identity not in (k[0], p.speaker)}
        self.last_hits.pop(identity, None)
        if self.parts:
            self._submit(self._rebuild_swap)

    def refresh(self) -> None:
        """Rebuild the view on the world pool and swap it; kcache is kept. Blocking (call from a worker thread)."""
        if not self.parts:
            return
        self._swap(self._rebuild() if _on_pool() else _WORLD_POOL.submit(self._rebuild).result())

    def close(self) -> None:
        """Final extraction and knowledge flush. Blocking; waits for queued world jobs first."""
        if self._idle is not None:
            self._on_loop(self._idle.cancel)
        concurrent.futures.wait(list(self._jobs))
        with self._lock:
            start, end = self._extracted, len(self._lines)
            self._extracted = end
        # ponytail: an extraction still running on the pool may finish after this; its rows are written anyway.
        if end > start and self._snap is not None:
            res = self._extract(start, end)
            if res is not None:
                with self._state:
                    self._evidence(res[0].evidence, clock.now())
        with self._state:
            dirty = self._take_dirty()
        self._upsert(dirty)

    # ---- matching ---------------------------------------------------------------------------------------------------
    def _matcher(self, lang: str) -> Matcher:
        if lang not in self._matchers:
            entries = [dataclasses.replace(e, key=f"lex:{lang}:{e.key}") for e in load_lexicon(lang).entries]
            try:
                t = load_table(lang)
                suf, strip = (*t.suffixes, *t.roman_suffixes), tuple(t.final_strip)
            except (KeyError, FileNotFoundError, ValueError) as e:
                log.info("no kin table suffixes for %s: %s", lang, e)
                suf, strip = (), ()
            self._matchers = {**self._matchers, lang: Matcher(entries, suffixes=suf, final_strip=strip)}
        return self._matchers[lang]

    def _score(self, v: WorldView, speaker: int, kind: str, id_: int, exact: bool) -> float:
        sc = 0.0
        if v.structural_known(speaker, kind, id_) or (kind == "person" and speaker in v.kin.people
                                                       and id_ in v.kin.people and v.kin.distance(speaker, id_) <= 2):
            sc += 3
        for back, (_sp, hs) in enumerate(reversed(self.recent)):
            if any(h.kind == kind and id_ in h.ids for h in hs):
                sc += 2 / (back + 1)
                break
        if any(v.visible(p, kind, id_) for p in self._members()):
            sc += 1
        return sc + (0.5 if exact else 0.0)

    def _rank(self, v: WorldView, hits: list[Hit], speaker: int) -> tuple[list[Hit], list[Hit]]:
        """(resolved hits with one id, ambiguous hits with ids best first). Exact and skeleton hits on one span merge."""
        spans: dict[tuple[int, int, str], tuple[Hit, dict[int, bool]]] = {}
        for h in hits:
            base, ids = spans.get((h.start, h.end, h.kind), (h, {}))
            spans[(h.start, h.end, h.kind)] = (base, {**ids, **{i: ids.get(i, False) or h.exact for i in h.ids}})
        resolved, ambiguous = [], []
        for base, ids in spans.values():
            if len(ids) == 1:
                (i, ex), = ids.items()
                resolved.append(replace(base, ids=(i,), exact=ex))
                continue
            scored = sorted(((self._score(v, speaker, base.kind, i, ex), i) for i, ex in ids.items()), reverse=True)
            if scored[0][0] - scored[1][0] < AMBIGUITY_MARGIN:
                ambiguous.append(replace(base, ids=tuple(i for _s, i in scored)))
            else:
                resolved.append(replace(base, ids=(scored[0][1],), exact=ids[scored[0][1]]))
        return resolved, ambiguous

    def _scan(self, snap: _Snap, speaker: str, text: str) -> tuple[list[Hit], list[Hit], list[Match]]:
        pid, lang = self.parts[speaker]
        resolved, ambiguous = self._rank(snap.view, snap.index.scan(text, lang), pid)
        cross = any(lg != lang for _i, _p, lg in self._listeners(speaker))
        return resolved, ambiguous, (self._matcher(lang).match(text) if cross else [])

    def _relational(self, snap: _Snap, speaker: str, text: str, taken: list[Hit]) -> list[Hit]:
        """3.5: "my/your/her roommate" with exactly one such tie, "that/the <head>" on a participant's thing."""
        pid, lang = self.parts[speaker]
        if lang != "en":
            return []
        v = snap.view
        spans = [(h.start, h.end) for h in taken]
        free = lambda a, b: not any(a < e and s < b for s, e in spans)  # noqa: E731
        listeners = self._listeners(speaker)
        everyone = [pid] + [L for _i, L, _l in listeners]
        # a reference resolves only through ties the speaker and every listener may see (the visibility rule)
        hop_ok = lambda owner, h: all(v._hop_ok(p, pid, owner, h, frozenset()) for p in everyone)  # noqa: E731
        out: list[Hit] = []
        for mt in _REL_RE.finditer(text):
            det, word = mt.group(1).lower(), mt.group(2).lower()
            if det == "my":
                owner = pid
            elif det == "your":
                owner = listeners[0][1] if len(listeners) == 1 else None
            else:
                owner = self._last_person(taken, mt.start(), exclude=pid)
            kind = REL_KIND[word]
            label = TIE_LABEL.get(kind, kind)
            targets = {h.to for h in v.adj.get(owner, ()) if h.kind == "tie" and h.label == label and hop_ok(owner, h)}
            if owner is not None and len(targets) == 1 and free(mt.start(), mt.end()):
                out.append(Hit(mt.start(), mt.end(), mt.group(0), "person", (targets.pop(),), word, True))
        members = self._members()
        owned = sorted((t for t in v.things.values() if t.owner_id in members
                        and all(v.visible(p, "thing", t.id, pid) for p in everyone)), key=lambda t: -t.id)
        for mt in _THE_RE.finditer(text):
            head = fold(mt.group(2))[0]
            t = next((t for t in owned if head in {fold(x)[0].strip() for x in (t.name, *(f for g in t.keys for f in g))}),
                     None)
            if t is not None and free(mt.start(), mt.end()):
                out.append(Hit(mt.start(), mt.end(), mt.group(0), "thing", (t.id,), head, True))
        return out

    def _last_person(self, taken: list[Hit], before: int, exclude: int) -> int | None:
        here = [h.ids[0] for h in sorted(taken, key=lambda h: -h.start) if h.kind == "person" and h.end <= before]
        older = [h.ids[0] for _sp, hs in reversed(self.recent) for h in reversed(hs) if h.kind == "person"]
        return next((i for i in here + older if i != exclude), None)

    def _unsent(self, v: WorldView, identity: str, hits: list[Hit]) -> list[Hit]:
        return [h for h in hits if len(h.ids) > 1 or (identity, C.entity_key(v, h.kind, h.ids[0])) not in self.sent]

    # ---- delivery ---------------------------------------------------------------------------------------------------
    def _admit(self, v: WorldView, identity: str, listener: int, speaker: int, cards: list[C.Card],
               mentioned: frozenset[int], now: datetime) -> list[C.Card]:
        """Dedupe per (identity, key) (D7) and run the delivery guard (D13) on every card."""
        out = []
        for c in cards:
            k = (identity, c.key)
            if k in self.sent:
                continue
            if not C.deliver_ok(v, c, listener, speaker, mentioned, now):
                self.guard_drops += 1
                continue
            self.sent = self.sent | {k}
            self.delivered = {**self.delivered, k: c}
            out.append(c)
        return out

    def _glance(self, speaker: str, identity: str, lang: str, cards: list[C.Card], partial: bool) -> dict:
        return {"type": "glance", "speaker": speaker, "role": "participant", "partial": partial,
                "items": [self._payload(identity, lang, c, partial) for c in cards]}

    def _payload(self, identity: str, lang: str, card: C.Card, partial: bool) -> dict:
        """Cached localization or English. A miss schedules a lazy localization only for a final card: partials make
        no LLM calls (D6); a confirmed partial card is localized from on_final."""
        p = card.payload
        if lang == "en" or not p.get("body"):
            return p
        hit = self._l10n.get((card.key, lang, _sha(p["body"])))
        if hit:
            return {**p, "body": hit}
        if not partial:
            self._lazy(identity, lang, card)
        return p

    def _lazy(self, identity: str, lang: str, card: C.Card) -> None:
        body = card.payload.get("body")
        k = (card.key, lang, _sha(body)) if body and lang != "en" else None
        if k is None or k in self._l10n or k in self._l10n_inflight:
            return
        self._l10n_inflight = self._l10n_inflight | {k}
        self._submit_l10n(self._lazy_l10n, identity, lang, card.key, body)  # English now, glance_update later

    def _submit_l10n(self, fn: Callable, *args) -> None:
        fut = _L10N_POOL.submit(fn, *args)
        self._jobs.add(fut)
        fut.add_done_callback(self._job_done)

    def _card_evidence(self, listener: int, c: C.Card) -> list[tuple[int, str, int, str]]:
        kind = c.item.get("kind")
        if kind in C.ENTITY_KINDS:
            return [(listener, kind, c.item["id"], "shown")]
        if kind == "storyline":
            return [(listener, "state", c.item["state"], "shown")]
        return []

    def _evidence(self, evidence, now: datetime) -> None:
        cache = dict(self.kcache)
        for knower, kind, item_id, ev in evidence:
            try:
                cache[(knower, kind, item_id)] = kn.update(cache.get((knower, kind, item_id)), ev, now)
            except KeyError:
                log.error("unknown evidence %r for %s %s:%s", ev, knower, kind, item_id)
                continue
            self._dirty = self._dirty | {(knower, kind, item_id)}
        self.kcache = cache

    def _log(self, rows: list[tuple[int, int | None, C.Card]], now: datetime, final: bool = True) -> None:
        if not rows:
            return
        self._log_rows = self._log_rows + tuple(C.LogRow(self.call_id, L, t, c.kind, c.key, now) for L, t, c in rows)
        self._submit(self._write_log, [(L, t, c.kind, c.key, list(c.fact_ids)) for L, t, c in rows], now, final)

    def _write_log(self, rows: list, now: datetime, final: bool) -> None:
        with session_scope() as s:
            s.add_all([m.CardLog(call_id=self.call_id, listener_id=L, target_id=t, kind=kind[:10], key=key[:80],
                                 fact_ids=fids, at=now, final=final) for L, t, kind, key, fids in rows])

    # ---- live path --------------------------------------------------------------------------------------------------
    @_locked
    def on_partial(self, speaker: str, text: str) -> Sends:
        snap = self._snap
        if snap is None or speaker not in self.parts or not text.strip():
            return {}
        v, S, now = snap.view, self.parts[speaker][0], clock.now()
        resolved, _amb, lex = self._scan(snap, speaker, text)
        prev = self.last_hits.get(speaker, frozenset())
        self.last_hits[speaker] = frozenset((h.start, h.ids[0]) for h in resolved) | frozenset(
            (mt.start, mt.entry.key) for mt in lex)
        stable = [h for h in resolved if (h.start, h.ids[0]) in prev]
        slex = [mt for mt in lex if (mt.start, mt.entry.key) in prev]
        if not stable and not slex:
            return {}
        mentioned = frozenset(h.ids[0] for h in resolved if h.kind == "person")
        sends: Sends = {}
        for ident, L, lang in self._listeners(speaker):
            found = C.gaps(v, self.kcache, L, S, self._unsent(v, ident, stable),
                           [mt for mt in slex if (ident, mt.entry.key) not in self.sent], now)
            cards = self._admit(v, ident, L, S, found, mentioned, now)
            if cards:
                self.pending = {**self.pending, **{(ident, c.key): _Pending(speaker, c) for c in cards}}
                sends[ident] = [self._glance(speaker, ident, lang, cards, True)]
        return sends

    @_locked
    def on_final(self, speaker: str, text: str) -> FinalResult:
        snap = self._snap
        if snap is None or speaker not in self.parts or not text.strip():
            return FinalResult({}, [])
        v, (S, slang), now = snap.view, self.parts[speaker], clock.now()
        resolved, ambiguous, lex = self._scan(snap, speaker, text)
        relational = self._relational(snap, speaker, text, resolved + ambiguous)
        resolved = sorted(resolved + relational, key=lambda h: h.start)
        self.last_hits[speaker] = frozenset()
        seen = {(h.start, h.ids[0]) for h in resolved} | {(mt.start, mt.entry.key) for mt in lex}
        mentioned = frozenset(h.ids[0] for h in resolved if h.kind == "person")
        sends: Sends = defaultdict(list)
        confirmed: list[tuple[int, C.Card]] = []
        retract: dict[str, list[str]] = defaultdict(list)
        for k, p in self.pending.items():
            if p.speaker != speaker:
                continue
            ident = k[0]
            if (p.card.item.get("start"), p.card.item.get("id")) in seen and ident in self.parts:
                confirmed.append((self.parts[ident][0], p.card))
                self._lazy(ident, self.parts[ident][1], p.card)  # sent in English on the partial
            else:
                retract[ident].append(p.card.key)
                self.sent = self.sent - {k}  # a wrong partial must not poison dedupe (D6)
                self.delivered = {d: c for d, c in self.delivered.items() if d != k}
        self.pending = {k: p for k, p in self.pending.items() if p.speaker != speaker}
        for ident, keys in retract.items():
            sends[ident].append({"type": "glance_retract", "keys": keys})
        for ident, L, lang in self._listeners(speaker):
            found = C.gaps(v, self.kcache, L, S, self._unsent(v, ident, resolved) + ambiguous,
                           [mt for mt in lex if (ident, mt.entry.key) not in self.sent], now)
            cards = self._admit(v, ident, L, S, found, mentioned, now)
            confirmed += [(L, c) for c in cards]
            if cards:
                sends[ident].append(self._glance(speaker, ident, lang, cards, False))
        # Section 4 ordering: decisions above read the state before this utterance; shown goes in before heard.
        self._evidence([e for L, c in confirmed for e in self._card_evidence(L, c)], now)
        self._log([(L, None, c) for L, c in confirmed], now)
        audience = [p for _i, p, _l in self._listeners(speaker)]
        mentions = [(h.kind, h.ids[0]) for h in resolved if h.kind in C.ENTITY_KINDS]
        self._evidence([(p, k, i, "heard") for k, i in mentions for p in audience]
                       + [(S, k, i, "said") for k, i in mentions], now)
        self.recent = (self.recent + [(S, resolved)])[-RECENT_LINES:]
        self._final_hits = {**self._final_hits, speaker: resolved}
        rel = {(h.start, h.ids[0]) for h in relational}
        spans = [self._span(v, h, S, audience, "relational" if (h.start, h.ids[0]) in rel else "alias")
                 for h in resolved]
        self._span_speaker = {**self._span_speaker, **{sp["node_id"]: S for sp in spans if sp and sp["node_id"]}}
        return FinalResult(dict(sends), [s for s in spans if s is not None])

    def _span(self, v: WorldView, h: Hit, speaker: int, audience: list[int], method: str) -> dict | None:
        """Linker-style span dict for Translator extra_spans; rendered for the single listener when visible."""
        ent = C._entity(v, h.kind, h.ids[0])
        if ent is None:
            return None
        if method == "relational" and not all(v.visible(L, h.kind, ent.id, speaker) for L in audience):
            # the reference resolved, but naming the entity would tell a listener something they cannot see
            return {"start": h.start, "end": h.end, "source": h.surface, "node_id": None, "type": h.kind,
                    "confidence": 0.85, "rendered": h.surface, "candidates": [], "method": method}
        rendered = ent.name
        if h.kind == "person" and len(audience) == 1 and v.visible(audience[0], "person", ent.id, speaker):
            rendered = v.render(audience[0], ent.id, speaker)
        typ = {"person": "person", "group": "group"}.get(h.kind) or ent.kind
        return {"start": h.start, "end": h.end, "source": h.surface, "node_id": ent.slug, "type": typ,
                "confidence": 0.95 if h.exact else 0.85, "rendered": rendered, "candidates": [], "method": method}

    @_locked
    def on_translated(self, speaker: str, utterance_id: int, text: str, translations: dict[str, str],
                      audience: list[int]) -> Sends:
        snap = self._snap
        if snap is None or speaker not in self.parts:
            return {}
        v, (S, slang), now = snap.view, self.parts[speaker], clock.now()
        self._lines = self._lines + [_Line(S, slang, text, utterance_id, tuple(audience))]
        hits = self._final_hits.get(speaker, [])
        mentioned = frozenset(h.ids[0] for h in hits if h.kind == "person")
        kw_hits = snap.kw.scan(text, slang) + [h for lg, tr in translations.items() if tr for h in snap.kw.scan(tr, lg)]
        logv = C.CardLogView(self.call_id, self._log_rows)
        sends: Sends = {}
        shown: list[tuple[int, int | None, C.Card]] = []
        for ident, L, lang in self._listeners(speaker):
            cross = lang != slang and translations.get(lang)
            texts, langs = [text] + ([translations[lang]] if cross else []), [slang] + ([lang] if cross else [])
            found = (C.bridges(v, self.kcache, L, S, texts, hits, now, logv, langs)
                     + C.storylines(v, self.kcache, L, S, kw_hits, hits, now))
            cards = self._admit(v, ident, L, S, found, mentioned, now)
            shown += [(L, S if c.kind == "bridge" else None, c) for c in cards]
            if cards:
                sends[ident] = [self._glance(speaker, ident, lang, cards, False)]
        self._evidence([e for L, _t, c in shown for e in self._card_evidence(L, c)], now)
        self._log(shown, now)
        self._told(snap, S, slang, text, hits, audience, now)
        self._flush_async()
        if len(self._lines) - self._extracted >= EXTRACT_EVERY:
            self._extract_async()
        else:
            self._on_loop(self._arm_idle)
        return sends

    def _told(self, snap: _Snap, S: int, slang: str, text: str, hits: list[Hit], audience: list[int],
              now: datetime) -> None:
        """5.6 fast path: the speaker's own words hit one of their bridge facts, so the line's audience has heard it.
        A FactAudience row also makes the fact visible, so a keyword false positive must not expose a non-shareable
        (SMS) fact: those get a card_log "told" row instead, which only blocks the bridge (7 days)."""
        v = snap.view
        rows = [(f, O) for O in set(audience) - {S}
                for f in C.relevant(C.bridge_candidates(v, S, O, now), [text], hits, [slang])]
        shared = [(f.id, O) for f, O in rows if f.shareable]
        quiet = [(S, O, C.Card(f"bridge:{f.id}", "told", {"kind": "fact", "id": f.id}, (f.id,), {}))
                 for f, O in rows if not f.shareable]
        self._log(quiet, now, final=False)
        if not shared:
            return
        add: dict[int, frozenset[int]] = {}
        for fid, O in shared:
            add[fid] = add.get(fid, frozenset()) | {O}
        self._told_aud = {**self._told_aud, **{f: self._told_aud.get(f, frozenset()) | o for f, o in add.items()}}
        if self._snap is snap:
            aud = {**v.audience, **{f: v.audience.get(f, frozenset()) | o for f, o in add.items()}}
            self._snap = replace(snap, view=replace(v, audience=aud))
        self._submit(self._write_told, shared, now)

    def _write_told(self, rows: list[tuple[int, int]], now: datetime) -> None:
        with session_scope() as s:
            for fid, pid in rows:
                have = s.scalar(select(m.FactAudience.id).where(m.FactAudience.fact_id == fid,
                                                                m.FactAudience.person_id == pid))
                if have is None:
                    s.add(m.FactAudience(fact_id=fid, person_id=pid, via="told", at=now, call_id=self.call_id))

    @_locked
    def asks(self, speaker: str, listeners: list[str], new_people: list) -> Sends:
        """CardsOut.new_people -> "Who is X?" cards (2.5 trigger 2). Names already in the alias index are dropped; a
        known name asked about ("question") is `asked` evidence for the speaker."""
        snap = self._snap
        if snap is None or speaker not in self.parts:
            return {}
        v, S, now = snap.view, self.parts[speaker][0], clock.now()
        sends: Sends = defaultdict(list)
        for raw in new_people:
            try:
                np = raw if isinstance(raw, NewPerson) else NewPerson.model_validate(raw)
            except ValidationError as e:
                log.warning("bad new_people item %r: %s", raw, e)
                continue
            name = (np.name or np.source).strip()
            known = [h for h in snap.index.scan(name) + snap.index.scan(np.source) if h.kind == "person"]
            if known:
                if np.relation == "question":
                    self._evidence([(S, "person", h.ids[0], "asked") for h in known if len(h.ids) == 1], now)
                continue
            if not name:
                continue
            rel = np.relation if np.relation and np.relation != "question" else "friend"
            for ident in listeners:
                if ident == speaker or ident not in self.parts:
                    continue
                L, lang = self.parts[ident]
                owner = {"speaker": S, "listener": L}.get(np.owner)
                owner_slug = v.people[owner].slug if owner in v.people else ""
                owner_name = v.people[owner].name if owner in v.people else np.owner_name
                label = f"{owner_name}'s {rel}" if owner_name else rel
                sugg = [SuggestionOut(owner=owner_slug, relation=rel, label=label)] if owner_slug else []
                card = C.ask(np.source or name, name, np.context or f"{v.people[S].name} mentioned {name}", sugg)
                cards = self._admit(v, ident, L, S, [card], frozenset(), now)
                if cards:
                    sends[ident].append(self._glance(speaker, ident, lang, cards, False))
        return dict(sends)

    @_locked
    def feedback(self, listener: str, key: str, action: str) -> None:
        """know -> confirmed evidence; remember -> remembered on the cited facts; dismiss -> nothing."""
        if action not in ("know", "remember", "dismiss"):
            raise ValueError(f"unknown feedback action {action!r}")
        card = self.delivered.get((listener, key))
        if card is None or listener not in self.parts:
            log.info("feedback %s on %s from %s: no such delivered card", action, key, listener)
            return
        if action == "know":
            ev = [(L, k, i, "confirmed") for L, k, i, _e in self._card_evidence(self.parts[listener][0], card)]
            self._evidence(ev, clock.now())
        elif action == "remember" and card.fact_ids:
            self._submit(self._remember, list(card.fact_ids))

    def _remember(self, fact_ids: list[int]) -> None:
        with session_scope() as s:
            s.execute(sql_update(m.Fact).where(m.Fact.id.in_(fact_ids)).values(remembered=True))
        self._rebuild_swap()

    # ---- prompts and helpers for the pipeline -------------------------------------------------------------------------
    @_locked
    def render(self, listener: str, node_id: str) -> str | None:
        """Listener-relative rendering of a grounded span; None when that node is not visible to the listener."""
        snap = self._snap
        if snap is None or listener not in self.parts or node_id not in snap.by_slug:
            return None
        v, L = snap.view, self.parts[listener][0]
        kind, id_ = snap.by_slug[node_id]
        sp = self._span_speaker.get(node_id)
        if not v.visible(L, kind, id_, sp):
            return None
        return v.render(L, id_, sp) if kind == "person" else C._entity(v, kind, id_).name

    @_locked
    def roster(self, listeners: list[str], speaker: str) -> str:
        snap = self._snap
        pids = frozenset(self.parts[i][0] for i in listeners if i in self.parts)
        if snap is None or not pids or speaker not in self.parts:
            return ""
        recent = list(dict.fromkeys(h.ids[0] for _s, hs in reversed(self.recent) for h in hs if h.kind == "person"))
        return snap.view.roster(pids, self.parts[speaker][0], recent)

    @_locked
    def translator(self, lang: str) -> "Translator":
        """Translator over view.kin with the linker and kin table for `lang`, the SPEAKER's language (the pipeline
        passes side.lang; the target language goes to translate_speech). Cached per lang, reset on every view swap.
        Without a view (a failed join) it runs over an empty graph: translation keeps working, cards stay off."""
        from ..graph.kinship import FamilyGraph
        from ..mt.translate import Translator  # lazy: mt pulls the linker and kin tables
        snap = self._snap
        if snap is None:
            return Translator(FamilyGraph(self.space_id, lang, [], [], []), lang=lang)
        if lang not in self._translators:
            self._translators = {**self._translators, lang: Translator(snap.view.kin, lang=lang)}
        return self._translators[lang]

    @_locked
    def keyterms(self, speaker: str) -> list[str]:
        """3.3 ASR bias: Latin forms of entities in the speaker's world. Non-Latin keywords are VERIFY for Muse."""
        snap = self._snap
        if snap is None or speaker not in self.parts:
            return []
        v, S = snap.view, self.parts[speaker][0]
        out: dict[str, None] = {}
        for p in v.people.values():
            if p.id == S or v.visible(S, "person", p.id):
                out.update(dict.fromkeys(f for f in (p.name, *(a for a, _l in p.aliases)) if _latin(f)))
        for t in v.things.values():
            if v.visible(S, "thing", t.id):
                out.update(dict.fromkeys(f for f in (t.name, *t.aliases) if _latin(f)))
        return list(out)[:KEYTERMS_CAP]

    # ---- knowledge flush ----------------------------------------------------------------------------------------------
    def _take_dirty(self) -> dict[tuple[int, str, int], kn.State]:
        items = {k: self.kcache[k] for k in self._dirty if k in self.kcache}
        self._dirty = frozenset()
        return items

    def _flush_async(self) -> None:
        items = self._take_dirty()
        if items:
            self._submit(self._upsert, items)

    @staticmethod
    def _upsert(items: dict[tuple[int, str, int], kn.State]) -> None:
        """Concurrent calls by one user: last write wins per row (4, stated ceiling)."""
        if not items:
            return
        cols = ("p", "half_life_days", "first_at", "last_at", "last_day", "n_heard", "n_shown", "n_said",
                "n_confirmed", "n_asked")
        with session_scope() as s:
            rows = {(r.knower_id, r.item_kind, r.item_id): r for r in s.scalars(
                select(m.Knowledge).where(m.Knowledge.knower_id.in_({k for k, _x, _y in items})))}
            for (knower, kind, item_id), st in items.items():
                row = rows.get((knower, kind, item_id))
                if row is None:
                    row = m.Knowledge(knower_id=knower, item_kind=kind, item_id=item_id)
                    s.add(row)
                for c in cols:
                    setattr(row, c, getattr(st, c))

    # ---- extraction (6.1, D14) ----------------------------------------------------------------------------------------
    def _arm_idle(self) -> None:
        if self._idle is not None:
            self._idle.cancel()
        self._idle = self.loop.call_later(EXTRACT_IDLE_S, self._extract_async)

    def _extract_async(self) -> None:
        with self._lock:
            if self._extracting or self._extracted >= len(self._lines):
                return
            self._extracting = True
            start, end = self._extracted, len(self._lines)
            self._extracted = end
        self._submit(self._extract_job, start, end)

    def _extract_job(self, start: int, end: int) -> None:
        try:
            res = self._extract(start, end)
        finally:
            with self._lock:
                self._extracting = False
        if res is not None:
            self._on_loop(self._after_extract, res, self._rebuild())

    def _candidates(self, v: WorldView, sp: int) -> list[Candidate]:
        out = [Candidate("person", p.id, p.slug, p.name, p.is_user,
                         tuple(dict.fromkeys(x for x in (p.lang_name, *(a for a, _l in p.aliases)) if x)))
               for p in v.people.values() if p.id != sp and v.visible(sp, "person", p.id)]
        out += [Candidate("thing", t.id, t.slug, t.name, False, t.aliases) for t in v.things.values()
                if v.visible(sp, "thing", t.id)]
        out += [Candidate("group", g.id, g.slug, g.name, False) for g in v.groups.values()
                if v.visible(sp, "group", g.id)]
        return out

    def _extract(self, start: int, end: int):
        """Blocking: one LLM call, validate, apply. Returns (ApplyResult, clean update, speaker_of_line,
        audience_of_line) or None."""
        v = self.view
        lines = self._lines[max(0, start - EXTRACT_OVERLAP):end]
        if v is None or not lines:
            return None
        win = [Line(n, ln.speaker, ln.lang, ln.text) for n, ln in enumerate(lines)]
        everyone = list(dict.fromkeys(self._ever.values()))  # leave() empties parts before the call-end extraction
        parts = [Participant(p, v.people[p].slug, v.people[p].name, lang) for p, lang in everyone if p in v.people]
        speakers = sorted({ln.speaker for ln in lines})
        with session_scope() as s:
            own = {sp: own_context(s, sp) for sp in speakers}
        cands = {sp: self._candidates(v, sp) for sp in speakers}
        upd = run_extraction(None, self.call_id, win, parts, own, cands, sorted({lg for _p, lg in everyone}))
        if upd is None:
            return None
        clean, _dropped = validate(upd, validate_ctx(win, parts, own, cands))  # drops are logged by validate
        if not (clean.entities or clean.facts or clean.ties):
            return None
        speaker_of = {n: ln.speaker for n, ln in enumerate(lines)}
        line_aud = {n: list(ln.audience) for n, ln in enumerate(lines)}
        ctx = ApplyCtx(self.space_id, self.call_id, None, speaker_of, line_aud,
                       {n: ln.utterance_id for n, ln in enumerate(lines) if ln.utterance_id}, clock.now())
        try:
            with session_scope() as s:
                res = apply_update(s, clean, ctx)
        except SQLAlchemyError:
            log.exception("applying extraction failed for call %s", self.call_id)
            return None
        return res, clean, speaker_of, line_aud

    @_locked
    def _after_extract(self, res: tuple[ApplyResult, WorldUpdateOut, dict[int, int], dict[int, list[int]]],
                       snap: _Snap) -> None:
        """On the loop: swap in the new view, apply evidence, send late who/ask cards (2.5 trigger 3) via emit."""
        result, clean, speaker_of, line_aud = res
        now = clock.now()
        self._swap(snap)
        self._evidence(result.evidence, now)
        v = snap.view
        shown: list[tuple[int, int | None, C.Card]] = []
        for e in clean.entities:
            pid = result.entities.get(e.ref)
            fact = next((f for f in clean.facts if e.ref in (f.subject, *f.refs)), None)
            if ENTITY_TABLE[e.kind] != "person" or pid not in v.people or fact is None:
                continue
            S = speaker_of[fact.lines[0]]
            sp_ident = self._identity(S)
            heard = set(line_aud.get(fact.lines[0], ()))  # only people who heard that line may learn of the mention
            for ident, L, lang in self._listeners(sp_ident) if sp_ident else []:
                if L not in heard or not v.visible(L, "person", pid, S):
                    continue
                cards = self._late_card(v, L, S, pid, e.existing_id is None, now)
                cards = self._admit(v, ident, L, S, cards, frozenset({pid}), now)
                if cards:
                    shown += [(L, None, c) for c in cards]
                    self._send_later(ident, self._glance(sp_ident, ident, lang, cards, False))
        self._evidence([ev for L, _t, c in shown for ev in self._card_evidence(L, c)], now)
        self._log(shown, now)
        self._flush_async()

    def _late_card(self, v: WorldView, L: int, S: int, pid: int, is_new: bool, now: datetime) -> list[C.Card]:
        name = v.people[pid].name
        rendered = v.render(L, pid, S)
        if is_new and (rendered == name or rendered.startswith(f"{name}, mentioned by")):  # no relation L can place
            owner = v.people[S]
            return [C.ask(name, name, f"{owner.name} mentioned {name}",
                          [SuggestionOut(owner=owner.slug, relation="friend", label=f"{owner.name}'s friend")])]
        return C.gaps(v, self.kcache, L, S, [Hit(0, 0, name, "person", (pid,), name, True)], [], now)

    # ---- localization (8.5) -------------------------------------------------------------------------------------------
    def _localize(self, items: list[tuple[str, str]], lang: str) -> dict[str, str]:
        if not items:
            return {}
        name = MUSE_LANGUAGES.get(lang, lang)
        user = json.dumps([{"key": k, "body": b} for k, b in items], ensure_ascii=False)
        try:
            out = get_llm().structured(LocalizeOut, LOCALIZE_SYSTEM.format(lang=name), user,
                                       reasoning_effort="minimal", max_completion_tokens=1500,
                                       prompt_cache_key=f"kin-l10n-{lang}")
        except _LLM_ERRORS as e:
            log.warning("card localization to %s failed: %s: %s", lang, type(e).__name__, e)
            return {}
        src = dict(items)
        got = {it.key: it.body.strip() for it in out.items if it.key in src and it.body.strip()}
        with self._state:
            self._l10n = {**self._l10n, **{(k, lang, _sha(src[k])): b for k, b in got.items()}}
        return got

    def _prewarm(self, listener: int, lang: str) -> None:
        """Best effort: bodies are rendered without a speaker, so a live card rendered through one misses."""
        v, now = self.view, clock.now()
        if v is None:
            return
        people = sorted((p for p in v.people.values() if p.id != listener and v.visible(listener, "person", p.id)
                         and not v.structural_known(listener, "person", p.id)),
                        key=lambda p: v.first_mention.get(p.id, _EPOCH), reverse=True)[:LOCALIZE_TOP]
        self._localize([(f"who:{p.slug}", v.card_body(listener, "person", p.id, None, now)[0]) for p in people], lang)

    def _lazy_l10n(self, identity: str, lang: str, key: str, body: str) -> None:
        try:
            got = self._localize([(key, body)], lang)
        finally:
            with self._state:
                self._l10n_inflight = self._l10n_inflight - {(key, lang, _sha(body))}
        if key in got and (identity, key) in self.sent:  # skip a card retracted meanwhile
            self._send_later(identity, {"type": "glance_update", "key": key, "body": got[key]})
