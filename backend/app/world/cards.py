"""Per-listener card selection (docs/ARCHITECTURE.md 8.6, bridges 5, storylines 6.5). Pure functions over a
WorldView and a knowledge cache; LiveWorld (live.py) owns dedupe, delivery and evidence.

Every card carries the fact ids its body cites; `deliver_ok` (D13) re-checks them for the listener right before a send.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

from ..cards.matcher import Match
from ..config import get_settings
from . import knowledge as kn
from .contracts import BridgeOut, GlanceItem, StateOut, SuggestionOut
from .match import ISOLATING, AliasIndex, Hit, fold, script_of
from .view import WorldView
from .visibility import FactV, bridge_candidate, usable

log = logging.getLogger("kin.world.cards")

KCache = dict[tuple[int, str, int], kn.State]
ENTITY_KINDS = ("person", "thing", "group")
CARD_KIND = {"person": "who", "thing": "what", "group": "who"}
BRIDGE_WINDOW = timedelta(days=180)
BRIDGE_CANDIDATES = 50
BRIDGE_GAP = timedelta(seconds=90)
BRIDGES_PER_CALL = 3
BRIDGE_REPEAT = timedelta(days=7)
RERANK_TOP, RERANK_TIMEOUT_S = 3, 2.5
STRONG_LATIN, STRONG_ISOLATING = 4, 2
STORY_STATES = 3
OWNER_KNOWN = 0.5
_RERANK_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kin-rerank")


@dataclass(frozen=True)
class Card:
    key: str
    kind: str
    item: dict  # internal: {"kind", "id", "start"?, "state"?}; never sent
    fact_ids: tuple[int, ...]
    payload: dict  # GlanceItem JSON (9.1)


@dataclass(frozen=True)
class LogRow:
    call_id: int
    listener_id: int
    target_id: int | None
    kind: str
    key: str
    at: datetime


@dataclass(frozen=True)
class CardLogView:
    """card_log rows that bear on rate limits: this call's and the last 7 days' bridges of the listeners."""
    call_id: int
    rows: tuple[LogRow, ...] = ()


def _glance(**kw) -> dict:
    return GlanceItem(**kw).model_dump()


def _entity(view: WorldView, kind: str, id_: int):
    return {"person": view.people, "thing": view.things, "group": view.groups}[kind].get(id_)


def entity_key(view: WorldView, kind: str, id_: int) -> str | None:
    e = _entity(view, kind, id_)
    return f"{CARD_KIND[kind]}:{e.slug}" if e is not None else None


# ---- who / what / term (8.6) ------------------------------------------------------------------------------------------
def gaps(view: WorldView, kcache: KCache, listener: int, speaker: int, hits: list[Hit], lex: list[Match],
         now: datetime) -> list[Card]:
    """Cards for the gaps in `listener`'s common ground. A hit with several ids is an ambiguous mention (3.4): an ask
    with candidates, never a guessed who card. Term/saying cards only across languages."""
    if listener == speaker:
        return []
    out: list[Card] = []
    for h in hits:
        if h.kind not in ENTITY_KINDS:
            continue
        c = _ask_ambiguous(view, listener, speaker, h) if len(h.ids) > 1 else _entity_card(view, kcache, listener,
                                                                                            speaker, h, now)
        if c is not None:
            out.append(c)
    lp, sp = view.people.get(listener), view.people.get(speaker)
    if lex and lp is not None and sp is not None and lp.lang and sp.lang and lp.lang != sp.lang:
        taken = [(h.start, h.end) for h in hits]
        for mt in lex:
            if not any(mt.start < e and s < mt.end for s, e in taken):
                out.append(_lex_card(mt))
    return out


def _entity_card(view: WorldView, kcache: KCache, listener: int, speaker: int, h: Hit, now: datetime) -> Card | None:
    id_ = h.ids[0]
    ent = _entity(view, h.kind, id_)
    if ent is None or (h.kind == "person" and id_ == listener) or not view.visible(listener, h.kind, id_, speaker):
        return None
    gap = kn.decide(kcache.get((listener, h.kind, id_)), now, view.structural_known(listener, h.kind, id_))
    if gap is None:
        return None
    body, fids = view.card_body(listener, h.kind, id_, speaker, now)
    if h.kind == "person":  # cite the hops the render quotes, so the guard re-checks them too (D13)
        fids = tuple(dict.fromkeys((*fids, *_render_facts(view, listener, id_, speaker))))
    key = entity_key(view, h.kind, id_)
    category = {"person": "person", "group": "group"}.get(h.kind) or ent.kind
    payload = _glance(key=key, kind=CARD_KIND[h.kind], title=ent.name, native=getattr(ent, "lang_name", ""),
                      body=body, category=category, node_id=ent.slug, gap=gap)
    return Card(key, CARD_KIND[h.kind], {"kind": h.kind, "id": id_, "start": h.start}, fids, payload)


def _render_facts(view: WorldView, ego: int, e: int, speaker: int | None) -> tuple[int, ...]:
    """Fact ids behind the hops `view.render(ego, e, speaker)` walks, mirroring view._render's branch order.
    ponytail: kin renders cite nothing here although link_kin stamps each edge with a fact, so the guard trusts
    view._kin_ok for them; returning the hop ids from view.card_body would close that."""
    mentioned = frozenset({e})
    ok = lambda a, h: view._hop_ok(ego, speaker, a, h, mentioned)  # noqa: E731
    if e == ego or view._kin_ok(ego, e, ok):
        return ()
    h = view._hop(ego, e, ("tie",), ok)
    if h:
        return ()  # a hop touching the ego needs no fact (view._hop_ok)
    if speaker is not None and speaker not in (ego, e) and speaker in view.people:
        if view._kin_ok(speaker, e, ok):
            return ()
        h = view._hop(speaker, e, ("tie", "group"), ok)
        if h:
            return _hop_facts(view, ego, speaker, h)
    path = view._bfs(ego, e, ok)
    return tuple(f for a, h in path or () for f in _hop_facts(view, ego, a, h))


def _hop_facts(view: WorldView, ego: int, a: int, h) -> tuple[int, ...]:
    """Like view._hop_ok: the ego's own membership and a hop touching the ego need no fact."""
    if h.kind == "group":
        return tuple(f for f, p in view.gpair.get((a, h.to, h.label), ()) if f is not None and p != ego)
    return (h.fact_id,) if h.fact_id is not None and ego not in (a, h.to) else ()


def _ask_ambiguous(view: WorldView, listener: int, speaker: int, h: Hit) -> Card | None:
    cands = [i for i in h.ids if h.kind == "person" and i in view.people and view.visible(listener, "person", i, speaker)]
    if len(cands) < 2:
        return None  # only one candidate this listener may see: nothing to disambiguate for them
    sugg = [SuggestionOut(owner=view.people[i].slug, relation="same_as", label=view.render(listener, i, speaker))
            for i in cands]
    return ask(h.surface, h.surface, f"Which {h.surface}?", sugg, {"kind": "ask", "id": None, "start": h.start})


def ask(term: str, guess: str, body: str, suggestions: list[SuggestionOut], item: dict | None = None) -> Card:
    """"Who is X?" card (2.5). Cites no facts: suggestions are renders over hops the listener may already see."""
    key = f"ask:{fold(term)[0].strip()}"[:80]
    payload = _glance(key=key, kind="ask", title=term, body=body, category="person", term=term, guess=guess,
                      suggestions=suggestions)
    return Card(key, "ask", item or {"kind": "ask", "id": None}, (), payload)


def _lex_card(mt: Match) -> Card:
    e = mt.entry
    kind = "saying" if e.category == "saying" else "term"
    payload = _glance(key=e.key, kind=kind, title=mt.source, native=e.native,
                      body=". ".join(x for x in (e.translate_as, e.note) if x), category=e.category)
    return Card(e.key, kind, {"kind": "lex", "id": e.key, "start": mt.start}, (), payload)


# ---- bridges (5) ------------------------------------------------------------------------------------------------------
def bridge_candidates(view: WorldView, listener: int, other: int, now: datetime) -> list[FactV]:
    """Self-only by construction (visibility.bridge_candidate): the listener's own facts `other` has not heard.
    A fact that refers to `other` is news about them, not for them ("Mei is my friend in Shanghai")."""
    lo = now - BRIDGE_WINDOW
    # listener in audience: apply always writes the speaker's row; without it the guard would drop the card
    found = [f for f in view.facts.values() if f.said_at >= lo and listener in view.audience.get(f.id, frozenset())
             and ("person", other) not in f.refs
             and bridge_candidate(f, view.audience.get(f.id, frozenset()), listener, other, now)]
    return sorted(found, key=lambda f: f.said_at, reverse=True)[:BRIDGE_CANDIDATES]


def _strong(form: str) -> bool:
    """Hangul is spaced but syllabic, so it counts like the isolating scripts; every other alphabet (Tamil,
    Devanagari, Cyrillic, Arabic) like Latin, in code points (vowel signs included)."""
    f = fold(form)[0].strip()
    script = next((script_of(c) for c in f if c.isalpha()), "common")
    if script in ISOLATING or script == "hangul":
        return len(f) >= STRONG_ISOLATING
    return script != "common" and len(f) >= STRONG_LATIN


def relevant(facts: list[FactV], texts: Iterable[str], hits: Iterable[Hit], langs: Iterable[str] = ()) -> list[FactV]:
    """Facts whose concept groups the texts hit at pass strength (5.2), in the given order. A group counts once;
    a hit on an entity in f.refs counts as one extra concept. Pass: one strong concept, or two concepts.
    langs[i] is the language of texts[i]: it turns on the 3.2 suffix and virama-stem rules."""
    if not facts:
        return []
    # kind "c<group index>" keeps each concept group apart inside one index
    idx = AliasIndex((form, f"c{gi}", f.id) for f in facts for gi, group in enumerate(f.keys) for form in group)
    concepts: dict[int, set[str]] = defaultdict(set)
    strong: set[int] = set()
    texts, langs = list(texts), list(langs)
    for t, lg in zip(texts, langs + [""] * (len(texts) - len(langs))):
        for h in idx.scan(t, lg):
            for fid in h.ids:
                concepts[fid].add(h.kind)
                if _strong(h.form):
                    strong.add(fid)
    linked = {(h.kind, i) for h in hits for i in h.ids}
    return [f for f in facts if f.id in strong or len(concepts[f.id]) + (1 if f.refs & linked else 0) >= 2]


def bridges(view: WorldView, kcache: KCache, listener: int, speaker: int, texts: list[str], hits: list[Hit],
            now: datetime, log: CardLogView, langs: list[str] = ()) -> list[Card]:
    """At most one private bridge for `listener` while `speaker` talks, under the 5.4 rate limits. A `told` row
    (5.6 fast path on a non-shareable fact) blocks like a sent bridge but does not count toward the rate limits."""
    lp, sp = view.people.get(listener), view.people.get(speaker)
    if listener == speaker or lp is None or sp is None or not lp.is_user:
        return []
    mine = [r for r in log.rows if r.kind == "bridge" and r.listener_id == listener]
    if any(now - r.at < BRIDGE_GAP for r in mine) or sum(r.call_id == log.call_id for r in mine) >= BRIDGES_PER_CALL:
        return []
    told = {r.key for r in log.rows if r.kind in ("bridge", "told") and r.listener_id == listener
            and r.target_id == speaker and now - r.at < BRIDGE_REPEAT}
    found = relevant([f for f in bridge_candidates(view, listener, speaker, now) if f"bridge:{f.id}" not in told],
                     texts, hits, langs)
    if found and get_settings().bridge_rerank:
        found = _rerank(found[:RERANK_TOP], texts)
    if not found:
        return []
    f = found[0]
    key = f"bridge:{f.id}"
    payload = _glance(key=key, kind="bridge", title=f"You haven't told {sp.name}", body=f.text, category="bridge",
                      target=sp.slug, private=True)
    return [Card(key, "bridge", {"kind": "fact", "id": f.id, "target": speaker}, (f.id,), payload)]


RERANK_SYSTEM = ("Pick the one fact (by id) that the speaker's words make natural to share right now, or null if none "
                 "fits. Return JSON for the schema.")


def _rerank(top: list[FactV], texts: list[str]) -> list[FactV]:
    """Optional (settings.bridge_rerank, default off): one BridgeOut call, 2.5 s budget; timeout or error = no bridge."""
    from ..llm import get_llm  # lazy: the default path never touches the LLM
    user = "FACTS (id | text)\n" + "\n".join(f"{f.id} | {f.text}" for f in top) + "\n\nSPEAKER SAID\n" + "\n".join(texts)
    fut = _RERANK_POOL.submit(lambda: get_llm().structured(BridgeOut, RERANK_SYSTEM, user, reasoning_effort="minimal",
                                                           max_completion_tokens=800, prompt_cache_key="kin-bridge"))
    try:
        out = fut.result(timeout=RERANK_TIMEOUT_S)
    except FutureTimeout:
        log.warning("bridge rerank timed out after %.1f s; no bridge", RERANK_TIMEOUT_S)
        return []
    except Exception as e:  # noqa: BLE001  StructuredOutputError, API errors: the rerank only ever removes a bridge
        log.warning("bridge rerank failed (%s: %s); no bridge", type(e).__name__, e)
        return []
    return [f for f in top if f.id == out.fact_id]


# ---- storylines (6.5) -------------------------------------------------------------------------------------------------
def storylines(view: WorldView, kcache: KCache, listener: int, speaker: int, kw_hits: list[Hit], hits: list[Hit],
               now: datetime) -> list[Card]:
    if listener == speaker:
        return []
    kw = {(h.kind, i) for h in kw_hits for i in h.ids}
    persons = frozenset(i for h in hits if h.kind == "person" for i in h.ids)
    out: list[Card] = []
    for st in view.storylines.values():
        if st.owner_id == listener:  # their own thread: nothing to catch up on
            continue
        concept = any(("fact", fid) in kw for _sid, _l, _at, fid, _s in st.states)
        if ("storyline", st.id) not in kw and not (st.owner_id in persons and concept):
            continue
        ok = lambda fid: fid in view.facts and usable(  # noqa: E731
            view.facts[fid], view.audience.get(fid, frozenset()), listener, speaker, persons, now)
        usable_states = [(sid, label, at, fid) for sid, label, at, fid, status in st.states
                         if status != "contradicted" and ok(fid)]
        unclear = [(sid, label, at, fid) for sid, label, at, fid, status in st.states
                   if status == "contradicted" and ok(fid)] if st.unresolved else []
        if len(unclear) >= 2:  # 6.4: only listeners for whom both contradicting facts are usable
            usable_states = unclear[-2:]
        elif not usable_states:
            continue
        newest = usable_states[-1][0]
        if kn.decide(kcache.get((listener, "state", newest)), now, structural=False) is None:
            continue
        owner = st.owner_id
        if not (view.structural_known(listener, "person", owner)
                or kn.p_now(kcache.get((listener, "person", owner)), now) >= OWNER_KNOWN):
            continue
        last = usable_states[-STORY_STATES:]
        name = view.people[owner].name if owner in view.people else ""
        title, title_fids = view.story_title(st, listener, speaker, persons, now)
        if len(unclear) >= 2:
            body = f"{name}'s {title}: unclear: {last[0][1]} or {last[1][1]}"
        else:
            body = f"{name}'s {title}: " + " -> ".join(f"{label} ({at:%b})" for _s, label, at, _f in last)
        states = [StateOut(label=label, at=at.date().isoformat(),
                           known=kn.p_now(kcache.get((listener, "state", sid)), now) >= kn.FORGOT)
                  for sid, label, at, _f in last]
        key = f"story:{st.id}"
        payload = _glance(key=key, kind="storyline", title=title, body=body, category="storyline",
                          storyline_id=st.id, states=states)
        out.append(Card(key, "storyline", {"kind": "storyline", "id": st.id, "state": newest},
                        tuple(dict.fromkeys((*title_fids, *(f for *_x, f in last)))), payload))
    return out


# ---- delivery guard (D13) ---------------------------------------------------------------------------------------------
def deliver_ok(view: WorldView, card: Card, listener: int, speaker: int, mentioned: frozenset[int],
               now: datetime) -> bool:
    """Every cited fact must be usable for the listener with this speaker; a bridge must cite only the listener's own
    facts. A failure is a bug upstream: logged, and the caller drops the card."""
    for fid in card.fact_ids:
        f = view.facts.get(fid)
        ok = f is not None and usable(f, view.audience.get(fid, frozenset()), listener, speaker, mentioned, now)
        if ok and card.kind == "bridge":
            ok = f.subject_id == listener and f.speaker_id == listener
        if not ok:
            log.warning("guard dropped %s for %s", card.key, listener)
            return False
    return True
