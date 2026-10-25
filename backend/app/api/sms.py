"""Twilio SMS webhook (docs/ARCHITECTURE.md section 7). /twilio/ is outside the KIN key gate; the Twilio signature
is checked whenever TWILIO_AUTH_TOKEN is set. Replies are TwiML."""
from __future__ import annotations

import asyncio
import hmac
import logging
import re
import threading
import time
from collections import defaultdict, deque
from xml.sax.saxutils import escape

from fastapi import APIRouter, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..db import models as m
from ..db.session import session_scope
from ..world.sms import FALLBACK, LINKED_REPLY, MAX_BODY, SLOW_REPLY, UNKNOWN_REPLY, ingest
from ..world.users import link_phone, normalize_phone, phone_code
from .twilio import _verify_twilio

log = logging.getLogger("kin.api.sms")
router = APIRouter(tags=["sms"])

RATE_LIMIT = 30
RATE_WINDOW_S = 3600.0
LINK_RE = re.compile(r"\s*KIN\s+([0-9a-f]{6})\s*", re.IGNORECASE)
# ponytail: in-memory, per process; resets on restart. Move to the messages table if KIN runs several workers.
_sent: dict[int | str, deque[float]] = defaultdict(deque)  # user id, or "link:<phone>" for link attempts
_lock = threading.Lock()


def twiml(text: str) -> str:
    return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escape(text)}</Message></Response>'


def _allow(user_id: int | str, now: float | None = None) -> bool:
    now = time.monotonic() if now is None else now
    with _lock:
        q = _sent[user_id]
        while q and now - q[0] >= RATE_WINDOW_S:
            q.popleft()
        if len(q) >= RATE_LIMIT:
            return False
        q.append(now)
        return True


def _stored_reply(sid: str) -> str | None:
    with session_scope() as s:
        msg = s.scalars(select(m.Message).where(m.Message.provider_sid == sid)).first()
        return None if msg is None else (msg.reply or FALLBACK)


def handle(from_number: str, body: str, sid: str | None) -> str:
    """Reply text for one inbound message. Idempotent on MessageSid (Twilio retries)."""
    if sid and (prev := _stored_reply(sid)) is not None:
        return prev
    phone = normalize_phone(from_number)
    try:
        with session_scope() as s:
            user = s.scalars(select(m.User).where(m.User.phone == phone)).first() if phone else None
            if user is None:  # stores nothing, unless this is the "KIN <code>" text that links the number
                return _link(s, phone, body)
            if (mt := LINK_RE.fullmatch(body)) and hmac.compare_digest(phone_code(user), mt.group(1).lower()):
                return LINKED_REPLY  # a Twilio retry of the link text, or the code sent twice: nothing to ingest
            if not _allow(user.id):
                log.info("sms rate limit hit for user %s", user.id)
                return SLOW_REPLY
            return ingest(s, user, body[:MAX_BODY], sid)[0]
    except IntegrityError:  # a concurrent retry with the same MessageSid won the insert
        return (_stored_reply(sid) if sid else None) or FALLBACK


def _link(s, phone: str | None, body: str) -> str:
    """A phone links to an account only by texting that account's code from it, so typing someone else's number
    in the app never redirects their texts."""
    match = LINK_RE.fullmatch(body) if phone else None
    if match is None:
        return UNKNOWN_REPLY
    if not _allow(f"link:{phone}"):  # 24-bit codes: cap guesses per number
        log.info("sms link rate limit hit")
        return SLOW_REPLY
    user = link_phone(s, phone, match.group(1))
    if user is None:
        log.info("sms link code matched no unlinked user")
        return UNKNOWN_REPLY
    log.info("sms linked a phone to user %s", user.id)
    return LINKED_REPLY


@router.post("/twilio/sms")
async def inbound_sms(request: Request) -> Response:
    form = {k: v for k, v in (await request.form()).items()}
    _verify_twilio(request, form)
    reply = await asyncio.to_thread(handle, str(form.get("From", "")), str(form.get("Body", "")),
                                    str(form.get("MessageSid") or "") or None)
    return Response(content=twiml(reply), media_type="application/xml")
