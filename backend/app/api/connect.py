"""Connect without a link: every user has a KIN handle (arjun-4821); a request to a handle, once accepted, makes the
two users contacts (GET /api/contacts, POST /api/calls/ring). No world Tie is written: a connection is not a fact.
POST /api/connect/match finds which of my phone contacts are KIN users, by hashed number (Nudge's pattern)."""
from __future__ import annotations

import asyncio
import hashlib
import re
import secrets
import unicodedata
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StringConstraints, model_validator
from sqlalchemy import ForeignKey, String, UniqueConstraint, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..db import models as m
from ..db.session import get_session
from . import events
from .users import current_user

router = APIRouter(prefix="/api", tags=["connect"])
HANDLE_TRIES = 20
MAX_MATCH_HASHES = 2000


# Known limit: new tables, not columns, because the schema has no migrations (create_all builds these on startup).
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
    """Exactly one: a typed handle, or a slug from POST /api/connect/match (a matched user may have no handle yet)."""
    handle: str | None = Field(None, min_length=1, max_length=60)
    slug: str | None = Field(None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def _one_target(self) -> "ConnectIn":
        if (self.handle is None) == (self.slug is None):
            raise ValueError("send a handle or a slug")
        return self


class MatchIn(BaseModel):
    # Each hash is lowercase hex sha256 of world.users.normalize_phone(number): digits only (any Unicode decimal
    # digit), a bare 10 digits without a leading + gets US 1, then "+" in front (E.164, e.g. +15125550100).
    # The iOS ContactMatch.normalize mirrors it. Hashes are used for this one lookup, never stored or logged.
    hashes: list[Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]] = Field(max_length=MAX_MATCH_HASHES)


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


def _target(s: Session, body: ConnectIn) -> int:
    """The user a request is for, by handle or by slug; 404 when there is no such user."""
    if body.handle is not None:
        q = select(UserHandle.user_id).where(UserHandle.handle == body.handle.strip().lstrip("@").lower())
    else:
        q = select(m.User.id).join(m.Person, m.Person.id == m.User.person_id).where(m.Person.slug == body.slug)
    target_id = s.scalar(q)
    if target_id is None:
        raise HTTPException(404, f"no one with that {'handle' if body.handle is not None else 'slug'}")
    return target_id


def _request(s: Session, me: m.User, body: ConnectIn) -> tuple[dict, int | None, dict | None]:
    """(response, person id to notify, event). Unknown target and yourself fail before anything is written."""
    target_id = _target(s, body)
    if target_id == me.id:
        raise HTTPException(422, "that is your own handle" if body.handle is not None else "that is you")
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
    out, notify, msg = await asyncio.to_thread(_request, s, user, body)
    if notify is not None:
        await events.send_to(notify, msg)
    return out


def _relations(s: Session, me_id: int) -> dict[int, str]:
    """Other user id -> connected | incoming (they asked, pending) | requested (I asked; declined looks pending)."""
    rank = {"connected": 3, "incoming": 2, "requested": 1}
    out: dict[int, str] = {}
    for r in s.scalars(select(ConnectRequest).where(or_(ConnectRequest.from_user == me_id, ConnectRequest.to_user == me_id))):
        mine = r.from_user == me_id
        rel = ("connected" if r.status == "accepted" else "requested" if mine
               else "incoming" if r.status == "pending" else None)
        other = r.to_user if mine else r.from_user
        if rel and rank[rel] > rank.get(out.get(other, ""), 0):
            out[other] = rel
    return out


@router.post("/connect/match")
def match(body: MatchIn, user: m.User = Depends(current_user), s: Session = Depends(get_session)) -> dict:
    """KIN users whose linked phone hashes to one of `hashes`, never me. Reveals only that they exist (slug, name),
    never their number. Known limit: hashes every linked phone per call, O(users); add an indexed hash column at scale."""
    want = set(body.hashes)
    rows = s.execute(select(m.User.id, m.User.phone).where(m.User.phone.is_not(None), m.User.id != user.id))
    found = [uid for uid, phone in rows if hashlib.sha256(phone.encode()).hexdigest() in want]
    rel = _relations(s, user.id) if found else {}
    return {"results": [{**_who(s, uid), "relation": rel.get(uid, "none")} for uid in found]}


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
