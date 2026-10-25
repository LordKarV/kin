"""Join a KIN call room (LiveKit). Each join mints a room token whose metadata says who this person is, and makes sure
the KIN agent is in the room.

The body is `{call_id?, invite?}` with header X-KIN-User. Joining an existing call needs the call's invite code
(returned by every join) or an existing seat."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import secrets
from fastapi import APIRouter, Body, Depends, Header, HTTPException
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import models as m
from ..db.session import get_session
from ..world import clock
from ..world.users import user_by_token
from ..rtc.agent import agents, livekit_creds, mint_token, room_name

router = APIRouter(prefix="/api/rtc", tags=["call app"])


class WorldJoinIn(BaseModel):
    call_id: int | None = None  # None: start a new world call; set: join that call
    invite: str | None = None  # the code from the invite link; not needed to rejoin a call I already sat in


# Known limit: per-process secret, so a restart invalidates outstanding invites (people already in a call rejoin through
# their CallParticipant row). Multi-worker deploys need a shared secret (settings) instead.
_INVITE_SECRET = secrets.token_bytes(32)


def invite_code(call_id: int) -> str:
    return hmac.new(_INVITE_SECRET, f"invite:{call_id}".encode(), hashlib.sha256).hexdigest()[:16]


def _parse(model: type[BaseModel], raw: dict) -> BaseModel:
    try:
        return model.model_validate(raw)
    except ValidationError as e:
        raise RequestValidationError(e.errors()) from e


@router.post("/join")
async def join(raw: dict = Body(...), x_kin_user: str | None = Header(None),
               s: Session = Depends(get_session)) -> dict:
    # Sync DB work runs off the loop; agents.ensure needs the loop, so it stays here.
    out = await asyncio.to_thread(_world_join, _parse(WorldJoinIn, raw), x_kin_user, s)
    agents.ensure(out["call_id"])
    return out


def _world_join(body: WorldJoinIn, token: str | None, s: Session) -> dict:
    user = user_by_token(s, token)
    if user is None:
        raise HTTPException(401, "X-KIN-User token required")
    me = s.get(m.Person, user.person_id)
    if body.call_id is None:
        call = m.Call(family_id=me.family_id, transport="livekit", mode="world")
        s.add(call)
        s.flush()
    else:
        call = s.get(m.Call, body.call_id)
        if call is None or call.mode != "world" or call.family_id != me.family_id or call.ended_at is not None:
            raise HTTPException(404, "unknown call")  # an ended call (declined, cancelled, missed) is not rejoinable
    identity = f"p{me.id}"
    row = s.scalars(select(m.CallParticipant).where(m.CallParticipant.call_id == call.id,
                                                    m.CallParticipant.person_id == me.id)).first()
    # bytes: compare_digest raises TypeError on a str with non-ASCII, which would turn a junk code into a 500
    invited = hmac.compare_digest((body.invite or "").encode(), invite_code(call.id).encode())
    if body.call_id is not None and row is None and not invited:
        raise HTTPException(404, "unknown call")  # same answer as a missing call: ids are sequential
    if row is None:
        s.add(m.CallParticipant(call_id=call.id, person_id=me.id, identity=identity, lang=user.lang,
                                joined_at=clock.now()))
    else:  # rejoin: same identity, fresh join time
        row.lang, row.joined_at, row.left_at = user.lang, clock.now(), None
    if me.id not in (call.participants or []):
        call.participants = [*(call.participants or []), me.id]
    s.commit()
    others = s.execute(select(m.CallParticipant, m.Person).join(m.Person, m.Person.id == m.CallParticipant.person_id)
                       .where(m.CallParticipant.call_id == call.id, m.CallParticipant.person_id != me.id,
                              m.CallParticipant.left_at.is_(None))).all()
    room = room_name(call.id)
    meta = {"person": me.slug, "person_id": me.id, "lang": user.lang, "name": me.display_name}
    tok = mint_token(room, identity=identity, name=me.display_name, metadata=meta)
    url, _, _ = livekit_creds()
    return {"call_id": call.id, "room": room, "token": tok, "url": url, "identity": identity, "person": me.slug,
            "name": me.display_name, "lang": user.lang, "invite": invite_code(call.id),
            "participants": [{"identity": cp.identity, "person": p.slug, "name": p.display_name, "lang": cp.lang}
                             for cp, p in others]}
