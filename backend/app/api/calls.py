from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..db import models as m
from ..db.session import get_session
from ..world import clock
from ..world.contracts import FeedbackIn, PauseIn, TextIn
from . import events
from .users import contacts, current_user

log = logging.getLogger("kin.calls")
SWEEP_EVERY_S = 3600

router = APIRouter(prefix="/api/calls", tags=["calls"])


# ---- call routes: pause, card feedback, typed text, voice, participants ----------------------------------------

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


# ---- ringing (in-app calling; no push, so the callee rings only while the app is open) -------------------------------

RING_TIMEOUT_S = 45


@dataclass
class Ring:
    call_id: int
    caller_id: int
    callee_id: int
    incoming: dict  # the call.incoming event, replayed when the callee's event socket (re)connects
    timer: asyncio.Task | None = None


# ponytail: in-process, like the event registry (one worker); a restart drops rings in flight, both sides time out.
_rings: dict[int, Ring] = {}
# How each recent ring ended: call_id -> (monotonic expiry, who was told, the event). Kept RING_TIMEOUT_S so a socket
# that was away at that moment (app in the background, a reconnect) still hears "answered" or "cancelled".
_done: dict[int, tuple[float, list[int], dict]] = {}


def pending_rings(person_id: int) -> list[dict]:
    """What a (re)connecting event socket missed: rings still ringing me, and how my recent rings ended."""
    now = time.monotonic()
    for cid in [cid for cid, (until, _, _) in _done.items() if until < now]:
        _done.pop(cid, None)
    return ([r.incoming for r in _rings.values() if r.callee_id == person_id]
            + [msg for _, to, msg in _done.values() if person_id in to])


class RingIn(BaseModel):
    to: str  # the callee's person slug
    video: bool = True


def _create_ring(s: Session, user: m.User, body: RingIn) -> tuple[int, int, dict]:
    """A world call with seats for both people, so the callee joins with no invite code. Callee must be one of my
    contacts (GET /api/contacts: a shared call, tie, edge or accepted connect request); anyone else answers 404 like an unknown person."""
    if body.to not in {c.person for c in contacts(user=user, s=s)}:
        raise HTTPException(404, "unknown person")
    me = s.get(m.Person, user.person_id)
    callee = s.scalar(select(m.Person).where(m.Person.slug == body.to, m.Person.family_id == me.family_id))
    callee_user = s.scalar(select(m.User).where(m.User.person_id == callee.id)) if callee else None
    if callee_user is None:
        raise HTTPException(404, "unknown person")
    now = clock.now()
    call = m.Call(family_id=me.family_id, transport="livekit", mode="world", participants=[me.id, callee.id])
    s.add(call)
    s.flush()
    # left_at = joined_at: a held seat, not someone in the room; /api/rtc/join clears left_at when they really join.
    for pid, lang in ((me.id, user.lang), (callee.id, callee_user.lang)):
        s.add(m.CallParticipant(call_id=call.id, person_id=pid, identity=f"p{pid}", lang=lang, joined_at=now, left_at=now))
    s.commit()
    incoming = {"type": "call.incoming", "call_id": call.id, "from": {"slug": me.slug, "name": me.display_name},
                "video": body.video}
    return call.id, callee.id, incoming


def _end(call_id: int) -> None:
    from ..db.session import session_scope
    with session_scope() as s:
        call = s.get(m.Call, call_id)
        if call is not None and call.ended_at is None:
            call.ended_at = clock.now()
        # ponytail: drop the held seats so neither person can POST /api/rtc/join a ring that ended (neither holds an
        # invite code). The real guard is an ended_at check in rtc._world_join, which this task does not own.
        s.execute(delete(m.CallParticipant).where(m.CallParticipant.call_id == call_id,
                                                  m.CallParticipant.left_at.is_not(None)))


async def _finish(ring: Ring, kind: str, to: list[int], end: bool) -> None:
    """Close a ring: stop its timer, tell `to`, and end the call when nobody will join it."""
    _rings.pop(ring.call_id, None)
    if ring.timer is not None and ring.timer is not asyncio.current_task():
        ring.timer.cancel()
    msg = {"type": kind, "call_id": ring.call_id}
    _done[ring.call_id] = (time.monotonic() + RING_TIMEOUT_S, to, msg)
    if end:
        await asyncio.to_thread(_end, ring.call_id)
    for pid in to:
        await events.send_to(pid, msg)


async def drop_person(person_id: int) -> None:
    """After DELETE /api/me: end the person's rings (the other side hears cancelled or missed), forget how their rings
    ended, and close their event sockets, so nothing of theirs stays in memory and a reused person id hears nothing."""
    for r in [r for r in _rings.values() if person_id in (r.caller_id, r.callee_id)]:
        theirs = r.caller_id == person_id
        await _finish(r, "call.cancelled" if theirs else "call.missed", [r.callee_id if theirs else r.caller_id], end=True)
    for cid in [cid for cid, (_, to, _) in _done.items() if person_id in to]:
        _done.pop(cid, None)
    await events.drop(person_id)


async def _miss_after(call_id: int, delay_s: float) -> None:
    await asyncio.sleep(delay_s)
    ring = _rings.get(call_id)
    if ring is not None:
        await _finish(ring, "call.missed", [ring.caller_id, ring.callee_id], end=True)


@router.post("/ring")
async def ring(body: RingIn, user: m.User = Depends(current_user), s: Session = Depends(get_session)) -> dict:
    call_id, callee_id, incoming = await asyncio.to_thread(_create_ring, s, user, body)
    r = Ring(call_id=call_id, caller_id=user.person_id, callee_id=callee_id, incoming=incoming)
    _rings[call_id] = r
    r.timer = asyncio.create_task(_miss_after(call_id, RING_TIMEOUT_S))
    delivered = await events.send_to(callee_id, incoming)
    return {"call_id": call_id, "delivered": delivered}


def _ringing(call_id: int, person_id: int, side: str) -> Ring:
    """The live ring for this call, when `person_id` is its `side` ("caller" or "callee")."""
    r = _rings.get(call_id)
    if r is None:
        raise HTTPException(409, "this call is not ringing")
    if (r.caller_id if side == "caller" else r.callee_id) != person_id:
        raise HTTPException(403, f"only the {side} can do that")
    return r


@router.post("/{call_id}/answer")
async def answer(call_id: int, person_id: int = Depends(caller)) -> dict:
    r = _ringing(call_id, person_id, "callee")
    await _finish(r, "call.answered", [r.caller_id], end=False)  # both now join with POST /api/rtc/join {call_id}
    return {"ok": True}


@router.post("/{call_id}/decline")
async def decline(call_id: int, person_id: int = Depends(caller)) -> dict:
    r = _ringing(call_id, person_id, "callee")
    await _finish(r, "call.declined", [r.caller_id], end=True)
    return {"ok": True}


@router.post("/{call_id}/cancel")
async def cancel(call_id: int, person_id: int = Depends(caller)) -> dict:
    r = _ringing(call_id, person_id, "caller")
    await _finish(r, "call.cancelled", [r.callee_id], end=True)
    return {"ok": True}
