"""Tap-a-word explain (ARCHITECTURE Amendment 5). No network: the LLM is mocked."""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.audio import pipeline
from app.db import models as m
from app.db.session import session_scope
from app.main import app
from app.world import clock
from app.world import knowledge as kn
from app.world.explain import explain
from app.world.live import LiveWorld
from app.world.users import create_user
from app.world import cards as C
from tests.test_cg_cards import add_fact, add_job_story, demo, mock_world_llm, offset  # noqa: F401  (fixtures)


@pytest.fixture
def live(demo, offset):  # noqa: F811
    offset(42)
    with session_scope() as s:
        dana, p, tok = create_user(s, "Dana", "en")
        demo.update(dana=p.id, dana_tok=tok)
    loop = asyncio.new_event_loop()
    worlds = []

    def make(*who):
        w = LiveWorld(demo["call"], demo["space"], lambda i, msg: asyncio.sleep(0), loop)
        for k in who:
            w.join(f"p{demo[k]}", demo[k], "zh" if k == "mei" else "en")
        worlds.append(w)
        return w
    yield demo, make
    for w in worlds:
        w.close()
    loop.close()


def _p(w, pid, item_id):
    return kn.p_now(w.kcache.get((pid, "person", item_id)), clock.now())


def test_tap_lin_returns_who_card_with_first_mention_and_asked_evidence(live):
    ids, make = live
    w = make("arjun", "mei", "dana")
    before_all = dict(w.kcache)
    before = _p(w, ids["arjun"], ids["lin"])
    with session_scope() as s:
        u = m.Utterance(call_id=ids["call"], speaker_id=ids["mei"], src_text="我和林去攀岩了")
        s.add(u)
        s.flush()
        uid = u.id
    items = explain(w, ids["call"], ids["arjun"], "Lin", utterance_id=uid)
    assert [(it["kind"], it["key"]) for it in items] == [("who", f"who:{ids['lin_slug']}")]
    assert "Fudan" in items[0]["body"] and "first mentioned" in items[0]["body"]
    assert _p(w, ids["arjun"], ids["lin"]) < before  # the tap is evidence he did not know
    assert w.kcache[(ids["arjun"], "person", ids["lin"])].n_asked == 1
    others = lambda kc: {k: v for k, v in kc.items() if k[0] != ids["arjun"]}  # noqa: E731
    assert others(w.kcache) == others(before_all)  # no other listener's state changed
    w.close()
    with session_scope() as s:
        rows = s.query(m.CardLog).all()
        assert [(r.listener_id, r.kind, r.key) for r in rows] == [(ids["arjun"], "explain", f"who:{ids['lin_slug']}")]


def test_tap_never_reveals_lin_to_someone_who_never_heard_of_her(live):
    ids, make = live
    w = make("arjun", "dana")  # Arjun only heard Mei's fact about Lin: he cannot disclose it (D9)
    items = explain(w, ids["call"], ids["dana"], "Lin")
    assert [it["kind"] for it in items] == ["ask"] and not items[0].get("node_id")
    assert "Fudan" not in items[0]["body"]
    assert (ids["dana"], "person", ids["lin"]) not in w.kcache
    w3 = make("arjun", "mei", "dana")  # no utterance_id, several others: rendered without a speaker
    items = explain(w3, ids["call"], ids["dana"], "Lin")
    assert [it["kind"] for it in items] == ["ask"] and items[0]["body"] == "KIN doesn't know Lin yet"


def test_hidden_name_answers_like_an_unknown_one(live):
    ids, make = live
    w = make("arjun", "dana")
    shape = lambda t: [(it["kind"], bool(it.get("node_id"))) for it in explain(w, ids["call"], ids["dana"], t)]  # noqa: E731
    assert shape("林") == shape("赵") == [("ask", False)]
    assert shape("lin") == shape("zhao") == []
    assert shape("Lin") == shape("Zhao") == [("ask", False)]
    assert shape("राहुल") == [("ask", False)]  # uncased script: no capital to go by


def test_fact_told_only_to_priya_is_never_cited(live):
    ids, make = live
    with session_scope() as s:  # Priya told only herself about Zhou: Mei cannot disclose it, Arjun never heard it
        zhou = m.Person(family_id=ids["space"], slug="p_zhou_x", display_name="Zhou")
        s.add(zhou)
        s.flush()
        add_fact(s, ids["space"], zhou.id, ids["priya"], "works_at", "works at Tesla", [(ids["priya"], "said")],
                 ids["t0"], refs=[("person", ids["priya"])])
    w = make("arjun", "mei")
    items = explain(w, ids["call"], ids["arjun"], "Zhou")
    assert [it["kind"] for it in items] == ["ask"] and "Tesla" not in items[0]["body"]


def test_delivery_guard_drops_the_card(live, monkeypatch):
    ids, make = live
    w = make("arjun", "mei")
    monkeypatch.setattr(C, "deliver_ok", lambda *a: False)
    assert explain(w, ids["call"], ids["arjun"], "Lin") == []  # visible to him, so no ask either


def test_tap_storyline_keyword_returns_storyline_card(live):
    ids, make = live
    with session_scope() as s:
        sid, _f1, _f2, state2 = add_job_story(s, ids)
    w = make("arjun", "mei")
    items = explain(w, ids["call"], ids["arjun"], "工作")
    assert [(it["kind"], it["key"]) for it in items] == [("storyline", f"story:{sid}")]
    assert w.kcache[(ids["arjun"], "state", state2)].n_asked == 1


def test_unknown_name_asks_and_plain_word_returns_nothing(live):
    ids, make = live
    w = make("arjun", "mei")
    items = explain(w, ids["call"], ids["arjun"], "Zhao")
    assert [(it["kind"], it["term"]) for it in items] == [("ask", "Zhao")]
    assert items[0]["suggestions"][0]["owner"] == ids["mei_slug"]
    assert explain(w, ids["call"], ids["arjun"], "climbing") == []
    assert explain(w, ids["call"], ids["arjun"], "The") == []


def test_explained_card_is_not_pushed_again(live):
    ids, make = live
    w = make("arjun", "mei")
    explain(w, ids["call"], ids["arjun"], "Lin")
    fr = w.on_final(f"p{ids['mei']}", "我和林去攀岩了")
    keys = [it["key"] for msg in fr.sends.get(f"p{ids['arjun']}", []) if msg["type"] == "glance" for it in msg["items"]]
    assert f"who:{ids['lin_slug']}" not in keys


def test_tap_by_listener_outside_the_call_raises(live):
    ids, make = live
    w = make("arjun", "mei")
    with pytest.raises(LookupError):
        explain(w, ids["call"], ids["dana"], "Lin")
    with pytest.raises(LookupError):
        explain(w, ids["call"], ids["arjun"], "Lin", utterance_id=999)


def test_api_explain_status_codes(live, monkeypatch):
    ids, make = live
    w = make("arjun", "dana")
    now = datetime.now(timezone.utc)
    with session_scope() as s:
        s.add_all([m.CallParticipant(call_id=ids["call"], person_id=ids[k], identity=f"p{ids[k]}", lang="en",
                                     joined_at=now) for k in ("arjun", "dana")])
        _, _, outsider = create_user(s, "Eve", "en")
    monkeypatch.setattr(pipeline.registry, "get", lambda cid: SimpleNamespace(world=w) if cid == ids["call"] else None)
    c = TestClient(app)
    url, h = f"/api/calls/{ids['call']}/explain", {"X-KIN-User": ids["dana_tok"]}
    r = c.post(url, json={"text": "Zhao"}, headers=h)
    assert r.status_code == 200 and [it["kind"] for it in r.json()["items"]] == ["ask"]
    assert c.post(url, json={"text": "  "}, headers=h).status_code == 422
    assert c.post(url, json={"text": ""}, headers=h).status_code == 422
    assert c.post(url, json={"text": "Lin"}, headers={"X-KIN-User": outsider}).status_code == 404
    assert c.post("/api/calls/99999/explain", json={"text": "Lin"}, headers=h).status_code == 404
    assert c.post(url, json={"text": "Lin"}).status_code == 401
    monkeypatch.setattr(pipeline.registry, "get", lambda cid: None)  # a real call, not live
    assert c.post(url, json={"text": "Lin"}, headers=h).status_code == 404
