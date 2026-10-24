"""Post-filter for pragmatics cards: only cards whose source is really in the utterance, deduped, capped."""
from __future__ import annotations

from rapidfuzz import fuzz

from .schemas import PragmaticsCard

MAX_CARDS = 2


def filter_cards(cards: list[PragmaticsCard], src_text: str) -> list[PragmaticsCard]:
    out: list[PragmaticsCard] = []
    seen: set[str] = set()
    for c in cards:
        key = c.source.strip().lower()
        if not key or key in seen:
            continue
        if key not in src_text.lower() and fuzz.partial_ratio(key, src_text.lower()) < 80:
            continue
        if not c.meaning.strip():
            continue
        seen.add(key)
        out.append(c)
        if len(out) >= MAX_CARDS:
            break
    return out
