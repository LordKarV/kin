"""Build the family as you go (nothing pre-seeded): two-minute setup, relation pickers, and the "Who's X?" card that
adds a relative mid-call. Every write refreshes the live calls of that family, so the next sentence is grounded."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..audio.pipeline import registry
from ..db.session import get_session
from ..graph.builder import add_relative, create_family, relations, suggest
from ..graph.kin_tables import available_codes
from ..mt.translate import get_translator, reset_translator_cache
from .calls import legacy_family

router = APIRouter(prefix="/api/family", tags=["family"])


class SetupIn(BaseModel):
    language: str = Field(min_length=2, max_length=8)
    your_name: str = Field(min_length=1, max_length=120)
    their_name: str = Field(min_length=1, max_length=120)
    you_call_them: str = Field(default="", max_length=64)
    relation: str = Field(default="mother.mother", max_length=80)


class RelativeIn(BaseModel):
    family_id: int
    path: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    you_call_them: str = Field(default="", max_length=64)


def _refresh(family_id: int) -> None:
    """New people/edges must reach calls already in progress (their translator holds the old graph)."""
    reset_translator_cache()
    fresh = get_translator(family_id)
    for cs in registry.active():
        if cs.family_id == family_id:
            cs.translator = fresh


def _render(family_id: int, slug: str) -> str:
    g = get_translator(family_id).g
    learner = g.by_slug[g.learner_slug()].id
    return g.render(learner, g.by_slug[slug].id)


@router.post("/setup")
def setup(body: SetupIn, s: Session = Depends(get_session)) -> dict:
    if body.language not in available_codes():
        raise HTTPException(400, f"unsupported language {body.language!r}; see GET /api/languages")
    try:
        fam, learner, elder = create_family(s, body.language, body.your_name.strip(), body.their_name.strip(),
                                            body.you_call_them.strip(), body.relation)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    s.commit()
    _refresh(fam.id)
    return {"family_id": fam.id, "learner": learner.slug, "elder": elder.slug, "render": _render(fam.id, elder.slug)}


@router.post("/relative")
def relative(body: RelativeIn, s: Session = Depends(get_session)) -> dict:
    legacy_family(s, body.family_id)
    try:
        p = add_relative(s, body.family_id, body.path, body.name.strip(), body.you_call_them.strip())
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    s.commit()
    _refresh(body.family_id)
    return {"id": p.slug, "name": p.display_name, "render": _render(body.family_id, p.slug)}


@router.get("/relations")
def relation_choices() -> list[dict]:
    return relations()


@router.get("/suggest")
def suggest_relations(term: str, family_id: int, s: Session = Depends(get_session)) -> list[dict]:
    """What a kin word the grandparent just used can mean, in this family's language (from its kin table)."""
    return suggest(term, legacy_family(s, family_id).heritage_lang)
