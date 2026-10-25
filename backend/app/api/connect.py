"""Connect without a link: every user has a KIN handle (arjun-4821); a request to a handle, once accepted, makes the
two users contacts (GET /api/contacts, POST /api/calls/ring). No world Tie is written: a connection is not a fact."""
from __future__ import annotations

import asyncio
import re
import secrets
import unicodedata
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import ForeignKey, String, UniqueConstraint, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..db import models as m
from ..db.session import get_session
from . import events
from .users import current_user

router = APIRouter(prefix="/api", tags=["connect"])
HANDLE_TRIES = 20


# ponytail: new tables, not columns, because the schema has no migrations (create_all builds these on startup).
class UserHandle(m.Base):
    __tablename__ = "user_handles"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    handle: Mapped[str] = mapped_column(String(40), unique=True)


class ConnectRequest(m.Base):
    __tablename__ = "connect_requests"
    __table_args__ = (UniqueConstraint("from_user", "to_user"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    from_user: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    to_user: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending | accepted | declined
    created_at: Mapped[datetime] = mapped_column(m.UTCDateTime(), default=m.now)


class ConnectIn(BaseModel):
    handle: str = Field(min_length=1, max_length=60)


def connected_person_ids(s: Session, user_id: int) -> set[int]:
    """Person ids of the users I have an accepted request with, either direction (users.contacts)."""
    rows = s.execute(select(ConnectRequest.from_user, ConnectRequest.to_user).where(
        ConnectRequest.status == "accepted", or_(ConnectRequest.from_user == user_id, ConnectRequest.to_user == user_id)))
    others = {b if a == user_id else a for a, b in rows}
    return set(s.scalars(select(m.User.person_id).where(m.User.id.in_(others)))) if others else set()


def _who(s: Session, user_id: int) -> dict:
    p = s.get(m.Person, s.get(m.User, user_id).person_id)
    return {"slug": p.slug, "name": p.display_name}


def _base(name: str) -> str:
    first = (name.split() or [""])[0]
    ascii_ = unicodedata.normalize("NFKD", first).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", ascii_)[:20] or "kin"


@router.get("/me/handle")
def my_handle(user: m.User = Depends(current_user), s: Session = Depends(get_session)) -> dict:
    """My handle, made on first ask: first name + 4 digits, a new draw on collision."""
    have = s.scalar(select(UserHandle.handle).where(UserHandle.user_id == user.id))
    if have:
        return {"handle": have}
    base = _base(s.get(m.Person, user.person_id).display_name)
    for _ in range(HANDLE_TRIES):
        cand = f"{base}-{secrets.randbelow(10000):04d}"
        if s.scalar(select(UserHandle.id).where(UserHandle.handle == cand)) is not None:
            continue
        try:
            s.add(UserHandle(user_id=user.id, handle=cand))
            s.commit()
            return {"handle": cand}
        except IntegrityError:  # a concurrent first ask (mine or theirs) won the row
            s.rollback()
            have = s.scalar(select(UserHandle.handle).where(UserHandle.user_id == user.id))
            if have:
                return {"handle": have}
    raise HTTPException(503, "could not pick a handle; try again")


def _request(s: Session, me: m.User, handle: str) -> tuple[dict, int | None, dict | None]:
    """(response, person id to notify, event). Unknown handle and yourself fail before anything is written."""
    target_id = s.scalar(select(UserHandle.user_id).where(UserHandle.handle == handle.strip().lstrip("@").lower()))
    if target_id is None:
        raise HTTPException(404, "no one with that handle")
    if target_id == me.id:
        raise HTTPException(422, "that is your own handle")
    theirs = s.scalar(select(ConnectRequest).where(ConnectRequest.from_user == target_id, ConnectRequest.to_user == me.id))
    mine = s.scalar(select(ConnectRequest).where(ConnectRequest.from_user == me.id, ConnectRequest.to_user == target_id))
    them = _who(s, target_id)
    target_person = s.get(m.User, target_id).person_id
    if any(r is not None and r.status == "accepted" for r in (theirs, mine)):
        return {"status": "accepted", "user": them}, None, None
    if theirs is not None and theirs.status == "pending":  # they asked me first: sending back is accepting
        theirs.status = "accepted"
        s.commit()
        return {"status": "accepted", "user": them}, target_person, {"type": "contact.accepted", "user": _who(s, me.id)}
    if mine is not None:  # idempotent; a declined request stays declined and looks pending (no re-notify)
        return {"status": "pending", "user": them}, None, None
    s.add(ConnectRequest(from_user=me.id, to_user=target_id))
    s.commit()
    return {"status": "pending", "user": them}, target_person, {"type": "contact.request", "from": _who(s, me.id)}


@router.post("/connect")
async def send_request(body: ConnectIn, user: m.User = Depends(current_user), s: Session = Depends(get_session)) -> dict:
    out, notify, msg = await asyncio.to_thread(_request, s, user, body.handle)
    if notify is not None:
        await events.send_to(notify, msg)
    return out


@router.get("/connect/requests")
def incoming(user: m.User = Depends(current_user), s: Session = Depends(get_session)) -> list[dict]:
    rows = s.scalars(select(ConnectRequest).where(ConnectRequest.to_user == user.id, ConnectRequest.status == "pending")
                     .order_by(ConnectRequest.created_at.desc()))
    return [{"from": _who(s, r.from_user), "created_at": r.created_at.isoformat()} for r in rows]


def _answer(s: Session, me: m.User, slug: str, status: str) -> tuple[int, dict]:
    """Mark the pending request from `slug` to me. Only its target can: anyone else gets 404, like no request."""
    req = s.scalar(select(ConnectRequest).join(m.User, m.User.id == ConnectRequest.from_user)
                   .join(m.Person, m.Person.id == m.User.person_id)
                   .where(m.Person.slug == slug, ConnectRequest.to_user == me.id, ConnectRequest.status == "pending"))
    if req is None:
        raise HTTPException(404, "no pending request from that person")
    req.status = status
    s.commit()
    return s.get(m.User, req.from_user).person_id, _who(s, me.id)


@router.post("/connect/{slug}/accept")
async def accept(slug: str, user: m.User = Depends(current_user), s: Session = Depends(get_session)) -> dict:
    requester, me = await asyncio.to_thread(_answer, s, user, slug, "accepted")
    await events.send_to(requester, {"type": "contact.accepted", "user": me})
    return {"status": "accepted"}


@router.post("/connect/{slug}/decline")
def decline(slug: str, user: m.User = Depends(current_user), s: Session = Depends(get_session)) -> dict:
    _answer(s, user, slug, "declined")
    return {"status": "declined"}
