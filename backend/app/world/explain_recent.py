"""On-demand context by gesture, "what's this about?" (docs/ARCHITECTURE.md Amendment 7).

Candidates come from the last lines the caller heard from someone else, rendered with that line's real speaker, through
the same scan, card builders (world/cards.py), visibility and delivery guard as push cards. A clear top candidate is
answered with no LLM call; otherwise Muse Spark picks one by id from the lines plus candidate ids and display names
(never facts), "none" widens the window once, and a timeout or failure falls back to the top-ranked candidate.
The answer is `asked` evidence and a card_log row of kind "gesture", like a caption tap (world/explain.py).
"""
from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, replace
from typing import Literal

from pydantic import create_model
from sqlalchemy import select

from ..db import models as m
from ..db.session import session_scope
from ..llm import get_llm
from . import cards as C
from . import clock
from . import knowledge as kn
from .explain import VIA as TAP_VIA
from .explain import _ask, _name_like, record
from .live import LiveWorld, _Line

log = logging.getLogger("kin.world.explain")

VIA = "gesture"
WINDOW, WIDE = 4, 12  # lines heard; "none" widens once
MARGIN = 0.5  # top score minus runner-up at or above this: answer without the LLM
SHOWN_PENALTY = 0.3  # already shown this call: ranks lower, not out (kept under MARGIN so it alone never decides)
ASKED_PENALTY = 1.0  # this listener already asked for it this call (tap or gesture): a repeat twist wants something else
# every candidate comes from a line the listener just heard, so a card with no knowledge row (a term, a storyline state,
# an ambiguous ask) ranks at the prior after one "heard", like the entities on_final gave heard evidence
HEARD_P = kn.PRIOR + (1 - kn.PRIOR) * kn.LEARN["heard"]
LLM_TIMEOUT_S = 2.5
NONE = "none"
_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="kin-gesture")
SYSTEM = ("Someone on a live call is lost and asked what the conversation is about right now. Pick the one candidate, "
          "by id, that the recent lines (the last line most of all) refer to, or \"none\" if you cannot tell. "
          "Return JSON for the schema.")


@dataclass(frozen=True)
class _Cand:
    card: C.Card
    speaker: int
    mentioned: frozenset[int]
    score: float


def explain_recent(live: LiveWorld, call_id: int, listener_person_id: int) -> list[dict]:
    """GlanceItem dicts (zero or one) for what the last lines `listener_person_id` heard are about. Raises LookupError
    when the listener is not in the live call. Blocking: DB reads, up to two LLM calls of LLM_TIMEOUT_S each."""
    L = listener_person_id
    if f"p{L}" not in live.parts:
        raise LookupError(f"person {L} is not in call {call_id}")
    lines = _heard(live, L, WINDOW)
    cands = _candidates(live, L, lines)
    if not cands:
        return _ask_unknown(live, L, lines)
    if len(cands) == 1 or cands[0].score - cands[1].score >= MARGIN:
        return _answer(live, L, cands[0])
    pick = _choose(live, L, lines, cands)
    if pick == NONE:
        lines = _heard(live, L, WIDE)
        cands = _candidates(live, L, lines)
        pick = _choose(live, L, lines, cands) if cands else NONE
    return [] if pick == NONE else _answer(live, L, pick)


def _heard(live: LiveWorld, L: int, n: int) -> list[_Line]:
    """Lines L heard, minus any a privacy delete removed or redacted mid-call (section 10): those words are never
    scanned or sent to the model again."""
    lines = live.heard(L, n)
    uids = [ln.utterance_id for ln in lines if ln.utterance_id is not None]
    with session_scope() as s:
        text = dict(s.execute(select(m.Utterance.id, m.Utterance.src_text).where(m.Utterance.id.in_(uids))).all())
    return [ln for ln in lines if ln.utterance_id is None or (text.get(ln.utterance_id) or "").strip()]


def _candidates(live: LiveWorld, L: int, lines: list[_Line]) -> list[_Cand]:
    """Best first. Newest line first, so a card key seen twice keeps its most recent mention."""
    ident = f"p{L}"
    with live._state:
        snap = live._snap
        if snap is None or ident not in live.parts:
            return []
        v, now, lang = snap.view, clock.now(), live.parts[ident][1]
        # a gesture means "I'm lost": the knowledge gate must not hide a card (as for a tap); p only ranks
        no_states = {k: st for k, st in live.kcache.items() if not (k[0] == L and k[1] == "state")}
        asked = {r.key for r in live._log_rows if r.listener_id == L and r.kind in (VIA, TAP_VIA)}
        best: dict[str, _Cand] = {}
        for back, ln in enumerate(reversed(lines)):
            S = ln.speaker
            hits = [h for h in snap.index.scan(ln.text, ln.lang) if h.kind in C.ENTITY_KINDS]
            resolved, ambiguous = live._rank(v, hits, S)
            sid = live._identity(S)
            if sid is not None:  # 3.5 needs the speaker on the call
                resolved = resolved + live._relational(snap, sid, ln.text, resolved + ambiguous)
            read = ln.translations.get(lang) if lang != ln.lang else None
            kw_hits = snap.kw.scan(ln.text, ln.lang) + (snap.kw.scan(read, lang) if read else [])
            lex = live._matcher(ln.lang).match(ln.text) if ln.lang and lang != ln.lang else []
            mentioned = frozenset(h.ids[0] for h in resolved if h.kind == "person")
            found = C.gaps(v, {}, L, S, resolved + ambiguous, lex, now) + C.storylines(
                v, no_states, L, S, kw_hits, resolved, now)
            for c in found:
                if c.key in best or not C.deliver_ok(v, c, L, S, mentioned, now):
                    continue
                st = live.kcache.get(_kkey(L, c))
                score = 1 / (back + 1) + 1 - (kn.p_now(st, now) if st else HEARD_P)
                score -= SHOWN_PENALTY if (ident, c.key) in live.sent else 0.0
                score -= ASKED_PENALTY if c.key in asked else 0.0
                best[c.key] = _Cand(c, S, mentioned, score)
        return sorted(best.values(), key=lambda c: -c.score)


_WORD = re.compile(r"[^\W\d_]+")
_SENTENCE_END = ".!?\u3002\uff01\uff1f"


def _names(text: str) -> list[str]:
    """Name-like words of a line, last first, by the tap's _name_like. ponytail: a sentence's first word is skipped
    (capitalized anyway), so a name that opens a sentence is missed, and a script without case (zh, hi, ta) yields
    none (every short word there would pass); its translation into the listener's language still counts. Upgrade
    path: let the LLM pick among these spans."""
    out = []
    for mt in _WORD.finditer(text):
        head, w = text[:mt.start()].rstrip(), mt.group()
        if head and head[-1] not in _SENTENCE_END and w[0].isupper() and _name_like(w, []):
            out.append(w)
    return out[::-1]


def _ask_unknown(live: LiveWorld, L: int, lines: list[_Line]) -> list[dict]:
    """No known candidate: the tap's "Who is X?" for the newest name-like word L heard that nothing visible to L
    matches. A match hidden from L counts as no match, as for a tap (explain.explain), so it answers like an unknown
    name and never with that person's card."""
    ident = f"p{L}"
    with live._state:
        snap = live._snap
        if snap is None or ident not in live.parts:
            return []
        v, now, lang = snap.view, clock.now(), live.parts[ident][1]
        for ln in reversed(lines):
            read = ln.translations.get(lang) if lang != ln.lang else None
            for text, lg in ((ln.text, ln.lang), (read or "", lang)):
                for w in _names(text):
                    hits = [h for h in snap.index.scan(w, lg) if h.kind in C.ENTITY_KINDS]
                    if not any(v.visible(L, h.kind, i, ln.speaker) for h in hits for i in h.ids):
                        return record(live, L, lang, [_ask(v, ln.speaker, w)], VIA, now)
        return []


def _kkey(L: int, c: C.Card) -> tuple[int, str, int] | None:
    kind = c.item.get("kind")
    if kind in C.ENTITY_KINDS:
        return (L, kind, c.item["id"])
    if kind == "storyline":
        return (L, "state", c.item["state"])
    return None  # ask / term: no knowledge row, ranked at HEARD_P


def _choose(live: LiveWorld, L: int, lines: list[_Line], cands: list[_Cand]) -> _Cand | str:
    """Muse Spark picks a candidate id or "none". The schema allows only those ids. Timeout or any failure: the
    top-ranked candidate. Sends the lines the listener heard and candidate ids and display names only."""
    by_key = {c.card.key: c for c in cands}
    Choice = create_model("GestureChoice", choice=(Literal[(*by_key, NONE)], ...))
    with live._state:
        v, lang = live.view, live.parts.get(f"p{L}", (L, ""))[1]
        names = {S: v.people[S].name for S in {ln.speaker for ln in lines} if v is not None and S in v.people}
    # a speaker is someone on the call; the listener's own translation is what they read
    heard = [f"{names.get(ln.speaker, 'Someone')}: {ln.text}"
             + (f" ({ln.translations[lang]})" if lang != ln.lang and ln.translations.get(lang) else "") for ln in lines]
    user = ("RECENT LINES (oldest first)\n" + "\n".join(heard) + "\n\nCANDIDATES (id | name)\n"
            + "\n".join(f"{k} | {c.card.payload.get('title') or k}" for k, c in by_key.items()))
    llm = get_llm()
    fut = _POOL.submit(llm.structured, Choice, SYSTEM, user, reasoning_effort="minimal", max_completion_tokens=800,
                       prompt_cache_key="kin-gesture")
    try:
        out = fut.result(timeout=LLM_TIMEOUT_S)
    except FutureTimeout:
        log.warning("gesture pick timed out after %.1f s; top-ranked candidate", LLM_TIMEOUT_S)
        return cands[0]
    except Exception as e:  # noqa: BLE001  StructuredOutputError (logged in llm.py), API errors: fall back, never fail
        log.warning("gesture pick failed (%s: %s); top-ranked candidate", type(e).__name__, e)
        return cands[0]
    return NONE if out.choice == NONE else by_key[out.choice]


def _answer(live: LiveWorld, L: int, cand: _Cand) -> list[dict]:
    """Re-run the guard on the current view (it may have been rebuilt while the LLM ran), then record like a tap."""
    with live._state:
        snap, now, ident = live._snap, clock.now(), f"p{L}"
        if snap is None or ident not in live.parts or not C.deliver_ok(snap.view, cand.card, L, cand.speaker,
                                                                         cand.mentioned, now):
            return []
        # gap None: the client labels it "You asked", as for a tap
        card = replace(cand.card, payload={**cand.card.payload, "gap": None})
        return record(live, L, live.parts[ident][1], [card], VIA, now)
