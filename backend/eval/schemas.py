"""Pydantic schemas for the eval test sets (plan Phase 1 acceptance)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

VIRAMA = "\u0bcd"  # Tamil pulli; dropped when a case suffix attaches (பொங்கல் + உக்கு → பொங்கலுக்கு)


def stem_in(source: str, text: str) -> bool:
    """True if `source` occurs in `text`, allowing the final pulli to be replaced by a suffix vowel sign."""
    if source in text:
        return True
    if source.endswith("\u0bae" + VIRAMA):  # -ம் nouns drop the ம் before a suffix (கல்யாணம் → கல்யாணத்துக்கு)
        return source[:-2] in text
    return source.endswith(VIRAMA) and source[:-1] in text


class ExpectedEntity(BaseModel):
    source: str                      # surface form as it appears in src_text or src_roman
    node: str                        # slug of the person/thing the span must resolve to
    type: Literal["person", "dish", "place", "event"]
    # Each inner list is a group of alternatives; at least one string from EVERY group must appear
    # (case/punct-insensitive) in the rendered span (or translation for the generic baseline).
    must_include: list[list[str]]
    must_not_include: list[str] = Field(default_factory=list)   # generic flattenings, e.g. "soup" for rasam


class GroundingItem(BaseModel):
    id: str
    category: Literal["kin", "name_collision", "dish_place"]
    speaker: str = "p_kamala"
    listener: str = "p_arjun"
    context: list[str] = Field(default_factory=list)   # prior utterances (romanized), oldest first
    src_text: str                                       # Tamil script, as ASR would emit it
    src_roman: str                                      # romanized, for readers and the fuzzy linker
    gloss: str                                          # plain English meaning (for humans)
    entities: list[ExpectedEntity]


class ExpectedCard(BaseModel):
    kind: Literal["idiom", "proverb", "register", "honorific", "cultural"]
    source: str
    literal: str
    meaning: str


class IdiomItem(BaseModel):
    id: str
    src_text: str
    src_roman: str
    gloss: str
    expect_card: bool
    card: ExpectedCard | None = None
