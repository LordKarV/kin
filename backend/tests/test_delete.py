"""Privacy operations (ARCHITECTURE section 10): deleted means gone, third parties expire, only owners delete facts."""
from datetime import datetime, timedelta, timezone

import json

import pytest
from sqlalchemy import JSON, String, Text, select

from app.db import models as m
from app.db.session import init_db, session_scope
from app.world import privacy
from app.world.users import create_user

T0 = datetime(2026, 9, 14, tzinfo=timezone.utc)
JSON_ID_COLS = {"audience", "participants"}


@pytest.fixture
def db():
    init_db()


def _fact(s, fam, subject, speaker, text, **kw):
    f = m.Fact(family_id=fam, subject_id=subject, speaker_id=speaker, predicate=kw.pop("predicate", "did"), text=text,
               lang="en", source_kind="call", said_at=kw.pop("said_at", T0), **kw)
    s.add(f); s.flush()
    return f


def _world(s):
    _, mei, _ = create_user(s, "Mei", "zh")
    _, arjun, _ = create_user(s, "Arjun", "en")
    _, priya, _ = create_user(s, "Priya", "en")
    fam = arjun.family_id
    lin = m.Person(family_id=fam, slug="p_lin_9", display_name="Lin")
    call = m.Call(family_id=fam, mode="world", participants=[mei.id, arjun.id])
    s.add_all([lin, call]); s.flush()
    u_arjun = m.Utterance(call_id=call.id, speaker_id=arjun.id, listener_id=mei.id, src_text="I started bouldering",
                          translations={"zh": "我开始抱石了"}, audience=[mei.id])
    u_mei = m.Utterance(call_id=call.id, speaker_id=mei.id, listener_id=arjun.id, src_text="Arjun got the internship",
                        audience=[arjun.id, priya.id], grounded_spans=[{"source": "实习", "rendered": "got the internship"}],
                        cards=[{"text": "got the internship"}], sensitive_topic="money")
    u_mei2 = m.Utterance(call_id=call.id, speaker_id=mei.id, listener_id=arjun.id, src_text="I went climbing with Lin",
                         audience=[arjun.id])
    s.add_all([u_arjun, u_mei, u_mei2]); s.flush()
    boulder = _fact(s, fam, arjun.id, arjun.id, "started bouldering", predicate="started", call_id=call.id, utterance_id=u_arjun.id)
    intern = _fact(s, fam, arjun.id, mei.id, "got the internship", call_id=call.id, utterance_id=u_mei.id)
    climb = _fact(s, fam, mei.id, mei.id, "went climbing with Lin", call_id=call.id, utterance_id=u_mei2.id)
    story = m.Storyline(family_id=fam, slug="s_job", owner_id=arjun.id, title="job search")
    s.add(story); s.flush()
    st_fact = _fact(s, fam, arjun.id, arjun.id, "applied to Acme", predicate="state", storyline_id=story.id)
    s.add(m.StorylineState(storyline_id=story.id, seq=1, label="applied", fact_id=st_fact.id, at=T0)); s.flush()
    state_id = s.scalars(select(m.StorylineState.id)).one()
    # a tie fact whose subject is the owner, not Arjun (apply.place_person writes these)
    friend = _fact(s, fam, mei.id, mei.id, "Mei's friend Arjun", predicate="tie")
    old_plan = _fact(s, fam, mei.id, mei.id, "plans a gap year", superseded_by=boulder.id)
    group = m.Group(family_id=fam, slug="g_crag", name="crag crew", fact_id=boulder.id)
    shoes = m.Thing(family_id=fam, slug="th_shoes", kind="thing", name="climbing shoes", owner_id=arjun.id)
    s.add_all([group, shoes]); s.flush()
    msg = m.Message(family_id=fam, author_id=arjun.id, from_number="+15125550101", received_at=T0, fact_ids=[boulder.id],
                    reply="Nice, you started bouldering")
    s.add(msg); s.flush()
    s.add_all([
        m.Tie(family_id=fam, src_person=arjun.id, dst_person=mei.id, kind="friend"),
        m.Tie(family_id=fam, src_person=mei.id, dst_person=arjun.id, kind="friend", fact_id=friend.id),
        m.FactRef(fact_id=friend.id, kind="person", ref_id=arjun.id),
        m.Edge(family_id=fam, src_person=arjun.id, dst_person=mei.id, relation="sibling", fact_id=boulder.id),
        m.GroupMember(group_id=group.id, person_id=arjun.id, fact_id=boulder.id),
        m.FactRef(fact_id=climb.id, kind="thing", ref_id=shoes.id),
        m.FactRef(fact_id=climb.id, kind="group", ref_id=group.id),
        m.Knowledge(knower_id=mei.id, item_kind="thing", item_id=shoes.id, p=0.9, half_life_days=7, first_at=T0, last_at=T0, last_day="2026-09-14"),
        m.Knowledge(knower_id=mei.id, item_kind="group", item_id=group.id, p=0.9, half_life_days=7, first_at=T0, last_at=T0, last_day="2026-09-14"),
        m.GlossaryEntry(family_id=fam, card={"k": "got the internship"}, utterance_id=u_mei.id),
        m.Tie(family_id=fam, src_person=mei.id, dst_person=lin.id, kind="friend", fact_id=climb.id),
        m.Alias(person_id=arjun.id, alias="Arjun", lang="en"),
        m.FactAudience(fact_id=boulder.id, person_id=priya.id, via="told", at=T0),
        m.FactAudience(fact_id=climb.id, person_id=arjun.id, via="heard", at=T0),
        m.FactRef(fact_id=climb.id, kind="person", ref_id=lin.id),
        m.FactRef(fact_id=climb.id, kind="person", ref_id=arjun.id),
        m.Knowledge(knower_id=arjun.id, item_kind="person", item_id=lin.id, p=0.9, half_life_days=7, first_at=T0, last_at=T0, last_day="2026-09-14"),
        m.Knowledge(knower_id=mei.id, item_kind="person", item_id=arjun.id, p=0.9, half_life_days=7, first_at=T0, last_at=T0, last_day="2026-09-14"),
        m.Knowledge(knower_id=priya.id, item_kind="fact", item_id=boulder.id, p=0.9, half_life_days=7, first_at=T0, last_at=T0, last_day="2026-09-14"),
        m.Knowledge(knower_id=mei.id, item_kind="state", item_id=state_id, p=0.9, half_life_days=7, first_at=T0, last_at=T0, last_day="2026-09-14"),
        m.CardLog(call_id=call.id, listener_id=arjun.id, kind="who", key="p_lin", fact_ids=[climb.id], at=T0),
        m.CardLog(call_id=call.id, listener_id=priya.id, target_id=mei.id, kind="bridge", key="b", fact_ids=[boulder.id], at=T0),
        m.CardLog(call_id=call.id, listener_id=mei.id, kind="who", key="p_lin", fact_ids=[climb.id], at=T0),
        m.CallParticipant(call_id=call.id, person_id=arjun.id, identity=f"p{arjun.id}", lang="en", joined_at=T0),
        m.CallParticipant(call_id=call.id, person_id=mei.id, identity=f"p{mei.id}", lang="zh", joined_at=T0),
        m.Mastery(learner_id=arjun.id, lemma="x"),
        m.Consent(person_id=arjun.id),
        m.GlossaryEntry(family_id=fam, card={"k": 1}, speaker_id=arjun.id),
        m.GlossaryEntry(family_id=fam, card={"k": 2}, utterance_id=u_arjun.id),
    ])
    s.flush()
    return dict(mei=mei.id, arjun=arjun.id, priya=priya.id, lin=lin.id, call=call.id, u_mei2=u_mei2.id, u_mei=u_mei.id,
                facts=[boulder.id, intern.id, st_fact.id, friend.id], climb=climb.id, old_plan=old_plan.id,
                texts=["started bouldering", "got the internship", "applied to Acme", "我开始抱石了", "friend Arjun",
                       "实习", "climbing shoes", "crag crew"])


def _people_refs(s, pid, fact_ids, texts):
    """Every row anywhere that still names the person, one of their facts, or their facts' text."""
    hits = []
    for t in m.Base.metadata.sorted_tables:
        people_cols = [c for c in t.columns if any(fk.column.table.name == "people" for fk in c.foreign_keys)]
        if t.name == "people":
            people_cols.append(t.c.id)
        fact_cols = [c for c in t.columns if any(fk.column.table.name == "facts" for fk in c.foreign_keys)]
        if t.name == "facts":
            fact_cols.append(t.c.id)
        for row in s.execute(select(t)).mappings():
            hits += [(t.name, c.name) for c in people_cols if row[c.name] == pid]
            hits += [(t.name, c.name) for c in fact_cols if row[c.name] in fact_ids]
            for c in t.columns:
                v = row[c.name]
                if isinstance(c.type, JSON) and isinstance(v, list):
                    ids = set(x for x in v if isinstance(x, int))
                    if (c.name in JSON_ID_COLS and pid in ids) or (c.name == "fact_ids" and ids & set(fact_ids)):
                        hits.append((t.name, c.name))
                if isinstance(c.type, JSON) and isinstance(v, (dict, list)):
                    v = json.dumps(v, ensure_ascii=False)
                if isinstance(c.type, (String, Text, JSON)) and isinstance(v, str) and any(x in v for x in texts):
                    hits.append((t.name, c.name, "text"))
        if t.name == "knowledge":
            hits += [("knowledge", "item")] * len([r for r in s.execute(select(t)).mappings()
                                                    if (r["item_kind"] == "person" and r["item_id"] == pid)
                                                    or (r["item_kind"] == "fact" and r["item_id"] in fact_ids)])
        if t.name == "fact_refs":
            hits += [("fact_refs", "ref_id")] * len([r for r in s.execute(select(t)).mappings()
                                                     if r["kind"] == "person" and r["ref_id"] == pid])
    # thing/group pointers are plain ints: any that outlive their row would attach to the next row with that id
    live = {"thing": set(s.scalars(select(m.Thing.id))), "group": set(s.scalars(select(m.Group.id)))}
    hits += [("knowledge", "dangling")] * len([k for k in s.scalars(select(m.Knowledge))
                                                if k.item_kind in live and k.item_id not in live[k.item_kind]])
    hits += [("fact_refs", "dangling")] * len([r for r in s.scalars(select(m.FactRef))
                                                if r.kind in live and r.ref_id not in live[r.kind]])
    return hits


def test_delete_person_leaves_no_reference_anywhere(db):
    with session_scope() as s:
        w = _world(s)
    with session_scope() as s:
        counts = privacy.delete_person(s, w["arjun"])
        assert counts["people"] == 1 and counts["facts"] == 4 and counts["users"] == 1
    with session_scope() as s:
        assert _people_refs(s, w["arjun"], w["facts"], w["texts"]) == []
        assert not s.scalars(select(m.Knowledge).where(m.Knowledge.item_kind == "state")).all()
        # other people's lines survive with the deleted listener unset and the deleted id out of the audience
        u = s.get(m.Utterance, w["u_mei2"])
        assert u.src_text == "I went climbing with Lin" and u.listener_id is None and u.audience == []
        assert s.get(m.Call, w["call"]).participants == [w["mei"]]
        assert s.get(m.Fact, w["climb"]) is not None and s.get(m.Person, w["mei"]) is not None
        assert len(s.scalars(select(m.CardLog)).all()) == 1  # Mei's own Lin card stays
        assert s.get(m.Fact, w["old_plan"]).superseded_by is None
        assert not s.scalars(select(m.Edge)).all() and not s.scalars(select(m.Group)).all() and not s.scalars(select(m.Thing)).all()
        red = s.get(m.Utterance, w["u_mei"])
        assert (red.src_text, red.grounded_spans, red.cards, red.sensitive_topic) == ("", [], [], "")


def test_delete_person_removes_states_of_owned_storylines_without_a_storyline_fact(db):
    """A state whose fact is not in the storyline (or not the owner's) still goes with the storyline."""
    with session_scope() as s:
        w = _world(s)
        story = s.scalars(select(m.Storyline)).one()
        stray = _fact(s, story.family_id, w["mei"], w["mei"], "Mei heard about it")
        s.add(m.StorylineState(storyline_id=story.id, seq=2, label="offer", fact_id=stray.id, at=T0)); s.flush()
        sid = s.scalars(select(m.StorylineState.id).where(m.StorylineState.seq == 2)).one()
        s.add(m.Knowledge(knower_id=w["priya"], item_kind="state", item_id=sid, p=0.9, half_life_days=7, first_at=T0,
                          last_at=T0, last_day="2026-09-14"))
    with session_scope() as s:
        privacy.delete_person(s, w["arjun"])
    with session_scope() as s:
        assert not s.scalars(select(m.StorylineState)).all()
        assert not s.scalars(select(m.Knowledge).where(m.Knowledge.item_kind == "state")).all()


def test_delete_account_is_delete_person(db):
    with session_scope() as s:
        w = _world(s)
    with session_scope() as s:
        user = s.scalars(select(m.User).where(m.User.person_id == w["mei"])).one()
        privacy.delete_account(s, user)
    with session_scope() as s:
        assert _people_refs(s, w["mei"], [w["climb"]], ["went climbing with Lin"]) == []
        # Lin was only in Mei's facts: gone now, not at the next sweep
        assert s.get(m.Person, w["lin"]) is None
        assert not s.scalars(select(m.Alias).where(m.Alias.person_id == w["lin"])).all()


def test_delete_fact_only_by_owner_and_redacts_its_line(db):
    with session_scope() as s:
        w = _world(s)
    with session_scope() as s:
        with pytest.raises(PermissionError):
            privacy.delete_fact(s, w["climb"], w["priya"])
        with pytest.raises(PermissionError):
            privacy.delete_fact(s, w["climb"], w["arjun"])  # heard it, does not own it
        privacy.delete_fact(s, w["climb"], w["mei"])
    with session_scope() as s:
        assert s.get(m.Fact, w["climb"]) is None
        assert s.get(m.Utterance, w["u_mei2"]).src_text == ""
        assert all(w["climb"] not in c.fact_ids for c in s.scalars(select(m.CardLog)))
        assert not s.scalars(select(m.Tie).where(m.Tie.dst_person == w["lin"])).all()  # tie born from the fact
        boulder = w["facts"][0]
        privacy.delete_fact(s, boulder, w["arjun"])
    with session_scope() as s:
        msg = s.scalars(select(m.Message)).one()
        assert msg.fact_ids == [] and msg.reply == ""  # the ack restated the deleted news


def _story(s, fam, owner, title, labels):
    """A storyline owned by `owner` with one state per label, each newer one superseding the one before (apply's
    progression). Returns (storyline id, [fact ids])."""
    story = m.Storyline(family_id=fam, slug=f"s_{title[:4]}", owner_id=owner, title=title, keys=[["internship", "实习"]])
    s.add(story); s.flush()
    fids = []
    for seq, label in enumerate(labels, start=1):
        f = _fact(s, fam, owner, owner, label, predicate="state", storyline_id=story.id, said_at=T0 + timedelta(days=seq))
        s.add(m.StorylineState(storyline_id=story.id, seq=seq, label=label, fact_id=f.id, at=f.said_at)); s.flush()
        if fids:
            old = s.get(m.Fact, fids[-1])
            old.status, old.superseded_by = "superseded", f.id
            for st in s.scalars(select(m.StorylineState).where(m.StorylineState.fact_id == old.id)):
                st.status = "superseded"
        fids.append(f.id)
    s.flush()
    return story.id, fids


def test_deleting_every_fact_of_a_storyline_deletes_the_storyline(db):
    with session_scope() as s:
        _, arjun, _ = create_user(s, "Arjun", "en")
        story, fids = _story(s, arjun.family_id, arjun.id, "Google internship", ["applied", "offer"])
        kept, kept_fids = _story(s, arjun.family_id, arjun.id, "moving", ["looking"])
        cited = m.Storyline(family_id=arjun.family_id, slug="s_cited", owner_id=arjun.id, title="cited")
        s.add(cited); s.flush()
        loose = _fact(s, arjun.family_id, arjun.id, arjun.id, "cited, no state", storyline_id=cited.id)
        s.add(m.StorylineState(storyline_id=cited.id, seq=1, label="x", fact_id=kept_fids[0], at=T0)); s.flush()
        ids = dict(arjun=arjun.id, story=story, fids=fids, kept=kept, cited=cited.id, loose=loose.id, kf=kept_fids[0])
    with session_scope() as s:
        privacy.delete_fact(s, ids["fids"][1], ids["arjun"])
        assert s.get(m.Storyline, ids["story"]) is not None  # "applied" is still there
        privacy.delete_fact(s, ids["fids"][0], ids["arjun"])
        assert s.get(m.Storyline, ids["story"]) is None  # no title or keys left behind
        privacy.delete_fact(s, ids["kf"], ids["arjun"])  # last state of "cited", but a fact still names it
        assert s.get(m.Storyline, ids["cited"]) is not None and s.get(m.Fact, ids["loose"]) is not None
        assert s.get(m.Storyline, ids["kept"]) is None


def test_deleting_a_founding_fact_takes_its_words_out_of_the_storyline(db):
    """The title, keys and slug came from the founding (first) state's fact: deleted means gone from them too."""
    with session_scope() as s:
        _, arjun, _ = create_user(s, "Arjun", "en")
        story, fids = _story(s, arjun.family_id, arjun.id, "Google internship", ["applied", "second round", "offer"])
        s.get(m.Storyline, story).slug = f"s_google_internship_{story}"
        s.get(m.Fact, fids[1]).keys = [["interview"]]
        lone, (lone_fid,) = _story(s, arjun.family_id, arjun.id, "Acme job", ["applied"])
        ids = dict(arjun=arjun.id, story=story, fids=fids, lone=lone, lone_fid=lone_fid)
    with session_scope() as s:
        privacy.delete_fact(s, ids["fids"][0], ids["arjun"])
    with session_scope() as s:
        st = s.get(m.Storyline, ids["story"])
        assert (st.title, st.keys, st.slug) == ("second round", [["interview"]], f"s_second_round_{ids['story']}")
        privacy.delete_fact(s, ids["fids"][2], ids["arjun"])  # not the founding one: the title stays
    with session_scope() as s:
        assert s.get(m.Storyline, ids["story"]).title == "second round"
        privacy.delete_fact(s, ids["lone_fid"], ids["arjun"])
        assert s.get(m.Storyline, ids["lone"]) is None  # no state left


def test_deleting_a_correction_restores_what_it_superseded(db):
    with session_scope() as s:
        _, arjun, _ = create_user(s, "Arjun", "en")
        story, (applied, offer) = _story(s, arjun.family_id, arjun.id, "Google internship", ["applied", "offer"])
        ids = dict(arjun=arjun.id, applied=applied, offer=offer)
    with session_scope() as s:
        assert s.get(m.Fact, ids["applied"]).status == "superseded"
        counts = privacy.delete_fact(s, ids["offer"], ids["arjun"])
        assert counts["facts_restored"] == 1
    with session_scope() as s:
        f = s.get(m.Fact, ids["applied"])
        assert (f.status, f.superseded_by) == ("active", None)
        st = s.scalars(select(m.StorylineState).where(m.StorylineState.fact_id == ids["applied"])).one()
        assert st.status == "active"


def test_sweep_expires_third_party_facts_and_orphans_but_keeps_pinned(db):
    with session_scope() as s:
        _, mei, _ = create_user(s, "Mei", "zh")
        fam = mei.family_id
        lin = m.Person(family_id=fam, slug="p_lin_1", display_name="Lin")
        bo = m.Person(family_id=fam, slug="p_bo_2", display_name="Bo")
        s.add_all([lin, bo]); s.flush()
        old = T0 - timedelta(days=121)
        f_lin = _fact(s, fam, lin.id, mei.id, "climbs at Fudan", third_party=True, said_at=old, expires_at=old + timedelta(days=120))
        f_bo = _fact(s, fam, bo.id, mei.id, "is Mei's coach", third_party=True, said_at=old, expires_at=old + timedelta(days=120),
                     pinned=True)
        s.add(m.Tie(family_id=fam, src_person=mei.id, dst_person=lin.id, kind="friend", fact_id=f_lin.id))
        ids = dict(lin=lin.id, bo=bo.id, mei=mei.id, f_lin=f_lin.id, f_bo=f_bo.id)
    with session_scope() as s:
        counts = privacy.sweep_expired(s, T0)
        assert counts["facts"] == 1 and counts["orphans"] == 1
    with session_scope() as s:
        assert s.get(m.Person, ids["lin"]) is None and s.get(m.Fact, ids["f_lin"]) is None
        assert s.get(m.Person, ids["bo"]) is not None and s.get(m.Fact, ids["f_bo"]) is not None
        assert s.get(m.Person, ids["mei"]) is not None  # users are never swept
        assert privacy.sweep_expired(s, T0) == {"orphans": 0}


def test_sweep_never_touches_the_legacy_family(db):
    with session_scope() as s:
        fam = m.Family(name="Krishnan", heritage_lang="ta")
        s.add(fam); s.flush()
        s.add(m.Person(family_id=fam.id, slug="p_lonely", display_name="Lonely"))
    with session_scope() as s:
        assert privacy.sweep_expired(s, T0)["orphans"] == 0


def test_forget_person_drops_my_facts_then_the_orphan(db):
    with session_scope() as s:
        w = _world(s)
        with pytest.raises(PermissionError):
            privacy.forget_person(s, w["arjun"], w["mei"])  # users are not forgettable
        r = privacy.forget_person(s, w["lin"], w["mei"])
        assert r == {"deleted_facts": 1, "person_deleted": True}
    with session_scope() as s:
        assert s.get(m.Person, w["lin"]) is None and s.get(m.Fact, w["climb"]) is None


def test_commit_and_checkpoint_truncates_the_wal(db, tmp_path, monkeypatch, caplog):
    calls = []
    real = privacy._wal_checkpoint
    monkeypatch.setattr(privacy, "_wal_checkpoint", lambda s: calls.append(s) or real(s))
    with session_scope() as s:
        w = _world(s)
    with session_scope() as s:
        privacy.delete_person(s, w["arjun"])
        assert privacy.commit_and_checkpoint(s) is True
        assert calls == [s]
    assert (tmp_path / "test.db-wal").stat().st_size == 0
    privacy.run_sweep()
    assert len(calls) == 2
    # a reader elsewhere keeps the WAL from truncating: report it, never pretend
    monkeypatch.setattr(privacy, "_wal_checkpoint", lambda s: 1)
    with session_scope() as s:
        assert privacy.commit_and_checkpoint(s) is False
    assert "WAL checkpoint busy" in caplog.text
