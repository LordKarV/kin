"""On-demand context: a listener taps a word in a caption (docs/ARCHITECTURE.md Amendment 5).

The tapped span runs through the same alias index, ranking, card builders (world/cards.py) and delivery guard as push
cards, for this listener only, so a tap never reveals anything a push card could not. The tap is `asked` evidence (the
listener did not know it), and the card is logged and marked sent so it is not pushed again right after.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from ..db import models as m
from ..db.session import session_scope
from ..graph.kin_tables import load_table
from ..graph.ontology import normalize_term
from . import cards as C
from . import clock
from .contracts import SuggestionOut
from .live import LiveWorld

log = logging.getLogger("kin.world.explain")

# card_log has no `via` column; kind = "explain" marks a tap (the card's own kind is the key prefix: who:/what:/ask:)
VIA = "explain"
# ponytail: sentence-initial words are capitalized too; this short list keeps "The" from becoming "Who is The?".
# Upgrade path: send the tap's offset in the caption and skip offset 0.
_NOT_NAMES = frozenset("i the a an and but so oh ok okay yes no we you he she they it my your our their this that "
                       "what who when where why how hi hey".split())
_UNCASED_MAX = 8  # longer uncased spans are phrases, not a name


def _speaker(live: LiveWorld, call_id: int, listener: int, utterance_id: int | None) -> int | None:
    """Whose words were tapped: the utterance's speaker, else the only other participant, else None (render without)."""
    if utterance_id is not None:
        with session_scope() as s:
            u = s.get(m.Utterance, utterance_id)
            if u is None or u.call_id != call_id:
                raise LookupError(f"utterance {utterance_id} is not in call {call_id}")
            return u.speaker_id
    others = {p for p, _l in live.parts.values() if p != listener}
    return others.pop() if len(others) == 1 else None


def _kin_term(text: str, langs: set[str]) -> bool:
    key = normalize_term(text)
    for lang in langs:
        try:
            d = load_table(lang).surface_forms().get(key)
        except (KeyError, FileNotFoundError, ValueError) as e:
            log.info("no kin table for %s: %s", lang, e)
            continue
        if d is not None and d.kind == "kin":
            return True
    return False


def _name_like(text: str, lex: list) -> bool:
    """Decided from the span alone, never from the hidden graph, so a hidden name and an unknown one get the same
    answer. ponytail: a script without letter case (zh, hi, ta) has no capital to go by, so any short span there that
    is no lexicon term counts; a common zh word gets "Who is X?". Upgrade path: a per-language common-word list."""
    t = text.strip()
    if any(ch.isupper() or ch.islower() for ch in t):
        return len(t) >= 2 and t[0].isupper() and t.lower() not in _NOT_NAMES
    return 0 < len(t) <= _UNCASED_MAX and not lex


def explain(live: LiveWorld, call_id: int, listener_person_id: int, text: str,
            utterance_id: int | None = None) -> list[dict]:
    """GlanceItem dicts for `text` as `listener_person_id` may see it: entity/term cards, one "ask" item when the span
    looks like a name or kin term but matches nothing visible, or [] for an ordinary word. Raises LookupError when
    the listener is not in the live call or the utterance is not in this call. Blocking (DB read, card_log write)."""
    L = listener_person_id
    ident = f"p{L}"
    if ident not in live.parts:
        raise LookupError(f"person {L} is not in call {call_id}")
    S = _speaker(live, call_id, L, utterance_id)
    with live._state:
        snap = live._snap
        if snap is None or not text.strip():
            return []
        v, now = snap.view, clock.now()
        lang = live.parts[ident][1]
        slang = next((lg for p, lg in live.parts.values() if p == S), None) or (v.people[S].lang if S in v.people else "")
        rank_as = S if S is not None else L
        hits = [h for h in snap.index.scan(text, slang) if h.kind in C.ENTITY_KINDS]
        resolved, ambiguous = live._rank(v, hits, rank_as)
        lex = live._matcher(slang).match(text) if slang else []
        mentioned = frozenset(h.ids[0] for h in resolved if h.kind == "person")
        # empty kcache: a tap means "I don't know this", so the knowledge gate must not hide the card
        # storylines keep the owner-known gate but drop "already knows the newest state": the tap says they do not
        no_states = {k: st for k, st in live.kcache.items() if not (k[0] == L and k[1] == "state")}
        found = C.gaps(v, {}, L, S, resolved + ambiguous, lex, now) + C.storylines(
            v, no_states, L, S, snap.kw.scan(text, slang), resolved, now)
        cards = [c for c in found if C.deliver_ok(v, c, L, S, mentioned, now)]
        cards = [_reminder(c, live.kcache.get((L, c.item["kind"], c.item["id"]))) for c in cards]
        seen = any(v.visible(L, h.kind, i, S) for h in hits for i in h.ids)  # known to them: no card, never an ask
        named = _name_like(text, lex) or _kin_term(text, {lang, slang, "en"} - {""})
        if not cards and not seen and named:
            cards = [_ask(v, S, text.strip())]  # a name nobody visible has: same "Who is X?" flow as new_people
        live._evidence([e for c in cards for e in _asked(L, c)], now)
        live.sent = live.sent | {(ident, c.key) for c in cards}
        live.delivered = {**live.delivered, **{(ident, c.key): c for c in cards}}
        live._log([(L, None, replace(c, kind=VIA)) for c in cards], now)
        live._flush_async()
        return [live._payload(ident, lang, c, False) for c in cards]


def _asked(L: int, c: C.Card) -> list[tuple[int, str, int, str]]:
    """Like LiveWorld._card_evidence, with "asked" (the listener did not know it) in place of "shown"."""
    kind = c.item.get("kind")
    if kind in C.ENTITY_KINDS:
        return [(L, kind, c.item["id"], "asked")]
    if kind == "storyline":
        return [(L, "state", c.item["state"], "asked")]
    return []


def _reminder(c: C.Card, st) -> C.Card:
    """The card was built as "new"; a listener with prior evidence is being reminded."""
    if st is None or c.payload.get("gap") is None:
        return c
    return replace(c, payload={**c.payload, "gap": "reminder"})


def _ask(v, S: int | None, term: str) -> C.Card:
    owner = v.people.get(S) if S is not None else None
    if owner is None:
        return C.ask(term, term, f"KIN doesn't know {term} yet", [])
    sugg = [SuggestionOut(owner=owner.slug, relation="friend", label=f"{owner.name}'s friend")]
    return C.ask(term, term, f"{owner.name} mentioned {term}", sugg)
