"""World extraction, validator and apply (docs/ARCHITECTURE.md 6.1-6.4, 2.5). Offline: the LLM is an httpx mock."""
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import func, select

from app import llm as llm_mod
from app.db import models as m
from app.db.session import init_db, session_scope
from app.graph.kinship import FamilyGraph
from app.world import apply as ap
from app.world import extract as ex
from app.world import privacy
from app.world.contracts import WorldUpdateOut
from app.world.users import create_user

T0 = datetime(2026, 9, 14, 10, tzinfo=timezone.utc)
LIN_LINE = "我和林是在复旦攀岩墙认识的"


def _llm(payload=None, status=200, seen=None):
    def handler(req: httpx.Request):
        body = json.loads(req.content)
        if seen is not None:
            seen.append(body)
        assert body["response_format"]["json_schema"]["name"] == "WorldUpdateOut"
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "boom"}})
        return httpx.Response(200, json={"id": "x", "object": "chat.completion", "created": 0, "model": "m",
                                         "choices": [{"index": 0, "finish_reason": "stop",
                                                      "message": {"role": "assistant", "content": json.dumps(payload)}}],
                                         "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})
    return llm_mod.LLM(api_key="k", base_url="https://api.meta.ai/v1", model="m", transport=httpx.MockTransport(handler))


def fact(subject, text, lines, predicate="did", refs=(), **kw):
    d = {"subject": subject, "predicate": predicate, "text_en": text, "text_src": kw.pop("text_src", ""), "keys": [],
         "refs": list(refs), "lines": list(lines), "sensitive_kind": "", "same_as": None, "contradicts": None, "storyline": None}
    d.update(kw)
    return d


def story(title, label, existing_id=None, resolved=False):
    return {"existing_id": existing_id, "title": title, "state_label": label, "resolved": resolved}


LIN = {"ref": "e1", "name": "Lin", "native": "林", "forms": ["林", "Lin", "Lynn"], "kind": "person", "existing_id": None}
CALL1 = {"entities": [LIN],
         "ties": [{"a": "speaker", "b": "e1", "kind": "friend", "context": "from the Fudan climbing wall"}],
         "facts": [fact("speaker", "Lin is Mei's friend from the Fudan climbing wall", [1], predicate="tie", refs=["e1"],
                        text_src=LIN_LINE, keys=[["climbing", "攀岩"]])]}


@pytest.fixture
def w():
    init_db()
    with session_scope() as s:
        _, mei, _ = create_user(s, "Mei", "zh")
        _, arjun, _ = create_user(s, "Arjun", "en")
        _, priya, _ = create_user(s, "Priya", "en")
        call = m.Call(family_id=mei.family_id, mode="world")
        s.add(call)
        s.flush()
        ids = dict(space=mei.family_id, mei=mei.id, arjun=arjun.id, priya=priya.id, call=call.id,
                   mei_slug=mei.slug, arjun_slug=arjun.slug)
    return ids


def _window(s, w, lines, at=T0):
    """lines: [(speaker key, text)] -> (Line list, ApplyCtx), utterances stored at `at`; audience = the other two."""
    people = {k: w[k] for k in ("mei", "arjun")}
    out, utt = [], {}
    for n, (who, text) in enumerate(lines, start=1):
        u = m.Utterance(call_id=w["call"], speaker_id=people[who], src_text=text, created_at=at)
        s.add(u)
        s.flush()
        utt[n] = u.id
        out.append(ex.Line(n, people[who], "zh" if who == "mei" else "en", text))
    sp = {ln.n: ln.speaker_id for ln in out}
    aud = {ln.n: [p for p in people.values() if p != ln.speaker_id] for ln in out}
    return out, ap.ApplyCtx(w["space"], w["call"], None, sp, aud, utt, at)


def _parts(w):
    return [ex.Participant(w["mei"], w["mei_slug"], "Mei", "zh"), ex.Participant(w["arjun"], w["arjun_slug"], "Arjun", "en")]


def _run(s, w, lines, payload, at=T0, own=None, flag_users=True):
    window, ctx = _window(s, w, lines, at)
    own = own or {w["mei"]: ex.own_context(s, w["mei"]), w["arjun"]: ex.own_context(s, w["arjun"])}
    known = [ex.Candidate("person", p.id, p.slug, p.display_name, flag_users and ap._is_user(s, p.id))
             for p in s.scalars(select(m.Person)) if p.id not in (w["mei"], w["arjun"])]
    known += [ex.Candidate("thing", t.id, t.slug, t.name, False) for t in s.scalars(select(m.Thing))]
    cands = {w["mei"]: known, w["arjun"]: known}
    upd = ex.run_extraction(_llm(payload), w["call"], window, _parts(w), own, cands, ["zh", "en"])
    clean, dropped = ex.validate(upd, ex.validate_ctx(window, _parts(w), own, cands))
    return ap.apply_update(s, clean, ctx), dropped


def _aud(s, fid):
    return dict(s.execute(select(m.FactAudience.person_id, m.FactAudience.via).where(m.FactAudience.fact_id == fid)).all())


def test_call1_creates_lin_with_translit_aliases_tie_and_audience(w):
    with session_scope() as s:
        res, dropped = _run(s, w, [("mei", LIN_LINE)], CALL1)
        assert dropped == []
        lin = s.get(m.Person, res.entities["e1"])
        assert lin.slug == f"p_lin_{lin.id}" and lin.lang_name == "林"
        assert {(a.alias, a.kind) for a in lin.aliases} >= {("林", "translit"), ("Lin", "translit"), ("Lynn", "translit")}
        assert next(a.lang for a in lin.aliases if a.alias == "林") == "zh"
        tie = s.scalars(select(m.Tie)).one()
        assert (tie.src_person, tie.dst_person, tie.kind) == (w["mei"], lin.id, "friend") and tie.fact_id == res.facts[0]
        f = s.get(m.Fact, res.facts[0])
        # Mei is the subject, but the fact is about Lin, a third party: it expires (PRODUCT hard rule)
        assert (f.subject_id, f.speaker_id, f.third_party, f.text_src) == (w["mei"], w["mei"], True, LIN_LINE)
        assert f.expires_at == T0 + timedelta(days=120)
        assert _aud(s, f.id) == {w["mei"]: "said", w["arjun"]: "heard"}
        assert s.scalar(select(m.FactRef.ref_id).where(m.FactRef.fact_id == f.id)) == lin.id
        assert (w["mei"], "fact", f.id, "said") in res.evidence and (w["arjun"], "person", lin.id, "heard") in res.evidence


def test_prompt_is_privacy_scoped_and_uses_call_cache_key(w):
    with session_scope() as s:
        s.add(m.Fact(family_id=w["space"], subject_id=w["arjun"], speaker_id=w["arjun"], predicate="started",
                     text="started bouldering", lang="en", source_kind="message", said_at=T0, shareable=False))
        s.flush()
        window, _ = _window(s, w, [("mei", LIN_LINE)])
        own = {w["mei"]: ex.own_context(s, w["mei"]), w["arjun"]: ex.own_context(s, w["arjun"])}
        assert own[w["arjun"]].facts and not own[w["mei"]].facts
        seen = []
        ex.run_extraction(_llm(CALL1, seen=seen), w["call"], window, _parts(w), own, {}, ["zh", "en"])
        user = seen[0]["messages"][-1]["content"]
        assert "started bouldering" not in user  # Arjun did not speak in this window: his facts stay out
        assert seen[0]["prompt_cache_key"] == f"kin-world-{w['call']}" and seen[0]["max_completion_tokens"] == 4000
        assert seen[0]["reasoning_effort"] == "low" and user.rstrip().endswith(LIN_LINE)


def test_fact_citing_line_outside_window_is_dropped(w):
    payload = {"entities": [], "ties": [], "facts": [fact("speaker", "likes tea", [7])]}
    with session_scope() as s:
        res, dropped = _run(s, w, [("mei", "我喜欢茶")], payload)
        assert res.facts == [] and "outside the window" in dropped[0]
        assert s.scalar(select(func.count(m.Fact.id))) == 0


def test_fact_about_arjun_from_meis_line_is_dropped(w):
    payload = {"entities": [], "ties": [], "facts": [fact(w["arjun_slug"], "Arjun started bouldering", [1])]}
    with session_scope() as s:
        res, dropped = _run(s, w, [("mei", "Arjun 开始抱石了")], payload)
        assert res.facts == [] and "about user" in dropped[0]


def test_existing_id_outside_candidates_and_bad_same_as_are_dropped(w):
    with session_scope() as s:
        bogus = dict(LIN, existing_id=w["arjun"])  # a participant, not in the candidate list
        payload = {"entities": [bogus], "ties": [], "facts": [fact("speaker", "x", [1], same_as=999)]}
        res, dropped = _run(s, w, [("mei", "hi")], payload)
        assert res.facts == [] and len(dropped) == 2
        assert "not in the candidate list" in dropped[0] and "same_as=999" in dropped[1]


def test_same_as_merges_audience(w):
    with session_scope() as s:
        f = m.Fact(family_id=w["space"], subject_id=w["arjun"], speaker_id=w["arjun"], predicate="started",
                   text="started bouldering", lang="en", source_kind="message", said_at=T0, shareable=False)
        s.add(f)
        s.flush()
        s.add(m.FactAudience(fact_id=f.id, person_id=w["arjun"], via="authored", at=T0))
        s.flush()
        payload = {"entities": [], "ties": [], "facts": [fact("speaker", "started bouldering", [1], same_as=f.id)]}
        res, dropped = _run(s, w, [("arjun", "I started bouldering")], payload, at=T0 + timedelta(days=42))
        assert dropped == [] and res.facts == [f.id]
        assert s.scalar(select(func.count(m.Fact.id))) == 1
        assert _aud(s, f.id) == {w["arjun"]: "authored", w["mei"]: "heard"}


def test_owner_progression_supersedes_previous_state(w):
    with session_scope() as s:
        r1, _ = _run(s, w, [("mei", "我投了简历")], {"entities": [], "ties": [], "facts": [
            fact("speaker", "applied for jobs", [1], predicate="state", keys=[["job", "工作"], ["apply", "投简历"]],
                 storyline=story("job search", "applied"))]})
        sid = s.get(m.Fact, r1.facts[0]).storyline_id
        r2, dropped = _run(s, w, [("mei", "我进了第二轮")], {"entities": [], "ties": [], "facts": [
            fact("speaker", "in the second round", [1], predicate="state", storyline=story("job search", "second round", sid))]},
            at=T0 + timedelta(days=30))
        assert dropped == []
        old, new = s.get(m.Fact, r1.facts[0]), s.get(m.Fact, r2.facts[0])
        assert new.storyline_id == sid and (old.status, old.superseded_by) == ("superseded", new.id)
        states = s.scalars(select(m.StorylineState).where(m.StorylineState.storyline_id == sid).order_by(m.StorylineState.seq)).all()
        assert [(x.label, x.status) for x in states] == [("applied", "superseded"), ("second round", "active")]
        st_id = states[1].id
        assert (w["arjun"], "state", st_id, "heard") in r2.evidence
        # a forgotten id is matched by title; a terminal label resolves the thread
        r3, _ = _run(s, w, [("mei", "我接受了offer")], {"entities": [], "ties": [], "facts": [
            fact("speaker", "accepted the offer", [1], predicate="state", storyline=story("Job search!", "offer accepted"))]},
            at=T0 + timedelta(days=40))
        f3 = s.get(m.Fact, r3.facts[0])
        assert f3.storyline_id == sid and f3.status == "resolved" and s.get(m.Storyline, sid).status == "resolved"


def test_contradiction_from_non_subject_marks_both_and_unresolved(w):
    with session_scope() as s:
        r1, _ = _run(s, w, [("mei", LIN_LINE)], CALL1)
        lin = s.get(m.Person, r1.entities["e1"])
        r2, _ = _run(s, w, [("mei", "林搬到北京了")], {"entities": [], "ties": [], "facts": [
            fact(lin.slug, "moved to Beijing", [1], predicate="lives_in", storyline=story("Lin's move", "moved to Beijing"))]},
            at=T0 + timedelta(days=1))
        beijing = s.get(m.Fact, r2.facts[0])
        own = {w["mei"]: ex.own_context(s, w["mei"])}
        assert beijing.id in dict(own[w["mei"]].facts)
        r3, dropped = _run(s, w, [("mei", "林还在上海")], {"entities": [], "ties": [], "facts": [
            fact(lin.slug, "still in Shanghai", [1], predicate="lives_in", contradicts=beijing.id,
                 storyline=story("Lin's move", "still in Shanghai", beijing.storyline_id))]},
            at=T0 + timedelta(days=2), own=own)
        assert dropped == []
        shanghai = s.get(m.Fact, r3.facts[0])
        assert beijing.status == "contradicted" and shanghai.status == "contradicted"
        assert s.get(m.Storyline, beijing.storyline_id).unresolved is True


def test_contradiction_by_subject_supersedes(w):
    with session_scope() as s:
        r1, _ = _run(s, w, [("mei", "我住在上海")], {"entities": [], "ties": [], "facts": [
            fact("speaker", "lives in Shanghai", [1], predicate="lives_in")]})
        r2, _ = _run(s, w, [("mei", "我搬到北京了")], {"entities": [], "ties": [], "facts": [
            fact("speaker", "lives in Beijing", [1], predicate="lives_in", contradicts=r1.facts[0])]}, at=T0 + timedelta(days=3))
        old = s.get(m.Fact, r1.facts[0])
        assert (old.status, old.superseded_by) == ("superseded", r2.facts[0])
        assert s.get(m.Fact, r2.facts[0]).status == "active"


def test_sensitive_fact_stored_as_topic_word(w):
    payload = {"entities": [], "ties": [], "facts": [
        fact("speaker", "knee surgery next week", [1], text_src="下周膝盖手术", keys=[["knee", "膝盖"]], sensitive_kind="health")]}
    with session_scope() as s:
        res, _ = _run(s, w, [("mei", "下周膝盖手术")], payload)
        f = s.get(m.Fact, res.facts[0])
        assert (f.text, f.text_src, f.keys, f.sensitive_kind) == ("health", "", [], "health")
        assert s.get(m.Utterance, f.utterance_id).sensitive_topic == "health"


def test_third_party_fact_expires_after_ttl(w):
    with session_scope() as s:
        r1, _ = _run(s, w, [("mei", LIN_LINE)], CALL1)
        lin = s.get(m.Person, r1.entities["e1"])
        res, _ = _run(s, w, [("mei", "林开始学吉他")], {"entities": [], "ties": [], "facts": [
            fact(lin.slug, "started guitar", [1], predicate="started")]}, at=T0 + timedelta(days=5))
        f = s.get(m.Fact, res.facts[0])
        assert f.third_party and f.said_at == T0 + timedelta(days=5)
        assert f.expires_at == f.said_at + timedelta(days=120)


def test_llm_error_returns_none_and_writes_nothing(w, caplog):
    with session_scope() as s:
        window, _ = _window(s, w, [("mei", LIN_LINE)])
        assert ex.run_extraction(_llm(status=500), w["call"], window, _parts(w), {}, {}, ["zh"]) is None
        assert ex.run_extraction(_llm({"entities": "nope"}), w["call"], window, _parts(w), {}, {}, ["zh"]) is None
        assert s.scalar(select(func.count(m.Fact.id))) == 0 and s.scalar(select(func.count(m.Person.id))) == 3
    assert f"call {w['call']}" in caplog.text


def test_place_person_social_tie(w):
    with session_scope() as s:
        lin, ev = ap.place_person(s, w["space"], w["arjun"], "Lin", w["mei"], "friend", "from climbing",
                                  [w["mei"]], now=T0, call_id=w["call"])
        tie = s.scalars(select(m.Tie)).one()
        assert (tie.src_person, tie.dst_person, tie.kind) == (w["mei"], lin.id, "friend")
        f = s.get(m.Fact, tie.fact_id)
        assert (f.source_kind, f.subject_id, f.speaker_id, f.predicate) == ("card", w["mei"], w["arjun"], "tie")
        assert set(_aud(s, f.id)) == {w["arjun"], w["mei"], lin.id}
        assert ev == [(w["arjun"], "person", lin.id, "confirmed")]
        again, _ = ap.place_person(s, w["space"], w["arjun"], "lin", w["priya"], "classmate", now=T0)
        assert again.id == lin.id


def test_link_kin_attaches_existing_paatti_through_placeholder_mom(w):
    with session_scope() as s:
        paatti = ap._new_person(s, w["space"], "Paatti")
        n_people = s.scalar(select(func.count(m.Person.id)))
        person, ev = ap.place_person(s, w["space"], w["arjun"], "", w["arjun"], "mother.mother", person=paatti.slug, now=T0)
        assert person.id == paatti.id
        assert s.scalar(select(func.count(m.Person.id))) == n_people + 1  # only the placeholder Mom
        assert s.scalar(select(func.count(m.Person.id)).where(m.Person.display_name == "Paatti")) == 1
        edges = s.scalars(select(m.Edge)).all()
        mom = next(e.src_person for e in edges if e.dst_person == w["arjun"])
        assert s.get(m.Person, mom).display_name == "Mom"
        assert any(e.src_person == paatti.id and e.dst_person == mom and e.relation == "parent" for e in edges)
        assert all(e.fact_id is not None for e in edges)
        assert set(_aud(s, edges[0].fact_id)) == {w["arjun"], paatti.id}
        assert ev == [(w["arjun"], "person", paatti.id, "confirmed")]
        # a relative who does not exist yet goes through builder.add_relative
        ravi, _ = ap.link_kin(s, w["space"], w["arjun"], "mother.younger_brother", None, me=w["arjun"], name="Ravi", now=T0)
        assert ravi.display_name == "Ravi" and s.scalar(select(func.count(m.Person.id)).where(m.Person.display_name == "Mom")) == 1


def test_kin_sibling_becomes_the_child_of_the_anchors_parents(w):
    """Arjun places Paatti as his mother's mother, then Ravi as his mother's younger brother (by slug and by name):
    Paatti must see each as her son, and Arjun's render is unchanged."""
    from app.world.view import WorldView
    with session_scope() as s:
        _, paatti, _ = create_user(s, "Paatti", "ta")
        ap.place_person(s, w["space"], w["arjun"], "", w["arjun"], "mother.mother", person=paatti.slug, now=T0)
        ravi = ap._new_person(s, w["space"], "Ravi")
        ap.place_person(s, w["space"], w["arjun"], "", w["arjun"], "mother.younger_brother", person=ravi.slug, now=T0)
        uma, _ = ap.link_kin(s, w["space"], w["arjun"], "mother.younger_sister", None, me=w["arjun"], name="Uma", now=T0)
        view = WorldView.build(s, w["space"], [w["arjun"], paatti.id], T0)
        assert view.render(paatti.id, ravi.id) == "your son Ravi magan (your son)"  # was plain 'Ravi'
        assert view.render(paatti.id, uma.id).startswith("your daughter Uma")
        assert view.render(w["arjun"], ravi.id) == "your uncle Ravi (Mom's younger brother)"
        assert all(e.fact_id is not None for e in s.scalars(select(m.Edge)))


def test_validate_drops_tie_without_tie_fact_when_two_people_spoke():
    ctx = ex.ValidateCtx({1: 5, 2: 6}, frozenset({5, 6}), {}, frozenset(), {})
    upd = WorldUpdateOut.model_validate({"entities": [LIN], "ties": CALL1["ties"], "facts": []})
    clean, dropped = ex.validate(upd, ctx)
    assert clean.ties == [] and "tie" in dropped[0]
    assert ex.clean_forms(["林", "Lin", "Lin", "Lதin", "", "x" * 41]) == ["林", "Lin"]


def test_fact_about_non_participant_user_is_dropped_by_validator_and_by_apply(w):
    with session_scope() as s:
        priya = s.get(m.Person, w["priya"]).slug
        payload = {"entities": [], "ties": [], "facts": [fact(priya, "Priya is pregnant", [1])]}
        res, dropped = _run(s, w, [("mei", "Priya 怀孕了")], payload)
        assert res.facts == [] and "about user" in dropped[0]
        # the caller forgot is_user: apply still refuses it from the users table
        res, dropped = _run(s, w, [("mei", "Priya 怀孕了")], payload, flag_users=False)
        assert dropped == [] and res.facts == [] and s.scalar(select(func.count(m.Fact.id))) == 0


def test_fact_citing_two_speakers_is_dropped(w):
    payload = {"entities": [], "ties": [], "facts": [fact("speaker", "likes tea", [1, 2])]}
    with session_scope() as s:
        res, dropped = _run(s, w, [("mei", "我喜欢茶"), ("arjun", "me too")], payload)
        assert res.facts == [] and "several speakers" in dropped[0]


def test_sensitive_storyline_keeps_only_the_topic_word(w):
    payload = {"entities": [], "ties": [], "facts": [
        fact("speaker", "knee surgery next week", [1], predicate="state", keys=[["knee", "膝盖"]], sensitive_kind="health",
             storyline=story("knee surgery", "surgery scheduled"))]}
    with session_scope() as s:
        res, _ = _run(s, w, [("mei", "下周膝盖手术")], payload)
        st = s.get(m.Storyline, s.get(m.Fact, res.facts[0]).storyline_id)
        label = s.scalars(select(m.StorylineState.label).where(m.StorylineState.storyline_id == st.id)).one()
        assert (st.title, st.slug, st.keys, label) == ("health", f"s_health_{st.id}", [], "health")


def test_existing_thing_is_not_reowned_by_a_fact(w):
    with session_scope() as s:
        wall = m.Thing(family_id=w["space"], slug="th_wall_1", kind="place", name="Fudan climbing wall")
        s.add(wall)
        s.flush()
        payload = {"entities": [], "ties": [], "facts": [fact("speaker", "climbs at the wall", [1], refs=["th_wall_1"])]}
        res, dropped = _run(s, w, [("mei", "我在攀岩墙")], payload)
        assert dropped == [] and res.facts
        assert (wall.fact_id, wall.owner_id) == (None, None)


def test_tie_without_tie_fact_gets_one_from_a_single_speaker(w):
    payload = {"entities": [LIN], "ties": CALL1["ties"], "facts": []}
    with session_scope() as s:
        res, dropped = _run(s, w, [("mei", LIN_LINE)], payload)
        assert dropped == []
        tie = s.scalars(select(m.Tie)).one()
        f = s.get(m.Fact, tie.fact_id)
        assert (f.predicate, f.subject_id, f.text) == ("tie", w["mei"], "Lin is Mei's friend from the Fudan climbing wall")


def test_tie_to_a_thing_is_dropped(w):
    with session_scope() as s:
        s.add(m.Thing(family_id=w["space"], slug="th_wall_1", kind="place", name="wall"))
        s.flush()
        payload = {"entities": [], "ties": [{"a": "speaker", "b": "th_wall_1", "kind": "friend", "context": ""}], "facts": []}
        res, dropped = _run(s, w, [("mei", "hi")], payload)
        assert res.facts == [] and "bad endpoints" in dropped[0] and s.scalar(select(func.count(m.Tie.id))) == 0


def test_third_party_introduced_by_one_speaker_only(w):
    payload = {"entities": [LIN], "ties": [], "facts": [
        fact("e1", "climbs", [1], predicate="did"), fact("e1", "is pregnant", [2], predicate="attribute")]}
    with session_scope() as s:
        res, dropped = _run(s, w, [("mei", LIN_LINE), ("arjun", "Lin is pregnant")], payload)
        assert len(res.facts) == 1 and "introduced by speaker" in dropped[0]


def test_clean_forms_keeps_diacritics_and_kana_marks():
    assert ex.clean_forms(["Lín", "Pāṭṭi", "Nguyễn", "ユーリ", "佐々木", "สมชาย", "Lin林"]) == \
        ["Lín", "Pāṭṭi", "Nguyễn", "ユーリ", "佐々木", "สมชาย"]


def test_place_person_unknown_slug_raises(w):
    with session_scope() as s:
        with pytest.raises(LookupError):
            ap.place_person(s, w["space"], w["arjun"], "", w["mei"], "friend", person="p_lin_17", now=T0)
        assert s.scalar(select(func.count(m.Person.id))) == 3


def test_lin_introduced_through_a_tie_is_swept_after_the_ttl(w):
    with session_scope() as s:
        res, _ = _run(s, w, [("mei", LIN_LINE)], CALL1)
        lin_id = res.entities["e1"]
        own, _ = _run(s, w, [("arjun", "I like tea")], {"entities": [], "ties": [], "facts": [
            fact("speaker", "likes tea", [1], predicate="likes")]})
        assert s.get(m.Fact, own.facts[0]).expires_at is None  # a user's own fact naming no third party stays
        assert privacy.sweep_expired(s, T0 + timedelta(days=119))["orphans"] == 0
        counts = privacy.sweep_expired(s, T0 + timedelta(days=121))
        assert counts["orphans"] == 1 and s.get(m.Person, lin_id) is None
        assert s.scalar(select(func.count(m.Tie.id))) == 0 and s.get(m.Fact, own.facts[0]) is not None


def test_place_person_tie_to_a_non_user_expires_and_to_a_user_does_not(w):
    with session_scope() as s:
        lin, _ = ap.place_person(s, w["space"], w["arjun"], "Lin", w["mei"], "friend", now=T0)
        arjun, _ = ap.place_person(s, w["space"], w["arjun"], "", w["mei"], "friend", person=w["arjun_slug"], now=T0)
        by_dst = {t.dst_person: s.get(m.Fact, t.fact_id) for t in s.scalars(select(m.Tie))}
        assert by_dst[lin.id].third_party and by_dst[lin.id].expires_at == T0 + timedelta(days=120)
        assert not by_dst[arjun.id].third_party and by_dst[arjun.id].expires_at is None


def test_place_person_tie_is_idempotent_and_refuses_a_self_tie(w):
    with session_scope() as s:
        lin, _ = ap.place_person(s, w["space"], w["arjun"], "Lin", w["mei"], "friend", now=T0)
        again, ev = ap.place_person(s, w["space"], w["arjun"], "Lin", w["mei"], "friend", call_audience=[w["priya"]],
                                    now=T0, call_id=w["call"])  # an iOS retry, this time on a call with Priya
        assert again.id == lin.id and ev == [(w["arjun"], "person", lin.id, "confirmed")]
        tie = s.scalars(select(m.Tie)).one()
        assert s.scalar(select(func.count(m.Fact.id))) == 1
        assert _aud(s, tie.fact_id) == {w["arjun"]: "card", w["mei"]: "told", lin.id: "told", w["priya"]: "heard"}
        _, ev = ap.place_person(s, w["space"], w["priya"], "Lin", w["mei"], "friend", now=T0)  # she heard it: nothing new
        assert ev == [(w["priya"], "person", lin.id, "confirmed")]
        assert s.scalar(select(func.count(m.Tie.id))) == 1 and s.scalar(select(func.count(m.Fact.id))) == 1
        with pytest.raises(ValueError):
            ap.place_person(s, w["space"], w["arjun"], "", w["mei"], "friend", person=w["mei_slug"], now=T0)
        with pytest.raises(ValueError):
            ap.place_person(s, w["space"], w["arjun"], "Mei", w["mei"], "friend", now=T0)
        assert s.scalar(select(func.count(m.Tie.id))) == 1


def test_placing_a_known_tie_never_adds_anyone_to_someone_elses_fact(w):
    """Review rank 1: Priya placing Lin as Mei's friend joined the audience of Mei's own fact (and its source line),
    which only Mei and Arjun heard; so did everyone on Priya's call."""
    with session_scope() as s:
        res, _ = _run(s, w, [("mei", LIN_LINE)], CALL1)
        f1, lin = res.facts[0], s.get(m.Person, res.entities["e1"])
        heard = _aud(s, f1)
        _, mallory, _ = create_user(s, "Mallory", "en")
        args = (s, w["space"], w["priya"], "", w["mei"], "friend")
        ap.place_person(*args, call_audience=[mallory.id], person=lin.slug, now=T0, call_id=w["call"])
        assert _aud(s, f1) == heard
        ties = s.scalars(select(m.Tie).order_by(m.Tie.id)).all()
        mine = s.get(m.Fact, ties[-1].fact_id)
        assert len(ties) == 2 and (mine.speaker_id, mine.source_kind, mine.third_party) == (w["priya"], "card", True)
        assert _aud(s, mine.id) == {w["priya"]: "card", w["mei"]: "told", lin.id: "told", mallory.id: "heard"}
        ap.place_person(*args, person=lin.slug, now=T0)  # Priya's retry finds her own card behind the second tie
        ap.place_person(s, w["space"], w["arjun"], "", w["mei"], "friend", person=lin.slug, now=T0)  # Arjun heard F1
        assert s.scalar(select(func.count(m.Tie.id))) == 2 and _aud(s, f1) == heard


def test_placing_over_an_expired_tie_writes_a_fresh_one(w):
    """Review rank 4: reusing a tie whose fact is past its TTL answered 'confirmed', then the sweep deleted it."""
    with session_scope() as s:
        lin, _ = ap.place_person(s, w["space"], w["arjun"], "Lin", w["mei"], "friend", now=T0)
        later = T0 + timedelta(days=121)
        ap.place_person(s, w["space"], w["arjun"], "Lin", w["mei"], "friend", now=later)
        old, fresh = s.scalars(select(m.Tie).order_by(m.Tie.id)).all()
        assert s.get(m.Fact, fresh.fact_id).expires_at == later + timedelta(days=120)
        privacy.sweep_expired(s, later)
        assert [t.id for t in s.scalars(select(m.Tie))] == [fresh.id] and s.get(m.Person, lin.id) is not None


def test_placed_paatti_renders_as_grandmother_in_each_listeners_language(w):
    """Demo bug 1: Mei (zh) signed up first, so the space is zh, and Paatti was '?' (rendered male)."""
    with session_scope() as s:
        _, paatti, _ = create_user(s, "Paatti", "ta")
        ap.place_person(s, w["space"], w["arjun"], "", w["arjun"], "mother.mother", person=paatti.slug, now=T0)
        assert paatti.gender == "f"
        g = FamilyGraph.from_session(s, w["space"])
        assert g.render(w["arjun"], paatti.id) == "your grandmother Paatti (Mom's mom)"
        assert g.render(paatti.id, w["arjun"]) == "your grandson Arjun peran (your daughter's son)"
        n_edges = s.scalar(select(func.count(m.Edge.id)))
        ap.place_person(s, w["space"], w["arjun"], "", w["arjun"], "mother.mother", person=paatti.slug, now=T0)
        assert s.scalar(select(func.count(m.Edge.id))) == n_edges  # placing her again adds no duplicate parent edge
