from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import models as m
from ..db.session import get_session

router = APIRouter(prefix="/api/calls", tags=["calls"])


class NewCall(BaseModel):
    family_id: int | None = None
    transport: str = "websocket"


@router.post("")
def create_call(body: NewCall, s: Session = Depends(get_session)) -> dict:
    fid = body.family_id or get_settings().demo_family_id
    if s.get(m.Family, fid) is None:
        raise HTTPException(404, "family not found")
    c = m.Call(family_id=fid, transport=body.transport)
    s.add(c); s.flush()
    return {"id": c.id, "family_id": fid}


@router.get("")
def list_calls(limit: int = 20, s: Session = Depends(get_session)) -> list[dict]:
    rows = s.scalars(select(m.Call).order_by(m.Call.id.desc()).limit(limit)).all()
    return [{"id": c.id, "family_id": c.family_id, "started_at": c.started_at.isoformat() if c.started_at else None,
             "ended_at": c.ended_at.isoformat() if c.ended_at else None, "transport": c.transport} for c in rows]


@router.get("/{call_id}/utterances")
def utterances(call_id: int, s: Session = Depends(get_session)) -> list[dict]:
    from ..memory.service import remembered_by_call, withheld

    rows = s.scalars(select(m.Utterance).where(m.Utterance.call_id == call_id).order_by(m.Utterance.id)).all()
    people = {p.id: p.slug for p in s.scalars(select(m.Person))}
    rem = remembered_by_call(s, [call_id])
    out = []
    for u in rows:
        hide = withheld(u, rem)
        note = f"[{u.sensitive_topic} topic withheld; tap 'remember this' after the call to keep it]"
        out.append({"id": u.id, "speaker": people.get(u.speaker_id), "listener": people.get(u.listener_id),
                    "src_text": note if hide else u.src_text, "translation": "" if hide else u.translation,
                    "grounded_spans": [] if hide else u.grounded_spans, "cards": u.cards, "passthrough": u.passthrough,
                    "sensitive_topic": u.sensitive_topic, "latencies": u.latencies, "created_at": u.created_at.isoformat() if u.created_at else None})
    return out


class Approve(BaseModel):
    remember_topics: list[str] = []


@router.post("/{call_id}/end")
def end_call(call_id: int) -> dict:
    """Mark the call ended; summarize and extract (Phase 6). Sensitive topics are reduced to a topic word."""
    from ..memory.service import end_call as _end
    try:
        return _end(call_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/{call_id}/approve")
def approve_call(call_id: int, body: Approve) -> dict:
    """Grandchild approves: non-sensitive people/dishes/places/events are added to the graph; listed topics are remembered."""
    from ..memory.service import approve_call as _approve
    try:
        return _approve(call_id, body.remember_topics)
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.get("/{call_id}/summary")
def get_summary(call_id: int, s: Session = Depends(get_session)) -> dict:
    cs = s.scalar(select(m.CallSummary).where(m.CallSummary.call_id == call_id))
    if cs is None:
        raise HTTPException(404, "no summary")
    return {"call_id": call_id, "summary": cs.summary, "extracted": cs.extracted, "approved": cs.approved}
