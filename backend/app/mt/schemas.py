"""Structured output schema for grounded translation (plan §2 Phase 2). Strict-mode friendly: no defaults, closed objects."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class GroundedSpan(BaseModel):
    source: str      # surface form in the source utterance
    rendered: str    # how it was rendered for the listener, e.g. "your uncle Ravi mama (Mom's younger brother)"
    node_id: str     # family-graph slug, e.g. p_ravi_mama


class PragmaticsCard(BaseModel):
    kind: Literal["idiom", "proverb", "register", "honorific", "cultural"]
    source: str
    literal: str
    meaning: str
    why_it_matters: str


class TranslationOut(BaseModel):
    translation: str
    grounded_spans: list[GroundedSpan]
    pragmatics_cards: list[PragmaticsCard]
    passthrough_kept: list[str]   # heritage-language tokens left untranslated (Fade)
    confidence: float
