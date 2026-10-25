"""In-app Messages: the user types their news to KIN in the app (world/sms.py ingest: self facts only, sensitive
reduction, never forwarded, body cleared once parsed). The caller is the X-KIN-User.

Known limit: no GET /api/me/messages. ingest clears Message.body after the parse (privacy), so the server has no
message text to list; the app keeps this session's thread itself and "What KIN understood" is the durable record.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, StringConstraints
from sqlalchemy.orm import Session

from ..db import models as m
from ..db.session import get_session
from ..world.contracts import FactRow
from ..world.sms import SLOW_REPLY, ingest
from .users import current_user
from .world import _row

RATE_LIMIT = 30
RATE_WINDOW_S = 3600.0
# Known limit: in-memory, per process; resets on restart. Move to the messages table if KIN runs several workers.
_sent: dict[int, deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def _allow(user_id: int, now: float | None = None) -> bool:
    now = time.monotonic() if now is None else now
    with _lock:
        q = _sent[user_id]
        while q and now - q[0] >= RATE_WINDOW_S:
            q.popleft()
        if len(q) >= RATE_LIMIT:
            return False
        q.append(now)
        return True

log = logging.getLogger("kin.api.messages")
router = APIRouter(prefix="/api/me", tags=["messages"])


class MessageIn(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class MessageOut(BaseModel):
    reply: str
    facts: list[FactRow] = []


@router.post("/messages", response_model=MessageOut)
def post_message(body: MessageIn, user: m.User = Depends(current_user), s: Session = Depends(get_session)) -> MessageOut:
    if not _allow(user.id):  # a per-user budget on what KIN parses
        log.info("in-app message rate limit hit for user %s", user.id)
        return MessageOut(reply=SLOW_REPLY)
    reply, _message_id, facts = ingest(s, user, body.text)
    rows = [s.get(m.Fact, f["id"]) for f in facts]
    return MessageOut(reply=reply, facts=[_row(s, f) for f in rows if f is not None])
