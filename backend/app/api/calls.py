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
    rows = s.scalars(select(m.Utterance).where(m.Utterance.call_id == call_id).order_by(m.Utterance.id)).all()
    people = {p.id: p.slug for p in s.scalars(select(m.Person))}
    return [{"id": u.id, "speaker": people.get(u.speaker_id), "listener": people.get(u.listener_id), "src_text": u.src_text,
             "translation": u.translation, "grounded_spans": u.grounded_spans, "cards": u.cards, "passthrough": u.passthrough,
             "latencies": u.latencies, "created_at": u.created_at.isoformat() if u.created_at else None} for u in rows]
