"""LiveWorld background jobs (docs/ARCHITECTURE.md 6.1, 8.5): card localization and debounced / call-end extraction.

Split out of live.py for size only. `LiveJobs` is a mixin: LiveWorld inherits it and these methods read and write the
same live state (kcache, sent, _lines, ...) under the same lock. Nothing here is called from outside live.py.
"""
from __future__ import annotations

import functools
import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable

import openai
from sqlalchemy.exc import SQLAlchemyError

from ..db.session import session_scope
from ..graph.kin_tables import MUSE_LANGUAGES
from ..llm import StructuredOutputError, get_llm
from . import cards as C
from . import clock
from .apply import ApplyCtx, ApplyResult, apply_update
from .contracts import LocalizeOut, SuggestionOut, WorldUpdateOut
from .extract import ENTITY_TABLE, Candidate, Line, Participant, own_context, run_extraction, validate, validate_ctx
from .match import Hit
from .view import WorldView

if TYPE_CHECKING:
    from .live import LiveWorld, _Snap

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


def _locked(fn: Callable) -> Callable:
    """The pipeline calls LiveWorld from the loop thread and from to_thread workers; every read-modify-write of live
    state (sent, pending, kcache, ...) runs under one lock. ponytail: one RLock per call, held ~1 ms in memory."""
    @functools.wraps(fn)
    def wrapper(self: "LiveWorld", *args, **kw):
        with self._state:
            return fn(self, *args, **kw)
    return wrapper


class LiveJobs:
    """Localization and extraction methods of LiveWorld (see the module docstring)."""

    # ---- localization (8.5) -------------------------------------------------------------------------------------------
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
