from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import models as m
from ..db.session import get_session
from ..world.contracts import FeedbackIn, PauseIn, TextIn

log = logging.getLogger("kin.calls")
SWEEP_EVERY_S = 3600

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
        out = _end(call_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    _sweep()
    return out


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


# ---- world call routes (docs/ARCHITECTURE.md 9.2, D17): pause, card feedback, typed text, voice, participants ----------

def _sweep() -> None:
    """Third-party expiry sweep (section 10); a failed sweep never fails the call that triggered it."""
    from ..world.privacy import run_sweep
    try:
        run_sweep()
    except Exception:  # noqa: BLE001
        log.exception("third-party sweep failed")


async def sweep_loop(every_s: float = SWEEP_EVERY_S) -> None:
    """Startup plus hourly sweep; started (and cancelled) by the app lifespan."""
    while True:
        await asyncio.to_thread(_sweep)
        await asyncio.sleep(every_s)


def caller(call_id: int, x_kin_user: str | None = Header(default=None), s: Session = Depends(get_session)) -> int:
    """X-KIN-User -> the caller's person id: 401 without a valid token, 404 for an unknown call, 403 for a non-participant."""
    from ..world.users import user_by_token
    user = user_by_token(s, x_kin_user)
    if user is None:
        raise HTTPException(401, "X-KIN-User token required")
    if s.get(m.Call, call_id) is None:
        raise HTTPException(404, "call not found")
    part = s.scalar(select(m.CallParticipant.id).where(m.CallParticipant.call_id == call_id,
                                                        m.CallParticipant.person_id == user.person_id))
    if part is None:
        raise HTTPException(403, "not a participant of this call")
    return user.person_id


def _live(call_id: int):
    from ..audio.pipeline import registry
    cs = registry.get(call_id)
    if cs is None or cs.world is None:
        raise HTTPException(409, "call is not live")
    return cs


def _side(cs, person_id: int):
    side = cs.sides.get(f"p{person_id}")
    if side is None:
        raise HTTPException(409, "join the call first")
    return side


@router.post("/{call_id}/pause")
async def pause(call_id: int, body: PauseIn, person_id: int = Depends(caller)) -> dict:
    cs = _live(call_id)
    _side(cs, person_id)  # a CallParticipant row outlives the leg: someone who left must not unpause the room
    return await cs.set_paused(person_id, body.paused)


@router.post("/{call_id}/feedback")
async def feedback(call_id: int, body: FeedbackIn, person_id: int = Depends(caller)) -> dict:
    cs = _live(call_id)
    _side(cs, person_id)
    await asyncio.to_thread(cs.world.feedback, f"p{person_id}", body.key, body.action)
    return {"ok": True}


@router.post("/{call_id}/text")
async def typed_text(call_id: int, body: TextIn, person_id: int = Depends(caller)) -> dict:
    cs = _live(call_id)
    _side(cs, person_id)
    await cs.on_text(f"p{person_id}", body.text)  # dropped inside on_text while paused
    return {"ok": True}


class VoiceIn(BaseModel):
    on: bool


@router.post("/{call_id}/voice")
async def voice(call_id: int, body: VoiceIn, person_id: int = Depends(caller)) -> dict:
    """Translated voice for this listener (Amendment 2): off by default, captions always."""
    side = _side(_live(call_id), person_id)
    side.voice_on = body.on
    return {"on": side.voice_on}


@router.get("/{call_id}/participants")
def participants(call_id: int, _me: int = Depends(caller), s: Session = Depends(get_session)) -> list[dict]:
    rows = s.execute(select(m.CallParticipant, m.Person.slug).join(m.Person, m.Person.id == m.CallParticipant.person_id)
                     .where(m.CallParticipant.call_id == call_id).order_by(m.CallParticipant.id)).all()
    return [{"person": slug, "identity": p.identity, "lang": p.lang, "joined_at": p.joined_at.isoformat() if p.joined_at else None,
             "left_at": p.left_at.isoformat() if p.left_at else None} for p, slug in rows]
