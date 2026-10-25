"""Structured output schema for grounded translation. Strict-mode friendly: no defaults, closed objects."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, create_model, model_validator

from ..world.contracts import NewPerson  # noqa: F401  (one definition)


class GroundedSpan(BaseModel):
    source: str      # surface form in the source utterance
    rendered: str    # how it was rendered for the listener, e.g. "your uncle Ravi <kin term> (Mom's younger brother)"
    node_id: str     # family-graph slug, e.g. p_ravi_7


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
    passthrough_kept: list[str]   # tokens left untranslated
    confidence: float


# Call A (hot path): what is spoken plus its grounding. The API emits strict-schema keys in ALPHABETICAL order
# (VERIFIED live 2026-10-24), so `a_translation` is named to come first. Comments, not docstrings: a docstring lands in the schema.
class SpeechOut(BaseModel):
    a_translation: str
    confidence: float
    grounded_spans: list[GroundedSpan]
    passthrough_kept: list[str]

    @model_validator(mode="before")
    @classmethod
    def _accept_single_call_shape(cls, v):
        # Known limit: accepts the old one-call reply ({"translation": ...}) so existing mocked providers keep working
        if isinstance(v, dict) and "a_translation" not in v and "translation" in v:
            return {**v, "a_translation": v["translation"]}
        return v


# Call B (enrichment, off the hot path): pragmatics cards, plus unresolved names on world calls.
# new_people defaults to [] so old replies and mocks without it still validate.
class CardsOut(BaseModel):
    pragmatics_cards: list[PragmaticsCard]
    new_people: list[NewPerson] = []

# Legacy call B (roster None): the pre-world schema under the same name, so its strict response_format stays
# byte-identical (to_strict_schema would make new_people required and ask the model for it).
LegacyCardsOut = create_model("CardsOut", pragmatics_cards=(list[PragmaticsCard], ...))
