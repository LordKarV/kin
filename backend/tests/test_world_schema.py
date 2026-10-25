from datetime import datetime, timezone

import pytest
from sqlalchemy import func, inspect, select, text

from app.db import models as m
from app.db.session import checkpoint_truncate, get_engine, init_db, session_scope
from app.world.users import create_user, get_space, normalize_phone, user_by_token

NEW_TABLES = {"users", "groups", "group_members", "ties", "facts", "fact_audience", "fact_refs", "storylines",
              "storyline_states", "knowledge", "card_log", "messages", "call_participants"}
T0 = datetime(2026, 9, 14, tzinfo=timezone.utc)


@pytest.fixture
def db():
    init_db()
    return get_engine()


def test_all_tables_create_with_new_columns(db):
    insp = inspect(db)
    assert NEW_TABLES <= set(insp.get_table_names())
    cols = lambda t: {c["name"] for c in insp.get_columns(t)}  # noqa: E731
    assert "kind" in cols("families") and "fact_id" in cols("edges") and "mode" in cols("calls")
    assert {"owner_id", "fact_id", "keys"} <= cols("things")
    assert {"lang", "audience", "translations"} <= cols("utterances")


def test_pragmas_on_file_db(db):
    with db.connect() as c:
        assert c.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert c.execute(text("PRAGMA secure_delete")).scalar() == 1
        assert c.execute(text("PRAGMA foreign_keys")).scalar() == 1


def _world(s):
    user, mei, _ = create_user(s, "Mei", "zh")
    _, arjun, _ = create_user(s, "Arjun", "en")
    lin = m.Person(family_id=mei.family_id, slug="p_lin_x", display_name="Lin")
    call = m.Call(family_id=mei.family_id, mode="world")
    s.add_all([lin, call])
    s.flush()
    story = m.Storyline(family_id=mei.family_id, slug="s_job", owner_id=mei.id, title="job search")
    s.add(story)
    s.flush()
    fact = m.Fact(family_id=mei.family_id, subject_id=mei.id, speaker_id=mei.id, predicate="state",
                  text="second round", lang="zh", keys=[["interview", "面试"]], source_kind="call",
                  call_id=call.id, said_at=T0, storyline_id=story.id)
    s.add(fact)
    s.flush()
    s.add_all([
        m.FactAudience(fact_id=fact.id, person_id=arjun.id, via="heard", at=T0, call_id=call.id),
        m.FactRef(fact_id=fact.id, kind="person", ref_id=lin.id),
        m.StorylineState(storyline_id=story.id, seq=1, label="second round", fact_id=fact.id, at=T0),
        m.Knowledge(knower_id=arjun.id, item_kind="fact", item_id=fact.id, p=0.9, half_life_days=7.0,
                    first_at=T0, last_at=T0, last_day="2026-09-14"),
        m.CardLog(call_id=call.id, listener_id=arjun.id, kind="who", key="p_lin", fact_ids=[fact.id], at=T0),
    ])
    return fact.id, arjun.id


def test_fact_round_trip_and_person_delete_cascades(db):
    with session_scope() as s:
        fact_id, arjun_id = _world(s)
    with session_scope() as s:
        f = s.get(m.Fact, fact_id)
        assert f.said_at == T0 and f.said_at.tzinfo is not None  # aware on read, comparable to clock.now()
        assert f.keys == [["interview", "面试"]] and f.status == "active" and f.shareable
        assert s.scalar(select(m.StorylineState.label).where(m.StorylineState.fact_id == fact_id)) == "second round"
        assert s.scalar(select(m.FactRef.kind).where(m.FactRef.fact_id == fact_id)) == "person"
        s.execute(m.Person.__table__.delete().where(m.Person.id == arjun_id))
    with session_scope() as s:
        for t, col in ((m.FactAudience, m.FactAudience.person_id), (m.Knowledge, m.Knowledge.knower_id),
                       (m.CardLog, m.CardLog.listener_id), (m.User, m.User.person_id)):
            assert s.scalar(select(func.count()).select_from(t).where(col == arjun_id)) == 0
        assert s.get(m.Fact, fact_id) is not None


def test_slugs_distinct_and_cjk_fallback(db):
    with session_scope() as s:
        _, a, _ = create_user(s, "Lin", "en")
        _, b, _ = create_user(s, "Lin", "zh")
        _, c, _ = create_user(s, "林美", "zh")
        assert a.slug == f"p_lin_{a.id}" and b.slug == f"p_lin_{b.id}" and a.slug != b.slug
        assert c.slug == f"p_{c.id}"
        assert a.family_id == c.family_id == get_space(s).id
        assert get_space(s).heritage_lang == "en" and get_space(s).kind == "space"


def test_token_round_trip_and_bad_lang(db):
    with session_scope() as s:
        user, _, token = create_user(s, "Priya", "hi", phone="+1 (512) 555-0101")
        assert user.token_hash != token and len(user.token_hash) == 64
        assert user.phone == "+15125550101"
        uid = user.id
    with session_scope() as s:
        assert user_by_token(s, token).id == uid
        assert user_by_token(s, "nope") is None and user_by_token(s, "") is None
        with pytest.raises(ValueError):
            create_user(s, "X", "xx")


@pytest.mark.parametrize("raw,want", [
    ("+1 512-555-0101", "+15125550101"), ("512-555-0101", "+15125550101"), ("15125550101", "+15125550101"),
    ("+86 138 0013 8000", "+8613800138000"), ("+९१ ९८७६५४३२१०", "+919876543210"), ("+５１２５５５０１０１", "+5125550101"),
    ("123", None), ("+1234567890123456", None), ("", None), (None, None),
])
def test_normalize_phone(raw, want):
    assert normalize_phone(raw) == want


def test_local_phone_matches_twilio_from_and_duplicates_rejected(db):
    with session_scope() as s:
        user, _, _ = create_user(s, "Arjun", "en", phone="512-555-0101")
        assert user.phone == normalize_phone("+15125550101")
        with pytest.raises(ValueError, match="already linked"):
            create_user(s, "Arjun2", "en", phone="+1 512 555 0101")


def test_one_space_enforced(db):
    with session_scope() as s:
        first = get_space(s)
        s.add(m.Family(name="dup", heritage_lang="en", kind="space"))
        with pytest.raises(Exception):
            s.flush()
        s.rollback()
        assert get_space(s).id == first.id


def _fact(s, subject_id, speaker_id, family_id):
    f = m.Fact(family_id=family_id, subject_id=subject_id, speaker_id=speaker_id, predicate="did", text="x",
               lang="en", source_kind="call", said_at=T0)
    s.add(f)
    s.flush()
    return f.id


def test_fact_delete_removes_everything_hanging_off_it(db):
    with session_scope() as s:
        fact_id, arjun_id = _world(s)
        f = s.get(m.Fact, fact_id)
        s.add_all([
            m.Edge(family_id=f.family_id, src_person=f.subject_id, dst_person=arjun_id, relation="sibling", fact_id=fact_id),
            m.Thing(family_id=f.family_id, slug="th_wall", kind="place", name="wall", fact_id=fact_id),
            m.Tie(family_id=f.family_id, src_person=f.subject_id, dst_person=arjun_id, kind="friend", fact_id=fact_id),
        ])
    with session_scope() as s:
        s.execute(m.Fact.__table__.delete().where(m.Fact.id == fact_id))
    with session_scope() as s:
        for t in (m.FactAudience, m.FactRef, m.StorylineState, m.Edge, m.Thing, m.Tie):
            assert s.scalar(select(func.count()).select_from(t).where(t.fact_id == fact_id)) == 0, t.__tablename__
        checkpoint_truncate(s)


def test_subject_delete_drops_fact_and_speaker_delete_nulls_it(db):
    with session_scope() as s:
        fact_id, arjun_id = _world(s)
        mei_id = s.get(m.Fact, fact_id).subject_id
        fam = s.get(m.Fact, fact_id).family_id
        about_arjun = _fact(s, arjun_id, mei_id, fam)
    with session_scope() as s:
        s.execute(m.Person.__table__.delete().where(m.Person.id == mei_id))
    with session_scope() as s:
        assert s.get(m.Fact, fact_id) is None
        assert s.get(m.Fact, about_arjun).speaker_id is None


def test_init_db_refuses_a_db_that_predates_the_schema(tmp_path):
    import sqlite3
    con = sqlite3.connect(tmp_path / "test.db")  # conftest's DATABASE_URL
    con.execute("CREATE TABLE families (id INTEGER PRIMARY KEY, name VARCHAR, heritage_lang VARCHAR)")
    con.commit()
    con.close()
    with pytest.raises(RuntimeError, match=r"families lacks \[.*'kind'"):
        init_db()
