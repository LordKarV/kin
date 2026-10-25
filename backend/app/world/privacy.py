"""Privacy operations (ARCHITECTURE section 10): delete a fact, a person or an account, and the third-party expiry sweep.

Every function returns per-table counts and never commits; the caller's session_scope does. Commit with
commit_and_checkpoint so the WAL does not keep the deleted text ("deleted means gone").
CASCADE covers most of the new tables, but the order here is explicit so the code does not depend on it (the legacy
tables have no ondelete at all, and PRAGMA foreign_keys=ON would reject the person delete)."""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import delete, exists, or_, select, text, update
from sqlalchemy.orm import Session

from ..db import models as m
from ..db.session import session_scope
from . import clock
from .apply import world_slug

log = logging.getLogger(__name__)


def _n(counts: dict[str, int], key: str, result) -> None:
    counts[key] = counts.get(key, 0) + (result.rowcount or 0)


def _strip_ids(s: Session, model, col: str, ids: set[int], counts: dict[str, int], key: str, **clear) -> None:
    """Remove ids from a JSON list column, and set `clear` columns on every row that cited one.
    ponytail: Python scan of the whole table; json_each query if it grows."""
    if not ids:
        return
    for row in s.scalars(select(model)):
        cur = getattr(row, col) or []
        if ids & set(cur):
            setattr(row, col, [x for x in cur if x not in ids])  # new list, so the ORM sees the change
            for k, v in clear.items():
                setattr(row, k, v)
            counts[key] = counts.get(key, 0) + 1


def _drop_items(s: Session, kind: str, ids: list[int], counts: dict[str, int]) -> None:
    """Knowledge and fact_refs point at things/groups by plain int (no FK). SQLite reuses a deleted max rowid, so a
    stale row would hand someone's P(knows) to the next thing created."""
    if ids:
        _n(counts, "knowledge", s.execute(delete(m.Knowledge).where(m.Knowledge.item_kind == kind, m.Knowledge.item_id.in_(ids))))
        _n(counts, "fact_refs", s.execute(delete(m.FactRef).where(m.FactRef.kind == kind, m.FactRef.ref_id.in_(ids))))


def _delete_things(s: Session, where, counts: dict[str, int]) -> None:
    gone = list(s.scalars(select(m.Thing.id).where(where)))
    if gone:
        _drop_items(s, "thing", gone, counts)
        _n(counts, "things", s.execute(delete(m.Thing).where(m.Thing.id.in_(gone))))


def _purge_facts(s: Session, fact_ids: set[int], counts: dict[str, int]) -> None:
    """Hard-delete facts and everything born from them or citing them."""
    if not fact_ids:
        return
    ids = list(fact_ids)
    state_ids = list(s.scalars(select(m.StorylineState.id).where(m.StorylineState.fact_id.in_(ids))))
    stories = set(s.scalars(select(m.StorylineState.storyline_id).where(m.StorylineState.fact_id.in_(ids))))
    stories |= set(s.scalars(select(m.Fact.storyline_id).where(m.Fact.id.in_(ids), m.Fact.storyline_id.is_not(None))))
    founded = [sid for sid in stories if s.scalars(select(m.StorylineState.fact_id).where(
        m.StorylineState.storyline_id == sid).order_by(m.StorylineState.seq).limit(1)).first() in fact_ids]
    _n(counts, "knowledge", s.execute(delete(m.Knowledge).where(or_(
        (m.Knowledge.item_kind == "fact") & m.Knowledge.item_id.in_(ids),
        (m.Knowledge.item_kind == "state") & m.Knowledge.item_id.in_(state_ids)))))
    _strip_ids(s, m.CardLog, "fact_ids", fact_ids, counts, "card_log_stripped")
    # The stored ack restates the news, so it goes with the fact.
    _strip_ids(s, m.Message, "fact_ids", fact_ids, counts, "messages_stripped", reply="")
    _n(counts, "fact_audience", s.execute(delete(m.FactAudience).where(m.FactAudience.fact_id.in_(ids))))
    _n(counts, "fact_refs", s.execute(delete(m.FactRef).where(m.FactRef.fact_id.in_(ids))))
    _n(counts, "storyline_states", s.execute(delete(m.StorylineState).where(m.StorylineState.fact_id.in_(ids))))
    _n(counts, "ties", s.execute(delete(m.Tie).where(m.Tie.fact_id.in_(ids))))
    _n(counts, "edges", s.execute(delete(m.Edge).where(m.Edge.fact_id.in_(ids))))
    _n(counts, "group_members", s.execute(delete(m.GroupMember).where(m.GroupMember.fact_id.in_(ids))))
    born = list(s.scalars(select(m.Group.id).where(m.Group.fact_id.in_(ids))))
    if born:
        _n(counts, "group_members", s.execute(delete(m.GroupMember).where(m.GroupMember.group_id.in_(born))))
        _drop_items(s, "group", born, counts)
        _n(counts, "groups", s.execute(delete(m.Group).where(m.Group.id.in_(born))))
    _delete_things(s, m.Thing.fact_id.in_(ids), counts)
    # Redact a source utterance only when no surviving fact cites it: every column that copies its words goes.
    utt_ids = set(s.scalars(select(m.Fact.utterance_id).where(m.Fact.id.in_(ids), m.Fact.utterance_id.is_not(None))))
    still = set(s.scalars(select(m.Fact.utterance_id).where(m.Fact.utterance_id.in_(utt_ids), m.Fact.id.not_in(ids))))
    if utt_ids - still:
        red = list(utt_ids - still)
        _n(counts, "utterances_redacted", s.execute(update(m.Utterance).where(m.Utterance.id.in_(red)).values(
            src_text="", translation="", translations={}, grounded_spans=[], cards=[], passthrough=[], src_lang_tags=[],
            sensitive_topic="")))
        _n(counts, "glossary", s.execute(delete(m.GlossaryEntry).where(m.GlossaryEntry.utterance_id.in_(red))))
    # Deleting a correction brings back what it replaced ("moved to Beijing" deleted: "lives in Shanghai" again).
    back = list(s.scalars(select(m.Fact.id).where(m.Fact.superseded_by.in_(ids), m.Fact.id.not_in(ids))))
    if back:
        _n(counts, "facts_restored", s.execute(update(m.Fact).where(m.Fact.id.in_(back), m.Fact.status == "superseded")
                                               .values(status="active")))
        s.execute(update(m.StorylineState).where(m.StorylineState.fact_id.in_(back),
                                                 m.StorylineState.status == "superseded").values(status="active"))
    s.execute(update(m.Fact).where(m.Fact.superseded_by.in_(ids)).values(superseded_by=None))
    _n(counts, "facts", s.execute(delete(m.Fact).where(m.Fact.id.in_(ids))))
    # A storyline left with no state and no fact keeps only a title and keys taken from the deleted words. Checked
    # after the fact delete because facts.storyline_id is ON DELETE CASCADE: a storyline still cited must stay.
    if stories:
        _n(counts, "storylines", s.execute(delete(m.Storyline).where(
            m.Storyline.id.in_(stories), ~exists().where(m.StorylineState.storyline_id == m.Storyline.id),
            ~exists().where(m.Fact.storyline_id == m.Storyline.id))))
    # The title, keys and slug came from the founding (first) state's fact (apply._storyline). The next state now
    # founds the thread; with no state left but a fact still citing it, the title is the hidden-title "news".
    for sid in founded:
        nxt = s.execute(select(m.StorylineState.label, m.Fact.keys).join(m.Fact, m.Fact.id == m.StorylineState.fact_id)
                        .where(m.StorylineState.storyline_id == sid).order_by(m.StorylineState.seq).limit(1)).first()
        title, keys = (nxt.label[:120], nxt.keys or []) if nxt else ("news", [])
        _n(counts, "storylines_retitled", s.execute(update(m.Storyline).where(m.Storyline.id == sid).values(
            title=title, keys=keys, slug=world_slug("s", title, sid))))


def delete_fact(s: Session, fact_id: int, by_person: int) -> dict[str, int]:
    """Only the fact's subject or speaker may delete it. Raises LookupError (missing) or PermissionError."""
    f = s.get(m.Fact, fact_id)
    if f is None:
        raise LookupError(f"fact {fact_id} not found")
    if by_person not in (f.subject_id, f.speaker_id):
        raise PermissionError(f"person {by_person} may not delete fact {fact_id}")
    counts: dict[str, int] = {}
    _purge_facts(s, {fact_id}, counts)
    s.expire_all()
    return counts


def delete_person(s: Session, person_id: int) -> dict[str, int]:
    """Remove a person and every row that names them. One transaction, the caller's."""
    P = person_id
    counts: dict[str, int] = {}
    owned = list(s.scalars(select(m.Storyline.id).where(m.Storyline.owner_id == P)))
    fact_ids = set(s.scalars(select(m.Fact.id).where(or_(
        m.Fact.subject_id == P, m.Fact.speaker_id == P, m.Fact.storyline_id.in_(owned)))))
    # A tie/edge/membership fact can have someone else as subject ("Arjun is Mei's friend", subject Mei): it is
    # still about P, and without the tie it would be P's name with nothing attached.
    for col, q in ((m.Tie.fact_id, or_(m.Tie.src_person == P, m.Tie.dst_person == P)),
                   (m.Edge.fact_id, or_(m.Edge.src_person == P, m.Edge.dst_person == P)),
                   (m.GroupMember.fact_id, m.GroupMember.person_id == P)):
        fact_ids |= set(s.scalars(select(col).where(q, col.is_not(None))))
    _n(counts, "knowledge", s.execute(delete(m.Knowledge).where(or_(
        m.Knowledge.knower_id == P, (m.Knowledge.item_kind == "person") & (m.Knowledge.item_id == P)))))
    # ponytail: Python scan for the JSON intersect; fine at hackathon scale.
    gone = [c.id for c in s.scalars(select(m.CardLog)) if P in (c.listener_id, c.target_id) or fact_ids & set(c.fact_ids or [])]
    if gone:
        _n(counts, "card_log", s.execute(delete(m.CardLog).where(m.CardLog.id.in_(gone))))
    _n(counts, "fact_audience", s.execute(delete(m.FactAudience).where(m.FactAudience.person_id == P)))
    _n(counts, "fact_refs", s.execute(delete(m.FactRef).where(m.FactRef.kind == "person", m.FactRef.ref_id == P)))
    if owned:  # section 10 order: storyline_states then storylines, before facts
        states = list(s.scalars(select(m.StorylineState.id).where(m.StorylineState.storyline_id.in_(owned))))
        if states:
            _n(counts, "knowledge", s.execute(delete(m.Knowledge).where(m.Knowledge.item_kind == "state",
                                                                         m.Knowledge.item_id.in_(states))))
            _n(counts, "storyline_states", s.execute(delete(m.StorylineState).where(m.StorylineState.id.in_(states))))
        s.execute(update(m.Fact).where(m.Fact.storyline_id.in_(owned)).values(storyline_id=None))  # all in fact_ids
        _n(counts, "storylines", s.execute(delete(m.Storyline).where(m.Storyline.id.in_(owned))))
    _purge_facts(s, fact_ids, counts)
    _n(counts, "ties", s.execute(delete(m.Tie).where(or_(m.Tie.src_person == P, m.Tie.dst_person == P))))
    _n(counts, "group_members", s.execute(delete(m.GroupMember).where(m.GroupMember.person_id == P)))
    _n(counts, "edges", s.execute(delete(m.Edge).where(or_(m.Edge.src_person == P, m.Edge.dst_person == P))))
    _delete_things(s, m.Thing.owner_id == P, counts)
    _n(counts, "aliases", s.execute(delete(m.Alias).where(m.Alias.person_id == P)))
    spoken = list(s.scalars(select(m.Utterance.id).where(m.Utterance.speaker_id == P)))
    if spoken:  # glossary.utterance_id has no ondelete; a card cut from P's words goes with them
        _n(counts, "glossary", s.execute(delete(m.GlossaryEntry).where(m.GlossaryEntry.utterance_id.in_(spoken))))
        _n(counts, "utterances", s.execute(delete(m.Utterance).where(m.Utterance.id.in_(spoken))))
    _n(counts, "utterances_unlistened", s.execute(update(m.Utterance).where(m.Utterance.listener_id == P).values(listener_id=None)))
    for u in s.scalars(select(m.Utterance)):
        if P in (u.audience or []):
            u.audience = [x for x in u.audience if x != P]
            counts["utterances_audience"] = counts.get("utterances_audience", 0) + 1
    for c in s.scalars(select(m.Call)):
        if P in (c.participants or []):
            c.participants = [x for x in c.participants if x != P]
            counts["calls_participants"] = counts.get("calls_participants", 0) + 1
    s.flush()
    _n(counts, "messages", s.execute(delete(m.Message).where(m.Message.author_id == P)))
    _n(counts, "call_participants", s.execute(delete(m.CallParticipant).where(m.CallParticipant.person_id == P)))
    _n(counts, "mastery", s.execute(delete(m.Mastery).where(m.Mastery.learner_id == P)))
    _n(counts, "consents", s.execute(delete(m.Consent).where(m.Consent.person_id == P)))
    _n(counts, "glossary_unspoken", s.execute(update(m.GlossaryEntry).where(m.GlossaryEntry.speaker_id == P).values(speaker_id=None)))
    _n(counts, "users", s.execute(delete(m.User).where(m.User.person_id == P)))
    _n(counts, "people", s.execute(delete(m.Person).where(m.Person.id == P)))
    s.expire_all()  # bulk deletes bypass the identity map; never hand back a stale Person or Fact
    return counts


def delete_account(s: Session, user: m.User) -> dict[str, int]:
    """delete_person, then the third parties only this user's facts linked (they would otherwise wait for the sweep)."""
    counts = delete_person(s, user.person_id)
    for pid in list(s.scalars(_orphans_q())):
        for k, v in delete_person(s, pid).items():
            counts[k] = counts.get(k, 0) + v
    return counts


def _orphans_q():
    """Third-party people of a world space that nothing links any more. Users and legacy families never qualify."""
    users = select(m.User.person_id)
    spaces = select(m.Family.id).where(m.Family.kind == "space")
    linked = [
        select(m.Fact.subject_id), select(m.Fact.speaker_id).where(m.Fact.speaker_id.is_not(None)),
        select(m.FactRef.ref_id).where(m.FactRef.kind == "person"),
        select(m.Tie.src_person), select(m.Tie.dst_person), select(m.Edge.src_person), select(m.Edge.dst_person),
        select(m.GroupMember.person_id),
    ]
    return select(m.Person.id).where(m.Person.family_id.in_(spaces), m.Person.id.not_in(users),
                                     *(m.Person.id.not_in(sq) for sq in linked))


def forget_person(s: Session, person_id: int, by_person: int) -> dict:
    """DELETE /api/me/world/people/{slug}: drop the facts `by_person` said about a third party (as subject, or naming
    them), then the person if nothing links them any more. Raises LookupError, or PermissionError for a user."""
    if s.get(m.Person, person_id) is None:
        raise LookupError(f"person {person_id} not found")
    if s.scalar(select(m.User.id).where(m.User.person_id == person_id)) is not None:
        raise PermissionError("users delete their own data")
    named = select(m.FactRef.fact_id).where(m.FactRef.kind == "person", m.FactRef.ref_id == person_id)
    fact_ids = set(s.scalars(select(m.Fact.id).where(
        m.Fact.speaker_id == by_person, or_(m.Fact.subject_id == person_id, m.Fact.id.in_(named)))))
    counts: dict[str, int] = {}
    _purge_facts(s, fact_ids, counts)
    s.flush()
    gone = s.scalar(_orphans_q().where(m.Person.id == person_id)) is not None
    if gone:
        delete_person(s, person_id)
    s.expire_all()
    return {"deleted_facts": counts.get("facts", 0), "person_deleted": gone}


def sweep_expired(s: Session, now: datetime) -> dict[str, int]:
    """Hard-delete expired unpinned third-party facts, then third-party people of the world space left with no
    facts, refs, ties, edges or group memberships. Users and legacy-family people are never swept."""
    counts: dict[str, int] = {}
    expired = set(s.scalars(select(m.Fact.id).where(
        m.Fact.third_party.is_(True), m.Fact.pinned.is_(False), m.Fact.expires_at.is_not(None), m.Fact.expires_at <= now)))
    _purge_facts(s, expired, counts)
    orphans = list(s.scalars(_orphans_q()))
    for pid in orphans:
        for k, v in delete_person(s, pid).items():
            counts[k] = counts.get(k, 0) + v
    counts["orphans"] = len(orphans)
    s.expire_all()
    return counts


def _wal_checkpoint(s: Session) -> int:
    """PRAGMA wal_checkpoint(TRUNCATE); returns its busy flag. Run here instead of session.checkpoint_truncate,
    which discards the result row."""
    if s.get_bind().dialect.name != "sqlite":
        return 0
    return int(s.execute(text("PRAGMA wal_checkpoint(TRUNCATE)")).one()[0])


def commit_and_checkpoint(s: Session) -> bool:
    """Commit a delete, then truncate the WAL (secure_delete only zeroes pages after a checkpoint) and drop cached
    legacy graphs that may still hold the deleted person. Returns False when another connection's read kept the WAL
    from truncating; the deleted rows then sit in kin.db-wal until the next checkpoint (run_sweep runs hourly).
    ponytail: no retry, since each busy attempt already waits out the sqlite busy timeout (5 s by default)."""
    from ..mt.translate import reset_translator_cache
    s.commit()
    busy = _wal_checkpoint(s)
    s.commit()  # the pragma runs inside a SQLAlchemy transaction; do not hold it open
    reset_translator_cache()
    if busy:
        log.warning("WAL checkpoint busy after delete; deleted rows remain in the WAL until the next checkpoint")
    return not busy


def run_sweep() -> dict[str, int]:
    """Startup / call end / hourly entry point: own session, sweep at world clock time, commit, checkpoint."""
    with session_scope() as s:
        counts = sweep_expired(s, clock.now())
        commit_and_checkpoint(s)
    if counts.get("facts") or counts.get("orphans"):
        log.info("third-party sweep: %s", counts)
    return counts
