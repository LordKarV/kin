"""Users routes: sign-up, me, contacts, and the X-KIN-User dependency every world route uses."""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import models as m
from ..db.session import get_session, session_scope
from ..graph.kin_tables import MUSE_LANGUAGES
from ..llm import get_llm
from ..world import clock, privacy
from ..world.contracts import ContactOut, DeleteMeOut, FormsOut, MeOut, MePatch, UserIn, UserOut
from ..world.extract import MAX_FORMS, clean_forms
from ..world.match import fold
from ..world.sms import refresh_calls
from ..world.users import create_user, normalize_phone, user_by_token
from ..world.view import WorldView

log = logging.getLogger("kin.api.users")
router = APIRouter(prefix="/api", tags=["users"])

FORMS_SYSTEM = """Write one person's name the way it is spelled in other scripts. Return JSON for the schema.
forms: up to 8 items {lang, form}: the name in its native script, a romanization (pinyin, romaji, RTGS, ISO-15919),
the common English spelling, and the name written in each language listed under LANGUAGES. lang is the language code.
One script per form. Never translate the meaning of the name."""


def current_user(x_kin_user: str | None = Header(default=None), s: Session = Depends(get_session)) -> m.User:
    """X-KIN-User token -> User, or 401."""
    user = user_by_token(s, x_kin_user)
    if user is None:
        raise HTTPException(401, "X-KIN-User token required (returned once by POST /api/users)")
    return user


def fetch_forms(person_id: int) -> None:
    """Background FormsOut call: cross-script spellings of a name, stored as translit aliases. Failures are
    logged; the person still matches by their typed name."""
    try:
        with session_scope() as s:
            p = s.get(m.Person, person_id)
            if p is None:
                return
            name = p.display_name
            langs = set(s.scalars(select(m.User.lang).join(m.Person, m.Person.id == m.User.person_id)
                                  .where(m.Person.family_id == p.family_id)))
        user = f"NAME: {name}\nLANGUAGES: {', '.join(sorted(langs | {'en'}))}"
        out = get_llm().structured(FormsOut, FORMS_SYSTEM, user, reasoning_effort="minimal",
                                   max_completion_tokens=1500, prompt_cache_key="kin-forms")
        with session_scope() as s:
            p = s.get(m.Person, person_id)
            if p is None:
                return
            have = {fold(x)[0].strip() for x in (p.display_name, p.lang_name, *(a.alias for a in p.aliases)) if x}
            for item in out.forms[:MAX_FORMS]:
                form = clean_forms([item.form])
                key = fold(form[0])[0].strip() if form else ""
                if key and key not in have:
                    have.add(key)
                    p.aliases.append(m.Alias(alias=form[0], lang=item.lang[:8], kind="translit"))
    except Exception:  # noqa: BLE001  background task: log it, never fail the request that scheduled it
        log.exception("FormsOut for person %s failed", person_id)


def _new_lang_others(s: Session, person: m.Person, lang: str) -> list[int]:
    """The other users' person ids when `lang` is new to the space: their names need forms in its script (a
    transcript in that script spells each name in it). fetch_forms always asks for English, so English is never new."""
    rows = s.execute(select(m.User.person_id, m.User.lang).join(m.Person, m.Person.id == m.User.person_id)
                     .where(m.Person.family_id == person.family_id, m.User.person_id != person.id)).all()
    return [] if lang == "en" or lang in {lg for _pid, lg in rows} else [pid for pid, _lg in rows]


def _me_out(s: Session, user: m.User) -> MeOut:
    p = s.get(m.Person, user.person_id)
    return MeOut(user_id=user.id, person_id=p.id, person=p.slug, name=p.display_name, lang=user.lang, phone=user.phone)


def circle(view: WorldView, me: int, pid: int) -> str | None:
    """family (any kin path), friends (a direct tie), group (a shared group), else None."""
    if me in view.kin.people and pid in view.kin.people and view.kin.shortest_steps(me, pid) is not None:
        return "family"
    hops = [h for h in view.adj.get(me, ()) if h.to == pid]
    if any(h.kind == "tie" for h in hops):
        return "friends"
    if any(h.kind == "group" for h in hops):
        return "group"
    return None


@router.post("/users", response_model=UserOut)
def sign_up(body: UserIn, background: BackgroundTasks, s: Session = Depends(get_session)) -> UserOut:
    phone = body.phone
    if phone is not None and not get_settings().dev_endpoints:
        # First come would win someone else's number: a phone links by texting "KIN <code>".
        log.info("sign-up phone not linked: texting the code from GET /api/me/phone-code links it")
        phone = None
    try:
        user, person, token = create_user(s, body.name, body.lang, phone)
    except ValueError as e:
        raise HTTPException(409 if "already linked" in str(e) else 422, str(e)) from e
    others = _new_lang_others(s, person, body.lang)
    s.commit()  # the background task reads the person in its own session
    for pid in [person.id, *others]:
        background.add_task(fetch_forms, pid)
    return UserOut(user_id=user.id, person_id=person.id, person=person.slug, space_id=person.family_id, token=token)


@router.get("/me", response_model=MeOut)
def get_me(user: m.User = Depends(current_user), s: Session = Depends(get_session)) -> MeOut:
    return _me_out(s, user)


@router.patch("/me", response_model=MeOut)
def patch_me(body: MePatch, background: BackgroundTasks, user: m.User = Depends(current_user),
             s: Session = Depends(get_session)) -> MeOut:
    p = s.get(m.Person, user.person_id)
    others: list[int] = []
    if body.name is not None:
        p.display_name = body.name.strip() or p.display_name
    if body.lang is not None:
        if body.lang not in MUSE_LANGUAGES:
            raise HTTPException(422, f"unsupported language {body.lang!r}")
        if body.lang != user.lang:
            others = _new_lang_others(s, p, body.lang)
        user.lang = body.lang
    if body.phone is not None:
        if body.phone.strip() and not get_settings().dev_endpoints:  # clearing your own number is always allowed
            raise HTTPException(403, "link a phone by texting 'KIN <code>' from it (code: GET /api/me/phone-code)")
        phone = normalize_phone(body.phone) if body.phone.strip() else None
        if body.phone.strip() and phone is None:
            raise HTTPException(422, f"invalid phone number {body.phone!r}")
        if phone and s.scalar(select(m.User.id).where(m.User.phone == phone, m.User.id != user.id)) is not None:
            raise HTTPException(409, "phone already linked")
        user.phone = phone
    s.flush()
    out = _me_out(s, user)
    s.commit()
    for pid in others:
        background.add_task(fetch_forms, pid)
    refresh_calls(person_id=p.id)
    return out


@router.delete("/me", response_model=DeleteMeOut)
def delete_me(user: m.User = Depends(current_user), s: Session = Depends(get_session)) -> DeleteMeOut:
    space_id = s.get(m.Person, user.person_id).family_id
    counts = privacy.delete_account(s, user)
    if not privacy.commit_and_checkpoint(s):
        log.warning("account delete committed but the WAL checkpoint was busy")
    refresh_calls(space_id=space_id)
    return DeleteMeOut(facts=counts.get("facts", 0), utterances=counts.get("utterances", 0))


@router.get("/contacts", response_model=list[ContactOut])
def contacts(user: m.User = Depends(current_user), s: Session = Depends(get_session)) -> list[ContactOut]:
    """Users I share a call, a tie or an edge with, or an accepted connect request (api/connect.py)."""
    from .connect import connected_person_ids  # lazy: connect imports current_user from here
    me = user.person_id
    my_calls = select(m.CallParticipant.call_id).where(m.CallParticipant.person_id == me)
    ids = set(s.scalars(select(m.CallParticipant.person_id).where(m.CallParticipant.call_id.in_(my_calls))))
    for src, dst in (*s.execute(select(m.Tie.src_person, m.Tie.dst_person).where(
                         m.Tie.status == "active", or_(m.Tie.src_person == me, m.Tie.dst_person == me))),
                     *s.execute(select(m.Edge.src_person, m.Edge.dst_person).where(
                         or_(m.Edge.src_person == me, m.Edge.dst_person == me)))):
        ids |= {src, dst}
    ids |= connected_person_ids(s, user.id)
    ids &= set(s.scalars(select(m.User.person_id)))
    ids.discard(me)
    if not ids:
        return []
    view = WorldView.build(s, s.get(m.Person, me).family_id, [me], clock.now())
    return [ContactOut(person=view.people[pid].slug, name=view.people[pid].name, lang=view.people[pid].lang,
                       render=view.render(me, pid), circle=circle(view, me, pid) or "friends")
            for pid in sorted(ids) if pid in view.people]
