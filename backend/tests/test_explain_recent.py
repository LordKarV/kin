"""Gesture explain, "what's this about?" (ARCHITECTURE Amendment 7). No network: the LLM is a MockTransport."""
import json
import time
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from app import llm as llm_mod
from app.audio import pipeline
from app.db import models as m
from app.db.session import session_scope
from app.main import app
from app.world import explain_recent as ER
from app.world.explain import explain
from app.world.explain_recent import explain_recent
from tests.test_cg_cards import add_fact, add_job_story, demo, mock_world_llm, offset  # noqa: F401  (fixtures)
from tests.test_explain import live  # noqa: F401  (fixture)


@pytest.fixture
def gllm(live, monkeypatch):  # noqa: F811
    """GestureChoice answers come from `replies` (default "none"); every other schema gets an empty answer."""
    st = SimpleNamespace(calls=[], replies=[], delay=0.0)

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        fmt = body["response_format"]["json_schema"]
        if fmt["name"] == "GestureChoice":
            st.calls.append(SimpleNamespace(user=body["messages"][-1]["content"],
                                            enum=fmt["schema"]["properties"]["choice"]["enum"]))
            reply = {"choice": st.replies.pop(0) if st.replies else "none"}  # taken on arrival, before any delay
            time.sleep(st.delay)
        elif fmt["name"] == "WorldUpdateOut":
            reply = {"entities": [], "ties": [], "facts": []}
        else:
            reply = {"items": []}
        return httpx.Response(200, json={"id": "x", "object": "chat.completion", "created": 0, "model": "m",
                                         "choices": [{"index": 0, "finish_reason": "stop",
                                                      "message": {"role": "assistant", "content": json.dumps(reply)}}],
                                         "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})
    fake = llm_mod.LLM(api_key="k", base_url="https://api.meta.ai/v1", model="m", transport=httpx.MockTransport(handler))
    monkeypatch.setattr(llm_mod, "_default", fake)
    return st


@pytest.fixture
def mog(live):  # noqa: F811
    """Moganshan: a place Mei told Arjun about."""
    ids, _make = live
    with session_scope() as s:
        t = m.Thing(family_id=ids["space"], slug="th_moganshan", kind="place", name="Moganshan", aliases=["莫干山"])
        s.add(t)
        s.flush()
        add_fact(s, ids["space"], ids["mei"], ids["mei"], "visited", "went hiking in Moganshan",
                 [(ids["mei"], "said"), (ids["arjun"], "heard")], ids["t0"], refs=[("thing", t.id)])
    return "what:th_moganshan"


def say(w, ids, who, text, en=None):
    """A final line by `who` that everyone else on the call heard, in pipeline order (on_final, then on_translated,
    audio/pipeline.py), so pushes and heard/shown evidence are in place as on a real call. Returns the utterance id."""
    pid = ids[who]
    ident, lang = f"p{pid}", w.parts[f"p{pid}"][1]
    audience = [p for p, _l in w.parts.values() if p != pid]
    tr = {"en": en} if en else {}
    w.on_final(ident, text)
    with session_scope() as s:
        u = m.Utterance(call_id=ids["call"], speaker_id=pid, src_text=text, lang=lang, audience=audience,
                        translations=tr)
        s.add(u)
        s.flush()
        uid = u.id
    w.on_translated(ident, uid, text, tr, audience)
    return uid


def test_clear_single_candidate_answers_with_no_llm_call(live, gllm):
    ids, make = live
    w = make("arjun", "mei")
    say(w, ids, "mei", "我和林去攀岩了", "I went climbing with Lin.")
    t0 = time.perf_counter()
    items = explain_recent(w, ids["call"], ids["arjun"])
    print(f"gesture no-LLM path: {(time.perf_counter() - t0) * 1000:.1f} ms")
    assert [(it["kind"], it["key"]) for it in items] == [("who", f"who:{ids['lin_slug']}")]
    assert "Fudan" in items[0]["body"] and items[0]["gap"] is None
    assert gllm.calls == []
    assert w.kcache[(ids["arjun"], "person", ids["lin"])].n_asked == 1  # asked: he did not know
    w.close()
    with session_scope() as s:
        rows = s.query(m.CardLog).filter_by(kind="gesture").all()
        assert [(r.listener_id, r.key) for r in rows] == [(ids["arjun"], f"who:{ids['lin_slug']}")]


def test_two_candidates_in_one_line_ask_the_llm_and_take_its_choice(live, gllm, mog):
    ids, make = live
    w = make("arjun", "mei")
    say(w, ids, "mei", "我和林去莫干山了")
    lin = f"who:{ids['lin_slug']}"
    gllm.replies = [lin]
    items = explain_recent(w, ids["call"], ids["arjun"])
    assert [it["key"] for it in items] == [lin]
    assert len(gllm.calls) == 1 and set(gllm.calls[0].enum) == {lin, mog, "none"}
    user = gllm.calls[0].user
    assert "我和林去莫干山了" in user and f"{lin} | Lin" in user and f"{mog} | Moganshan" in user
    assert "Fudan" not in user and "hiking" not in user  # facts never go to the model


def test_that_trip_resolves_through_the_llm_to_a_place_three_lines_back(live, gllm, mog):
    ids, make = live
    w = make("arjun", "mei")
    for zh, en in [("我们去了莫干山", "We went to Moganshan."), ("林也在", "Lin was there too."),
                   ("嗯嗯", "Mm."), ("那次旅行太疯狂了", "That trip was insane.")]:
        say(w, ids, "mei", zh, en)
    gllm.replies = [mog]
    items = explain_recent(w, ids["call"], ids["arjun"])
    assert [(it["kind"], it["key"]) for it in items] == [("what", mog)]
    assert len(gllm.calls) == 1 and "That trip was insane." in gllm.calls[0].user


def test_none_widens_to_twelve_lines_and_retries_once(live, gllm, mog):
    ids, make = live
    with session_scope() as s:
        sid, *_ = add_job_story(s, ids)
    w = make("arjun", "mei")
    lines = ["好"] * 4 + ["我的工作面试进入第二轮了"] + ["嗯"] * 5 + ["我和林去莫干山了"] + ["嗯"] * 3  # 14 lines
    for zh in lines:
        say(w, ids, "mei", zh)
    story = f"story:{sid}"
    gllm.replies = ["none", story]
    items = explain_recent(w, ids["call"], ids["arjun"])
    assert [(it["kind"], it["key"]) for it in items] == [("storyline", story)]
    first, second = gllm.calls
    assert story not in first.enum and story in second.enum
    assert first.user.count("Mei: ") == 4 and second.user.count("Mei: ") == 12
    gllm.replies = ["none", "none"]  # twice "cannot tell": nothing, after exactly one retry
    assert explain_recent(w, ids["call"], ids["arjun"]) == [] and len(gllm.calls) == 4


def test_llm_timeout_or_bad_answer_falls_back_to_top_ranked(live, gllm, mog, monkeypatch):
    ids, make = live
    w = make("arjun", "mei")
    say(w, ids, "mei", "我和林去莫干山了")
    lin = f"who:{ids['lin_slug']}"
    monkeypatch.setattr(ER, "LLM_TIMEOUT_S", 0.05)
    gllm.delay, gllm.replies = 0.3, [lin]
    assert [it["key"] for it in explain_recent(w, ids["call"], ids["arjun"])] == [mog]
    for _ in range(50):  # the request is still in flight when the timeout fires
        if gllm.calls:
            break
        time.sleep(0.02)
    assert lin in gllm.calls[0].enum
    monkeypatch.setattr(ER, "LLM_TIMEOUT_S", 2.5)
    gllm.delay, gllm.replies = 0.0, ["who:p_not_a_candidate"]  # outside the schema enum: validation fails
    # Arjun just asked for Moganshan: it ranks lower (not out), so Lin is the top-ranked fallback now
    assert [it["key"] for it in explain_recent(w, ids["call"], ids["arjun"])] == [lin]
    assert mog in gllm.calls[-1].enum


def test_term_in_a_line_with_a_person_does_not_win_without_the_llm(live, gllm):
    ids, make = live
    w = make("arjun")
    w.join(f"p{ids['mei']}", ids["mei"], "hi")
    say(w, ids, "mei", "Lin ने दाल बनाई", "Lin made dal.")
    lin = f"who:{ids['lin_slug']}"
    gllm.replies = [lin]
    assert [it["key"] for it in explain_recent(w, ids["call"], ids["arjun"])] == [lin]
    assert len(gllm.calls) == 1 and {lin, "lex:hi:dal"} <= set(gllm.calls[0].enum)


def test_repeat_gesture_over_the_same_lines_does_not_repeat_the_answer(live, gllm, mog):
    ids, make = live
    w = make("arjun", "mei")
    say(w, ids, "mei", "我和林去莫干山了")
    lin = f"who:{ids['lin_slug']}"
    gllm.replies = [mog]
    assert [it["key"] for it in explain_recent(w, ids["call"], ids["arjun"])] == [mog]
    snap = ER._candidates(w, ids["arjun"], ER._heard(w, ids["arjun"], ER.WINDOW))
    assert [c.card.key for c in snap] == [lin, mog]  # asked: lower, still a candidate
    gllm.replies = [lin]
    assert [it["key"] for it in explain_recent(w, ids["call"], ids["arjun"])] == [lin]
    assert len(gllm.calls) == 2


def test_line_redacted_mid_call_is_never_rescanned_or_sent(live, gllm, mog):
    ids, make = live
    with session_scope() as s:
        sid, *_ = add_job_story(s, ids)
    w = make("arjun", "mei")
    gone = say(w, ids, "mei", "我的工作面试进入第二轮了")
    say(w, ids, "mei", "我和林去莫干山了")
    with session_scope() as s:  # a privacy delete redacts the line (section 10)
        s.execute(update(m.Utterance).where(m.Utterance.id == gone).values(src_text=""))
    gllm.replies = ["none", "none"]
    assert explain_recent(w, ids["call"], ids["arjun"]) == []
    assert len(gllm.calls) == 2
    for c in gllm.calls:
        assert f"story:{sid}" not in c.enum and "面试" not in c.user


def test_hidden_entity_is_never_a_candidate_or_in_the_prompt(live, gllm, mog):
    ids, make = live
    with session_scope() as s:  # only Priya heard about Zhou
        zhou = m.Person(family_id=ids["space"], slug="p_zhou_x", display_name="Zhou")
        s.add(zhou)
        s.flush()
        add_fact(s, ids["space"], zhou.id, ids["priya"], "works_at", "works at Tesla", [(ids["priya"], "said")],
                 ids["t0"], refs=[("person", ids["priya"])])
        zid = zhou.id
    w = make("arjun", "mei", "priya")  # Priya on the call: Zhou is in the view and the index, hidden from Arjun
    text = "我和林还有Zhou去莫干山了"
    assert any(h.ids == (zid,) for h in w._snap.index.scan(text, "zh"))  # the name is in the line
    say(w, ids, "mei", text)
    gllm.replies = ["none", "none"]
    assert explain_recent(w, ids["call"], ids["arjun"]) == []
    for c in gllm.calls:
        assert set(c.enum) == {f"who:{ids['lin_slug']}", mog, "none"}
        assert "p_zhou_x" not in c.user and "Tesla" not in c.user and "| Zhou" not in c.user
    # on_final may record "heard" (he heard the name); the gesture never answers with Zhou, so never "asked"
    assert getattr(w.kcache.get((ids["arjun"], "person", zid)), "n_asked", 0) == 0


def test_own_lines_are_not_candidates_and_nothing_qualifies_is_empty(live, gllm, mog):
    ids, make = live
    w = make("arjun", "mei")
    assert explain_recent(w, ids["call"], ids["arjun"]) == []  # nothing heard yet
    say(w, ids, "arjun", "I went to Moganshan with Lin")
    say(w, ids, "mei", "你好", "Hello.")
    assert [ln.text for ln in w.heard(ids["arjun"], 4)] == ["你好"]
    assert explain_recent(w, ids["call"], ids["arjun"]) == []
    assert gllm.calls == []
    with pytest.raises(LookupError):
        explain_recent(w, ids["call"], ids["dana"])  # not in the call


def test_api_gesture_body(live, gllm, monkeypatch):
    ids, make = live
    w = make("arjun", "mei", "dana")
    say(w, ids, "mei", "我和林去攀岩了")
    with session_scope() as s:
        s.add_all([m.CallParticipant(call_id=ids["call"], person_id=ids[k], identity=f"p{ids[k]}",
                                     lang="zh" if k == "mei" else "en", joined_at=datetime.now(timezone.utc))
                   for k in ("arjun", "mei", "dana")])
    monkeypatch.setattr(pipeline.registry, "get", lambda cid: SimpleNamespace(world=w) if cid == ids["call"] else None)
    c = TestClient(app)
    url, h = f"/api/calls/{ids['call']}/explain", {"X-KIN-User": ids["dana_tok"]}
    r = c.post(url, json={"text": None, "recent": True}, headers=h)
    assert r.status_code == 200 and [it["key"] for it in r.json()["items"]] == [f"who:{ids['lin_slug']}"]
    assert c.post(url, json={"text": None}, headers=h).status_code == 422
    assert c.post(url, json={}, headers=h).status_code == 422
    assert c.post(url, json={"text": "Zhao"}, headers=h).json()["items"][0]["kind"] == "ask"  # tap path unchanged


def test_unknown_name_falls_back_to_the_ask_a_tap_gives(live, gllm):
    ids, make = live
    w = make("arjun", "dana")
    uid = say(w, ids, "dana", "I went climbing with Rosa yesterday")
    items = explain_recent(w, ids["call"], ids["arjun"])
    assert [(it["kind"], it["key"], it["title"]) for it in items] == [("ask", "ask:rosa", "Rosa")]
    assert items == explain(w, ids["call"], ids["arjun"], "Rosa", utterance_id=uid)
    assert gllm.calls == []
    say(w, ids, "dana", "Lin and Rosa were there")  # a known entity still wins over the ask
    assert [it["key"] for it in explain_recent(w, ids["call"], ids["arjun"])] == [f"who:{ids['lin_slug']}"]
    w2 = make("arjun", "dana")
    say(w2, ids, "dana", "Hello. Thanks!")  # sentence-initial words are not names
    assert explain_recent(w2, ids["call"], ids["arjun"]) == []


def test_hidden_name_gets_the_same_ask_as_an_unknown_one(live, gllm):
    ids, make = live
    with session_scope() as s:  # only Priya heard about Zhou
        zhou = m.Person(family_id=ids["space"], slug="p_zhou_x", display_name="Zhou")
        s.add(zhou)
        s.flush()
        add_fact(s, ids["space"], zhou.id, ids["priya"], "works_at", "works at Tesla", [(ids["priya"], "said")],
                 ids["t0"], refs=[("person", ids["priya"])])
    w = make("arjun", "dana", "priya")  # Priya on the call: Zhou is in the view and the index, hidden from Arjun
    say(w, ids, "dana", "I went climbing with Zhou yesterday")
    hidden = json.dumps(explain_recent(w, ids["call"], ids["arjun"]))
    say(w, ids, "dana", "I went climbing with Rosa yesterday")
    unknown = json.dumps(explain_recent(w, ids["call"], ids["arjun"]))
    assert '"kind": "ask"' in hidden and "p_zhou_x" not in hidden and "Tesla" not in hidden
    assert hidden.replace("Zhou", "X").replace("zhou", "x") == unknown.replace("Rosa", "X").replace("rosa", "x")
