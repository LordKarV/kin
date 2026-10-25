"""Tap a word in the caption (docs/ARCHITECTURE.md Amendment 5). The response goes to the caller only."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import models as m
from ..db.session import get_session
from .users import current_user

router = APIRouter(prefix="/api/calls", tags=["explain"])


class ExplainIn(BaseModel):
    text: str = Field(min_length=1, max_length=200)
    utterance_id: int | None = None


def _listener(call_id: int, user: m.User = Depends(current_user), s: Session = Depends(get_session)) -> int:
    """Like calls.caller, but a caller outside the call gets 404 (Amendment 5): it does not learn the call exists."""
    part = s.scalar(select(m.CallParticipant.id).where(m.CallParticipant.call_id == call_id,
                                                        m.CallParticipant.person_id == user.person_id))
    if s.get(m.Call, call_id) is None or part is None:
        raise HTTPException(404, "call not found")
    return user.person_id


@router.post("/{call_id}/explain")
async def explain(call_id: int, body: ExplainIn, person_id: int = Depends(_listener)) -> dict:
    from ..audio.pipeline import registry
    from ..world.explain import explain as run  # lazy: world.live pulls heavy deps

    if not body.text.strip():
        raise HTTPException(422, "text is empty")
    cs = registry.get(call_id)
    if cs is None or cs.world is None:
        raise HTTPException(404, "call is not live")
    try:
        items = await asyncio.to_thread(run, cs.world, call_id, person_id, body.text, body.utterance_id)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    return {"items": items}
