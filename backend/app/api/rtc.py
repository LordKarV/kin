"""Join a KIN call room (LiveKit). The grandchild starts a call and shares the link; the grandparent opens it.
Each join mints a room token whose metadata says who this person is, and makes sure the KIN agent is in the room."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import models as m
from ..db.session import get_session
from ..mt.translate import get_translator
from ..rtc.agent import agents, livekit_creds, mint_token, room_name

router = APIRouter(prefix="/api/rtc", tags=["call app"])


class JoinIn(BaseModel):
    family_id: int
    role: Literal["grandchild", "grandparent"]
    call_id: int | None = None  # None: start a new call (grandchild); set: join the shared link (grandparent)


@router.post("/join")
async def join(body: JoinIn, s: Session = Depends(get_session)) -> dict:
    if s.get(m.Family, body.family_id) is None:
        raise HTTPException(404, "no such family: set one up first")
    if body.call_id is None:
        call = m.Call(family_id=body.family_id, transport="livekit")
        s.add(call)
        s.flush()
        call_id = call.id
        s.commit()
    else:
        call = s.get(m.Call, body.call_id)
        if call is None or call.family_id != body.family_id:
            raise HTTPException(404, "unknown call for this family")
        call_id = call.id
    g = get_translator(body.family_id).g
    person = g.learner_slug() if body.role == "grandchild" else g.elder_slug()
    node = g.by_slug.get(person)
    room = room_name(call_id)
    token = mint_token(room, identity=f"{body.role}-{call_id}", name=node.name if node else body.role,
                       metadata={"role": body.role, "person": person})
    agents.ensure(call_id)
    url, _, _ = livekit_creds()
    return {"call_id": call_id, "room": room, "token": token, "url": url, "role": body.role, "person": person,
            "name": node.name if node else "", "heritage_lang": g.heritage_lang}
