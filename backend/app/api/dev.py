"""Dev routes (docs/ARCHITECTURE.md 9.2, D22): world clock, direct world updates, SMS without Twilio, and sign-in as
an existing user. All 404 when settings.dev_endpoints is false, and on a locked server (security.locked()) also to any
caller that is not loopback, because the KIN key travels in every invite link. No X-KIN-User: these drive the demo and
eval through the real server."""
from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import security
from ..config import get_settings
from ..db import models as m
from ..db.session import get_session
from ..world import clock
from ..world.apply import ApplyCtx, apply_update
from ..world.contracts import AppliedEntity, ClockIn, ClockOut, DevApplyIn, DevApplyOut, DevSmsIn, DevSmsOut, FactBrief
from ..world.extract import ENTITY_TABLE, Candidate, Line, Participant, own_context, validate, validate_ctx
from ..world.sms import UNKNOWN_REPLY, ingest, refresh_calls, write_evidence
from ..world.users import _hash, get_space, normalize_phone


_LOOPBACK = ("127.0.0.1", "::1")


def _loopback(request: Request) -> bool:
    return request.client is not None and request.client.host in _LOOPBACK


def _dev_only(request: Request) -> None:
    if not get_settings().dev_endpoints or (security.locked() and not _loopback(request)):
        raise HTTPException(404, "Not Found")


log = logging.getLogger("kin.api.dev")
router = APIRouter(prefix="/api/dev", tags=["dev"], dependencies=[Depends(_dev_only)])
_TABLE = {"person": m.Person, "thing": m.Thing, "group": m.Group}


@router.post("/clock", response_model=ClockOut)
def set_clock(body: ClockIn) -> ClockOut:
    try:
        clock.set_offset_days(body.offset_days)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return ClockOut(now=clock.now())


def _person(s: Session, space_id: int, slug: str) -> m.Person:
    p = s.scalars(select(m.Person).where(m.Person.family_id == space_id, m.Person.slug == slug)).first()
    if p is None:
        raise HTTPException(404, f"no person {slug!r} in the world space")
    return p


@router.post("/apply", response_model=DevApplyOut)
def dev_apply(body: DevApplyIn, s: Session = Depends(get_session)) -> DevApplyOut:
    """Same validate + apply_update path as a call: one line 0 said by `speaker`, heard by `audience`."""
    space_id = get_space(s).id
    speaker = _person(s, space_id, body.speaker)
    audience = [_person(s, space_id, a).id for a in body.audience]
    if body.call_id is not None and s.get(m.Call, body.call_id) is None:
        raise HTTPException(404, f"no call {body.call_id}")
    users = dict(s.execute(select(m.User.person_id, m.User.lang)).all())
    lang = users.get(speaker.id, "en")
    # Dev tool: every row in the space is a candidate (real calls offer only what the speaker can see).
    cands = [Candidate("person", p.id, p.slug, p.display_name, p.id in users)
             for p in s.scalars(select(m.Person).where(m.Person.family_id == space_id))]
    cands += [Candidate(kind, r.id, r.slug, r.name, False) for kind, model in (("thing", m.Thing), ("group", m.Group))
              for r in s.scalars(select(model).where(model.family_id == space_id))]
    window = [Line(0, speaker.id, lang, "")]
    vctx = validate_ctx(window, [Participant(speaker.id, speaker.slug, speaker.display_name, lang)],
                        {speaker.id: own_context(s, speaker.id)}, {speaker.id: cands})
    # 9.2: every fact cites line 0 by the speaker, whatever the payload said.
    update = body.update.model_copy(update={"facts": [f.model_copy(update={"lines": [0]}) for f in body.update.facts]})
    clean, dropped = validate(update, vctx)
    if dropped:
        log.warning("dev/apply dropped %d item(s): %s", len(dropped), "; ".join(dropped))
    now = clock.now()
    ctx = ApplyCtx(space_id, body.call_id, None, {0: speaker.id}, {0: audience}, {}, now,
                   source_kind="call" if body.call_id is not None else "setup")
    res = apply_update(s, clean, ctx)
    write_evidence(s, res.evidence, now)
    table = {e.ref: ENTITY_TABLE[e.kind] for e in clean.entities}
    entities = [AppliedEntity(ref=ref, id=rid, slug=s.get(_TABLE[table[ref]], rid).slug) for ref, rid in res.entities.items()]
    s.commit()
    refresh_calls(space_id=space_id)
    return DevApplyOut(facts=res.facts, entities=entities)


@router.post("/sms", response_model=DevSmsOut)
def dev_sms(body: DevSmsIn, s: Session = Depends(get_session)) -> DevSmsOut:
    """The Twilio path without a signature or a number (section 7)."""
    phone = normalize_phone(body.from_)
    user = s.scalars(select(m.User).where(m.User.phone == phone)).first() if phone else None
    if user is None:
        return DevSmsOut(reply=UNKNOWN_REPLY)
    reply, message_id, facts = ingest(s, user, body.body)
    return DevSmsOut(reply=reply, message_id=message_id, facts=[FactBrief(**f) for f in facts])


class DevSigninIn(BaseModel):
    person: str  # the user's person slug


class DevSigninOut(BaseModel):
    person: str
    token: str


@router.post("/signin", response_model=DevSigninOut)
def dev_signin(body: DevSigninIn, request: Request, s: Session = Depends(get_session)) -> DevSigninOut:
    """A fresh X-KIN-User token for an existing user, so a phone can become the demo driver's Arjun when the driver's
    printed sign-in link is lost. Only the hash is stored, so this rotates it: the previous token stops working.
    Loopback callers only: the KIN key travels in every invite link, so on a deploy with DEV_ENDPOINTS=1 the key alone
    would hand anyone a takeover of any account (run the curl on the server host, over ssh)."""
    if not _loopback(request):  # even unlocked: a LAN dev server is reachable by anyone on the network
        raise HTTPException(404, "Not Found")
    person = _person(s, get_space(s).id, body.person)
    user = s.scalars(select(m.User).where(m.User.person_id == person.id)).first()
    if user is None:
        raise HTTPException(404, f"{body.person!r} is not a user")
    token = secrets.token_urlsafe(32)
    user.token_hash = _hash(token)
    s.commit()
    log.warning("dev/signin rotated the token of %s", person.slug)
    return DevSigninOut(person=person.slug, token=token)
