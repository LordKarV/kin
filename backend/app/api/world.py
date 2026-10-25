"""World routes: my world view, placing people, and owning my facts.

Everything returned is what the viewer may see: a WorldView built for [me] decides it.
"""
from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import models as m
from ..db.session import get_session
from ..graph import builder
from ..world import clock, privacy
from ..world.apply import _find_person, _new_person, form_lang, place_person
from ..world.contracts import (DeletedOut, DeletePersonOut, FactPatch, FactRow, FactsOut, HeardByOut, KinRelationOut,
                               PlaceIn, PlaceOut, RelationsOut, SocialRelationOut, WorldEdgeOut, WorldGroupOut,
                               WorldOut, WorldPersonOut, WorldStateOut, WorldStorylineOut, WorldThingOut, WorldTieOut)
from ..world.extract import TIE_KINDS
from ..world.match import fold
from ..world.sms import refresh_calls, write_evidence
from ..world.view import TIE_LABEL, WorldView
from ..world.visibility import fact_visible
from .users import circle, current_user, fetch_forms

log = logging.getLogger("kin.api.world")
router = APIRouter(prefix="/api", tags=["world"])


def _space(s: Session, user: m.User) -> int:
    return s.get(m.Person, user.person_id).family_id


def _seen(view: WorldView, me: int, fact_id: int | None) -> bool:
    """A link row is visible to me when it is setup data (no fact) or I heard its fact."""
    if fact_id is None:
        return True
    f = view.facts.get(fact_id)
    return f is not None and fact_visible(f, view.audience.get(fact_id, frozenset()), me, view.now)


def _target(s: Session, view: WorldView, me: int, space_id: int, body: PlaceIn) -> str | None:
    """The slug place_person should use, resolved over MY view only: a person I can see (or any
    user: users are addressable), an exact name match among them, or None for a brand-new person. A name that only
    matches someone hidden from me gets a fresh Person here, so place_person's space-wide name match never reaches it."""
    addressable = [p for p in view.people.values() if p.is_user or view.visible(me, "person", p.id)]
    if body.person is not None:
        if not any(p.slug == body.person for p in addressable):
            raise HTTPException(404, f"no person {body.person!r} in your world")
        return body.person
    key = fold(body.name or "")[0].strip()
    if not key:
        return None
    hits = [p for p in addressable if p.id != me
            and any(f and fold(f)[0].strip() == key for f in (p.name, p.lang_name, *(a for a, _l in p.aliases)))]
    if len(hits) > 1:
        raise HTTPException(409, f"{body.name!r} matches {len(hits)} people in your world; pass `person` (a slug)")
    if hits:
        return hits[0].slug
    if _find_person(s, space_id, body.name or "") is None:
        return None  # no row anywhere: place_person creates it
    fresh = _new_person(s, space_id, body.name.strip())
    fresh.aliases.append(m.Alias(alias=fresh.display_name, lang=form_lang(fresh.display_name, []), kind="name"))
    s.flush()
    return fresh.slug


def _after_privacy(s: Session, space_id: int) -> None:
    if not privacy.commit_and_checkpoint(s):
        log.warning("privacy delete committed but the WAL checkpoint was busy; rows remain in the WAL until the next one")
    refresh_calls(space_id=space_id)


# ---------------------------------------------------------------------------------------------------------------------
# world view


@router.get("/world", response_model=WorldOut)
def get_world(user: m.User = Depends(current_user), s: Session = Depends(get_session)) -> WorldOut:
    me = user.person_id
    view = WorldView.build(s, _space(s, user), [me], clock.now())
    vis = {pid for pid in view.people if view.visible(me, "person", pid)}
    slug = {pid: view.people[pid].slug for pid in vis}
    people = [WorldPersonOut(id=pid, person=slug[pid], name=view.people[pid].name, render=view.render(me, pid),
                             lang=view.people[pid].lang, is_user=view.people[pid].is_user, circle=circle(view, me, pid))
              for pid in sorted(vis)]
    ties = [WorldTieOut(src=slug[t.src_person], dst=slug[t.dst_person], kind=t.kind, context=t.context)
            for t in s.scalars(select(m.Tie).where(m.Tie.family_id == view.space_id, m.Tie.status == "active"))
            if t.src_person in vis and t.dst_person in vis
            and (me in (t.src_person, t.dst_person) or _seen(view, me, t.fact_id))]
    edges = [WorldEdgeOut(src=slug[e.src_person], dst=slug[e.dst_person], relation=e.relation)
             for e in s.scalars(select(m.Edge).where(m.Edge.family_id == view.space_id))
             if e.src_person in vis and e.dst_person in vis
             and (me in (e.src_person, e.dst_person) or _seen(view, me, e.fact_id))]
    groups = [WorldGroupOut(id=g.id, name=g.name, members=sorted(slug[p] for p in g.members if p in vis))
              for g in view.groups.values() if view.visible(me, "group", g.id)]
    things = [WorldThingOut(id=t.id, slug=t.slug, kind=t.kind, name=t.name,
                            owner=slug.get(t.owner_id) if t.owner_id is not None else None)
              for t in view.things.values() if view.visible(me, "thing", t.id)]
    stories = []
    for st in view.storylines.values():
        if not view.visible(me, "storyline", st.id):
            continue
        mine = st.owner_id == me
        states = [WorldStateOut(label=label, at=at.date().isoformat()) for _sid, label, at, fid, status in st.states
                  if status == "active" and (mine or _seen(view, me, fid))]
        # the title comes from the founding fact, which may be an SMS only its author saw (cards.storylines)
        title = st.title if mine or (st.states and _seen(view, me, st.states[0][3])) else "news"
        stories.append(WorldStorylineOut(id=st.id, title=title, status=st.status, states=states,
                                         owner=slug.get(st.owner_id)))
    return WorldOut(me=view.people[me].slug, people=people, ties=ties, edges=edges, groups=groups, things=things,
                    storylines=stories)


@router.get("/world/relations", response_model=RelationsOut)
def relations(lang: str = "", user: m.User = Depends(current_user)) -> RelationsOut:
    """Social kinds plus common kin paths. Known limit: `lang` is accepted for the picker and not used yet; labels are
    English (the app localizes them); add builder.suggest per kin word if the picker needs language-specific paths."""
    social = [SocialRelationOut(kind=k, label=TIE_LABEL.get(k, k.replace("_", " "))) for k in sorted(TIE_KINDS)]
    return RelationsOut(social=social, kin=[KinRelationOut(path=r["path"], label=r["label"]) for r in builder.relations()])


@router.post("/world/place", response_model=PlaceOut)
def place(body: PlaceIn, background: BackgroundTasks, user: m.User = Depends(current_user),
          s: Session = Depends(get_session)) -> PlaceOut:
    me, space_id, now = user.person_id, _space(s, user), clock.now()
    if body.relation == "same_as":
        return _confirm(s, me, space_id, body, now)
    view = WorldView.build(s, space_id, [me], now)
    owner = next((p for p in view.people.values() if p.slug == body.owner), None)
    if owner is None or not view.visible(me, "person", owner.id):
        raise HTTPException(404, f"no person {body.owner!r} in your world")
    call_audience: list[int] = []
    if body.call_id is not None:
        rows = set(s.scalars(select(m.CallParticipant.person_id).where(m.CallParticipant.call_id == body.call_id)))
        if me not in rows:
            raise HTTPException(403, "not a participant of that call")
        call_audience = sorted(rows - {me})
    before = s.scalar(select(func.max(m.Person.id))) or 0
    target = _target(s, view, me, space_id, body)
    try:
        person, evidence = place_person(s, space_id, me, body.name or "", owner.id, body.relation, body.context or "",
                                        call_audience, person=target, now=now, call_id=body.call_id)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    write_evidence(s, evidence, now)
    s.commit()
    if person.id > before:  # a new person: fetch cross-script forms off the request path
        background.add_task(fetch_forms, person.id)
    render = WorldView.build(s, space_id, [me], now).render(me, person.id)
    refresh_calls(person_id=me)
    return PlaceOut(id=person.id, person=person.slug, name=person.display_name, render=render)


def _offered(call_id: int, me: int, slug: str) -> str | None:
    """The label a "Which X?" card delivered to me in this live call showed for candidate `slug`, else None."""
    from ..audio.pipeline import registry  # local: the pipeline imports the audio stack
    world = getattr(registry.get(call_id), "world", None)
    delivered = getattr(world, "delivered", None) or {}  # replaced, never mutated (LiveWorld._admit): safe to read
    return next((sg["label"] for (ident, _k), c in delivered.items() if ident == f"p{me}" and c.kind == "ask"
                 for sg in c.payload.get("suggestions") or []
                 if sg.get("owner") == slug and sg.get("relation") == "same_as"), None)


def _confirm(s: Session, me: int, space_id: int, body: PlaceIn, now: datetime) -> PlaceOut:
    """A "Which Ravi?" pick (cards._ask_ambiguous): `owner` is the candidate the listener means. It creates no tie;
    it records that the listener knows that person. A candidate only the call's other participant may disclose is
    accepted only when an ask card delivered to me in that live call offered it, and the reply repeats that card's
    label: checking disclosure alone would let any past co-participant probe the other's ties by guessing slugs."""
    label = None
    if body.call_id is not None:
        rows = set(s.scalars(select(m.CallParticipant.person_id).where(m.CallParticipant.call_id == body.call_id)))
        if me not in rows:
            raise HTTPException(403, "not a participant of that call")
        label = _offered(body.call_id, me, body.owner)
    view = WorldView.build(s, space_id, [me], now)
    p = s.scalar(select(m.Person).where(m.Person.family_id == space_id, m.Person.slug == body.owner))
    if p is None or (label is None and not (p.id in view.people and view.visible(me, "person", p.id))):
        raise HTTPException(404, f"no person {body.owner!r} in your world")
    write_evidence(s, [(me, "person", p.id, "confirmed")], now)
    s.commit()
    refresh_calls(person_id=me)
    return PlaceOut(id=p.id, person=p.slug, name=p.display_name,
                    render=label if label is not None else view.render(me, p.id))


# ---------------------------------------------------------------------------------------------------------------------
# my facts


def _row(s: Session, f: m.Fact) -> FactRow:
    slug = lambda pid: s.get(m.Person, pid).slug if pid is not None and s.get(m.Person, pid) else None  # noqa: E731
    heard = s.execute(select(m.Person.slug, m.Person.display_name, m.FactAudience.via)
                      .join(m.Person, m.Person.id == m.FactAudience.person_id).where(m.FactAudience.fact_id == f.id)
                      .order_by(m.FactAudience.id)).all()
    return FactRow(id=f.id, text=f.text, subject=slug(f.subject_id), speaker=slug(f.speaker_id),
                   source_kind=f.source_kind, said_at=f.said_at, status=f.status, sensitive_kind=f.sensitive_kind,
                   pinned=f.pinned, expires_at=f.expires_at,
                   heard_by=[HeardByOut(person=p, name=n, via=v) for p, n, v in heard])


@router.get("/me/facts", response_model=FactsOut)
def my_facts(user: m.User = Depends(current_user), s: Session = Depends(get_session)) -> FactsOut:
    me = user.person_id
    about = s.scalars(select(m.Fact).where(m.Fact.subject_id == me).order_by(m.Fact.said_at.desc())).all()
    said = s.scalars(select(m.Fact).where(m.Fact.speaker_id == me, m.Fact.subject_id != me)
                     .order_by(m.Fact.said_at.desc())).all()
    return FactsOut(about_me=[_row(s, f) for f in about], i_said=[_row(s, f) for f in said])


@router.patch("/me/facts/{fact_id}", response_model=FactRow)
def patch_fact(fact_id: int, body: FactPatch, user: m.User = Depends(current_user),
               s: Session = Depends(get_session)) -> FactRow:
    """text/status: subject or speaker only. pinned/remembered: also anyone who heard it."""
    me = user.person_id
    f = s.get(m.Fact, fact_id)
    if f is None:
        raise HTTPException(404, f"fact {fact_id} not found")
    owner = me in (f.subject_id, f.speaker_id)
    heard = s.scalar(select(m.FactAudience.id).where(m.FactAudience.fact_id == fact_id,
                                                     m.FactAudience.person_id == me)) is not None
    if (body.text is not None or body.status is not None) and not owner:
        raise HTTPException(403, "only the fact's subject or speaker may change its text or status")
    if (body.pinned is not None or body.remembered is not None) and not (owner or heard):
        raise HTTPException(403, "not your fact")
    for col in ("text", "status", "pinned", "remembered"):
        if getattr(body, col) is not None:
            setattr(f, col, getattr(body, col))
    if body.text is not None:  # the old detail must not survive in the source span or the match keys
        f.text_src, f.keys = "", []
    s.flush()
    out = _row(s, f)
    s.commit()
    refresh_calls(space_id=f.family_id)
    return out


@router.delete("/me/facts/{fact_id}", response_model=DeletedOut)
def delete_fact(fact_id: int, user: m.User = Depends(current_user), s: Session = Depends(get_session)) -> DeletedOut:
    try:
        privacy.delete_fact(s, fact_id, by_person=user.person_id)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    _after_privacy(s, _space(s, user))
    return DeletedOut()


@router.delete("/me/world/people/{slug}", response_model=DeletePersonOut)
def forget(slug: str, user: m.User = Depends(current_user), s: Session = Depends(get_session)) -> DeletePersonOut:
    space_id = _space(s, user)
    pid = s.scalar(select(m.Person.id).where(m.Person.family_id == space_id, m.Person.slug == slug))
    view = WorldView.build(s, space_id, [user.person_id], clock.now()) if pid is not None else None
    # someone I cannot see (the GET /api/world rule) answers like a missing slug, else the reply is an existence oracle
    if pid is None or pid not in view.people or not view.visible(user.person_id, "person", pid):
        raise HTTPException(404, f"no person {slug!r}")
    try:
        out = privacy.forget_person(s, pid, by_person=user.person_id)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    _after_privacy(s, space_id)
    return DeletePersonOut(**out)
