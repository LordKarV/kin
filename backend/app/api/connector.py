"""Read-only, key-authenticated endpoints for the Muse custom connector (Phase 6) + the connector brief."""
from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import models as m
from ..db.session import get_session
from ..memory.service import search
from .glossary import glossary as _glossary
from .graph import family_graph as _family_graph

router = APIRouter(tags=["connector"])


def require_key(x_kin_key: str | None = Header(default=None), authorization: str | None = Header(default=None)) -> None:
    key = get_settings().kin_api_key
    given = x_kin_key or (authorization.split(" ", 1)[1] if authorization and authorization.lower().startswith("bearer ") else None)
    if not given or not hmac.compare_digest(given, key):
        raise HTTPException(401, "missing or invalid KIN API key (X-KIN-Key or Authorization: Bearer)")


@router.get("/api/v1/family/graph", dependencies=[Depends(require_key)])
def v1_graph(s: Session = Depends(get_session)) -> dict:
    return _family_graph(None, s)


@router.get("/api/v1/calls/recent", dependencies=[Depends(require_key)])
def v1_recent(limit: int = 5, s: Session = Depends(get_session)) -> list[dict]:
    fid = get_settings().demo_family_id
    calls = s.scalars(select(m.Call).where(m.Call.family_id == fid).order_by(m.Call.id.desc()).limit(limit)).all()
    out = []
    for c in calls:
        cs = s.scalar(select(m.CallSummary).where(m.CallSummary.call_id == c.id))
        n = s.scalar(select(m.Utterance.id).where(m.Utterance.call_id == c.id).limit(1))
        out.append({"call_id": c.id, "started_at": c.started_at.isoformat() if c.started_at else None, "ended_at": c.ended_at.isoformat() if c.ended_at else None,
                    "summary": cs.summary if cs else "", "approved": bool(cs and cs.approved),
                    "topics": [t["topic"] for t in (cs.extracted or {}).get("topics", [])] if cs else [], "has_utterances": n is not None})
    return out


@router.get("/api/v1/memory/search", dependencies=[Depends(require_key)])
def v1_search(q: str, limit: int = 8) -> dict:
    return {"query": q, "results": search(q, get_settings().demo_family_id, limit)}


@router.get("/api/v1/glossary", dependencies=[Depends(require_key)])
def v1_glossary(limit: int = 50, s: Session = Depends(get_session)) -> list[dict]:
    return _glossary(None, limit, s)


BRIEF = """# KIN — connector brief for Muse

KIN is a family-specific interpreter for calls between grandchildren and grandparents. This connector lets Muse
answer questions about **one family's** calls: who was mentioned, what was said, what a word means in this family.

## Base URL
`{base}`

## Authentication
Every `/api/v1/*` request needs the family's key, either header `X-KIN-Key: <key>` or `Authorization: Bearer <key>`.
The key is **read-only** and can be revoked by the family at any time. Never echo the key back to the user.

## Endpoints (all GET, JSON)
- `/api/v1/family/graph` — people (with how the grandchild should hear each one, e.g. "your uncle Ravi mama (Mom's younger brother)"), kin-term edges, dishes/places/events with the family's own meaning.
- `/api/v1/calls/recent?limit=5` — recent calls with their approved summaries and topic words.
- `/api/v1/memory/search?q=<text>` — fuzzy search over what was actually said (source + translation) and call summaries. Returns `results[].text`, `translation`, `speaker`, `when`, `score`.
- `/api/v1/glossary` — every pragmatics card ever shown (idioms, proverbs, register), with literal and meaning.

## Safety rules
- Read-only. There is no write endpoint; do not try to create or modify anything.
- Health, money and conflict topics appear only as a topic word unless the grandchild chose "remember this" (then `remembered_topics` lists them). Do not speculate beyond what is returned.
- This is one family's private memory. Answer only the family member who connected it; do not summarize it to anyone else.

## Example prompts
- "What did Ammamma say about her knee last week?" → `/api/v1/memory/search?q=knee`, then answer with the date and the quote.
- "What does *gongura* / *rasam* mean in my family?" → `/api/v1/family/graph` → `things[]` note for that dish.
- "Who is Ravi periyappa?" → `/api/v1/family/graph` → the `render` field for `p_ravi_periyappa`.
- "What did we talk about on the last call?" → `/api/v1/calls/recent?limit=1` → `summary`.
"""


@router.get("/connectors/muse.md", response_class=PlainTextResponse)
def brief(request: Request) -> str:
    base = str(request.base_url).rstrip("/")
    return BRIEF.format(base=base)
