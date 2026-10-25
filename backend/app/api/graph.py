"""Family graph for the UI and the Muse connector (read-only)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import models as m
from ..db.session import get_session
from ..mt.translate import get_translator

router = APIRouter(prefix="/api/family", tags=["family"])


def _generation(g, ego: int, pid: int) -> int:
    """Generation offset relative to ego: parents -1, grandparents -2, children +1, cousins/siblings 0."""
    path = g.shortest_path(ego, pid) or []
    gen = 0
    for step in path:
        if step in ("mother", "father"):
            gen -= 1
        elif step in ("son", "daughter"):
            gen += 1
    return gen


@router.get("/all")
def families(s: Session = Depends(get_session)) -> list[dict]:
    """Every family with its heritage language (any of the 25 in app/languages.py), for family pickers."""
    from ..graph.kin_tables import MUSE_LANGUAGES
    return [{"id": f.id, "name": f.name, "heritage_lang": f.heritage_lang, "language": MUSE_LANGUAGES.get(f.heritage_lang, f.heritage_lang)}
            for f in s.scalars(select(m.Family).order_by(m.Family.id))]


@router.get("/graph")
def family_graph(family_id: int | None = None, s: Session = Depends(get_session)) -> dict:
    fid = family_id or get_settings().demo_family_id
    if s.get(m.Family, fid) is None:
        raise HTTPException(404, "no family yet: set one up with POST /api/family/setup")
    g = get_translator(fid).g
    if not g.people:
        raise HTTPException(404, "family has no people yet")
    learner = next((p for p in g.people.values() if p.is_learner), None) or next(iter(g.people.values()))
    people = []
    for pid, p in g.people.items():
        people.append({"id": p.slug, "name": p.name, "lang_name": p.lang_name, "gender": p.gender, "birth_year": p.birth_year,
                       "render": g.render(learner.id, pid), "aliases": [a for a, _l, k in p.aliases if k in ("nickname", "address")],
                       "notes": p.notes, "deceased": p.is_deceased, "is_learner": p.is_learner, "generation": _generation(g, learner.id, pid)})
    slug = {pid: p.slug for pid, p in g.people.items()}
    edges = [{"src": slug[e.src_person], "dst": slug[e.dst_person], "relation": e.relation, "lang_term": e.lang_term}
             for e in s.scalars(select(m.Edge).where(m.Edge.family_id == fid))]
    things = [{"id": t.slug, "kind": t.kind, "name": t.name, "lang_name": t.lang_name, "aliases": t.aliases, "note": t.note} for t in g.things]
    return {"family_id": fid, "heritage_lang": g.heritage_lang, "learner": learner.slug, "people": people, "edges": edges, "things": things}
