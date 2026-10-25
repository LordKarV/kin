"""LiveWorld background jobs: card localization and debounced / call-end extraction.

Split out of live.py for size only. `LiveJobs` is a mixin: LiveWorld inherits it and these methods read and write the
same live state (kcache, sent, _lines, ...) under the same lock. Nothing here is called from outside live.py.
"""
from __future__ import annotations

import functools
import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable

import openai
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from ..db import models as m
from ..db.session import session_scope
from ..graph.kin_tables import MUSE_LANGUAGES
from ..llm import StructuredOutputError, get_llm
from . import cards as C
from . import clock
from .apply import ApplyCtx, ApplyResult, apply_update
from .contracts import LocalizeOut, SuggestionOut, WorldUpdateOut
from .extract import (ENTITY_TABLE, Candidate, Line, Participant, ValidateCtx, _tie_fact, own_context, run_extraction,
                      validate, validate_ctx)
from .match import Hit
from .view import WorldView

if TYPE_CHECKING:
    from .live import LiveWorld, _Line, _Snap

log = logging.getLogger("kin.world.live")

# localization gets its own worker so a burst of misses never queues ahead of extraction, flushes or refresh()
_L10N_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kin-l10n")
EXTRACT_EVERY = 4
EXTRACT_IDLE_S = 30.0
EXTRACT_OVERLAP = 3
LOCALIZE_TOP = 30
_LLM_ERRORS = (StructuredOutputError, openai.APIError, TimeoutError)
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

LOCALIZE_SYSTEM = ("You localize short context cards shown during a live call. Translate each body into natural {lang} "
                   "({lang} script), as short as the English, keeping people's names as written. Return every key "
                   "unchanged with its translated body. Return JSON for the schema.")


def _sha(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()


def _new_only(raw: WorldUpdateOut, upd: WorldUpdateOut, first_new: int, vctx: ValidateCtx) -> WorldUpdateOut:
    """Overlap handling: lines before `first_new` were extracted last time and are context only. Facts citing only them
    are dropped (a model that ignores same_as would write them twice), with the ties and entities only they carried.
    `upd` is validate's output for `raw`. A tie fact validate synthesized (one speaker) sits on the speaker's
    first line, usually an overlap one, so it is kept: it is a tie fact with no storyline and not sensitive (validate
    never rewrites those) that the model did not send. Known limit: a tie the model re-sends from overlap lines without
    its tie fact gets one more tie Fact row (apply keeps the first Tie); marking synthesized facts in validate fixes
    that. Entities nothing cited pass through as validate let them (apply learns a known entity's new forms)."""
    if first_new == 0:
        return upd
    facts = [f for f in upd.facts if max(f.lines) >= first_new
             or (f.predicate == "tie" and f.storyline is None and not f.sensitive_kind and f not in raw.facts)]
    for i, f in enumerate(upd.facts):
        if f not in facts:  # index and length only: fact text is user content (privacy)
            log.info("extraction dropped: fact #%d (%d chars) cites only overlap lines %s", i, len(f.text_en), f.lines)
    refs = {e.ref: e for e in upd.entities}
    ties = [t for t in upd.ties if _tie_fact(t, facts, refs, vctx) is not None]

    def cited(fs, ts):
        return {tok for f in fs for tok in (f.subject, *f.refs)} | {tok for t in ts for tok in (t.a, t.b)}
    used, was = cited(facts, ties), cited(upd.facts, upd.ties)
    return WorldUpdateOut(entities=[e for e in upd.entities if e.ref in used or e.ref not in was], ties=ties,
                          facts=facts)


def _locked(fn: Callable) -> Callable:
    """The pipeline calls LiveWorld from the loop thread and from to_thread workers; every read-modify-write of live
    state (sent, pending, kcache, ...) runs under one lock. Known limit: one RLock per call, held ~1 ms in memory."""
    @functools.wraps(fn)
    def wrapper(self: "LiveWorld", *args, **kw):
        with self._state:
            return fn(self, *args, **kw)
    return wrapper


class LiveJobs:
    """Localization and extraction methods of LiveWorld (see the module docstring)."""

    # ---- localization -------------------------------------------------------------------------------------------------
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

    def _prewarm(self, listener: int, lang: str, speaker: int | None = None) -> None:
        """Best effort. Bodies render through `speaker` like a live card (cards._entity_card), so the (key, lang, body)
        cache hits when that speaker names the person; that also covers people the listener sees only through the
        speaker's own disclosure. Bodies already cached are not sent again (a rejoin prewarms again)."""
        v, now = self.view, clock.now()
        if v is None:
            return
        people = sorted((p for p in v.people.values() if p.id != listener
                         and v.visible(listener, "person", p.id, speaker)
                         and not v.structural_known(listener, "person", p.id)),
                        key=lambda p: v.first_mention.get(p.id, _EPOCH), reverse=True)[:LOCALIZE_TOP]
        items = [(f"who:{p.slug}", v.card_body(listener, "person", p.id, speaker, now)[0]) for p in people]
        self._localize([(k, b) for k, b in items if b and (k, lang, _sha(b)) not in self._l10n], lang)

    def _lazy_l10n(self, identity: str, lang: str, key: str, body: str) -> None:
        try:
            got = self._localize([(key, body)], lang)
        finally:
            with self._state:
                self._l10n_inflight = self._l10n_inflight - {(key, lang, _sha(body))}
        if key in got and (identity, key) in self.sent:  # skip a card retracted meanwhile
            self._send_later(identity, {"type": "glance_update", "key": key, "body": got[key]})

    # ---- extraction ---------------------------------------------------------------------------------------------------
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

    def _live_lines(self, start: int, end: int, extra: set[int]) -> tuple[list["_Line"], int, frozenset[int]]:
        """Window lines that may still go to the LLM, plus the index of the first new one (>= start) and which of the
        people in the lines or `extra` still exist. A privacy delete mid-call removes a speaker or
        redacts an utterance: those words never go back to the model. Audiences lose deleted people, whose rows
        would fail the FK and roll back the whole apply."""
        lo = max(0, start - EXTRACT_OVERLAP)
        raw = self._lines[lo:end]
        uids = {ln.utterance_id for ln in raw if ln.utterance_id is not None}
        with session_scope() as s:
            alive = frozenset(s.scalars(select(m.Person.id).where(m.Person.id.in_(
                extra | {p for ln in raw for p in (ln.speaker, *ln.audience)}))))
            text = dict(s.execute(select(m.Utterance.id, m.Utterance.src_text).where(m.Utterance.id.in_(uids))).all())
        keep = [(i, replace(ln, audience=tuple(p for p in ln.audience if p in alive)))
                for i, ln in enumerate(raw, lo)
                if ln.speaker in alive and (ln.utterance_id is None or (text.get(ln.utterance_id) or "").strip())]
        if len(keep) < len(raw):
            log.info("call %s: %d deleted or redacted lines left out of extraction", self.call_id, len(raw) - len(keep))
        first_new = next((n for n, (i, _ln) in enumerate(keep) if i >= start), len(keep))
        return [ln for _i, ln in keep], first_new, alive

    def _extract(self, start: int, end: int):
        """Blocking: one LLM call, validate, apply. Returns (ApplyResult, clean update, speaker_of_line,
        audience_of_line) or None."""
        v = self.view
        if v is None:
            return None
        everyone = list(dict.fromkeys(self._ever.values()))  # leave() empties parts before the call-end extraction
        lines, first_new, alive = self._live_lines(start, end, {p for p, _l in everyone})
        if first_new >= len(lines):  # nothing new survived
            return None
        win = [Line(n, ln.speaker, ln.lang, ln.text) for n, ln in enumerate(lines)]
        parts = [Participant(p, v.people[p].slug, v.people[p].name, lang) for p, lang in everyone
                 if p in v.people and p in alive]
        speakers = sorted({ln.speaker for ln in lines})
        with session_scope() as s:
            own = {sp: own_context(s, sp) for sp in speakers}
        cands = {sp: self._candidates(v, sp) for sp in speakers}
        upd = run_extraction(None, self.call_id, win, parts, own, cands, sorted({lg for _p, lg in everyone}))
        if upd is None:
            return None
        vctx = validate_ctx(win, parts, own, cands)
        clean = _new_only(upd, validate(upd, vctx)[0], first_new, vctx)  # drops are logged by validate
        if not (clean.entities or clean.facts or clean.ties):
            return None
        speaker_of = {n: ln.speaker for n, ln in enumerate(lines)}
        line_aud = {n: list(ln.audience) for n, ln in enumerate(lines)}
        # Stamp with when the lines were said, not when this job finishes: the dev clock may have jumped meanwhile.
        said = max((ln.at for ln in lines if ln.at is not None), default=None) or clock.now()
        ctx = ApplyCtx(self.space_id, self.call_id, None, speaker_of, line_aud,
                       {n: ln.utterance_id for n, ln in enumerate(lines) if ln.utterance_id}, said)
        try:
            with session_scope() as s:
                res = apply_update(s, clean, ctx)
        except SQLAlchemyError:
            log.exception("applying extraction failed for call %s", self.call_id)
            return None
        return res, clean, speaker_of, line_aud, said

    @_locked
    def _after_extract(self, res: tuple[ApplyResult, WorldUpdateOut, dict[int, int], dict[int, list[int]], datetime],
                       snap: _Snap) -> None:
        """On the loop: swap in the new view, apply evidence, send late who/ask cards (2.5 trigger 3) via emit."""
        result, clean, speaker_of, line_aud, said = res
        now = clock.now()
        self._swap(snap)
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
        # Ordering: the late-card decisions above read the state before these lines; shown before heard.
        self._evidence([ev for L, _t, c in shown for ev in self._card_evidence(L, c)], now)
        self._evidence(result.evidence, said)  # heard when said, not when extraction finished
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
