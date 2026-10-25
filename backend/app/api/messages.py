"""In-app Messages (PRODUCT.md, Messages): the user types their news to KIN in the app and it takes the same path as a
text to KIN's number (world/sms.py ingest: self facts only, sensitive reduction, never forwarded, body cleared once
parsed). The caller is the X-KIN-User, so no phone number or link code is involved.

ponytail: no GET /api/me/messages. ingest clears Message.body after the parse (section 7 privacy), so the server has
no message text to list; the app keeps this session's thread itself and "What KIN understood" is the durable record.
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, StringConstraints
from sqlalchemy.orm import Session

from ..db import models as m
from ..db.session import get_session
from ..world.contracts import FactRow
from ..world.sms import SLOW_REPLY, ingest
from .sms import _allow
from .users import current_user
from .world import _row

log = logging.getLogger("kin.api.messages")
router = APIRouter(prefix="/api/me", tags=["messages"])


class MessageIn(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class MessageOut(BaseModel):
    reply: str
    facts: list[FactRow] = []


@router.post("/messages", response_model=MessageOut)
def post_message(body: MessageIn, user: m.User = Depends(current_user), s: Session = Depends(get_session)) -> MessageOut:
    if not _allow(user.id):  # the same per-user budget as SMS: typing in the app is not a way around it
        log.info("in-app message rate limit hit for user %s", user.id)
        return MessageOut(reply=SLOW_REPLY)
    reply, _message_id, facts = ingest(s, user, body.text)
    rows = [s.get(m.Fact, f["id"]) for f in facts]
    return MessageOut(reply=reply, facts=[_row(s, f) for f in rows if f is not None])
