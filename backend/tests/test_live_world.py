"""LiveWorld live path (ARCHITECTURE 8.5, D6, D7, 3.6). No network: the LLM is mocked."""
import asyncio
import time
from datetime import timedelta

import pytest

from app.db import models as m
from app.db.session import init_db, reset_engine, session_scope
from app.world import clock
from app.world.live import LiveWorld
from app.world.users import create_user
from tests.test_cg_cards import add_fact, demo, mock_world_llm, new_call, offset  # noqa: F401  (fixtures)


@pytest.fixture
def live(demo, offset):  # noqa: F811
    offset(42)
    with session_scope() as s:
        _, dana, _ = create_user(s, "Dana", "en")
        demo["dana"] = dana.id
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


def _items(sends, ident, typ="glance"):
    return [it for msg in sends.get(ident, []) if msg["type"] == typ for it in msg.get("items", [msg])]


def test_partial_card_only_on_second_stable_partial(live):
    ids, make = live
    w = make("arjun", "mei")
    mei, arjun = f"p{ids['mei']}", f"p{ids['arjun']}"
    assert w.on_partial(mei, "我和林") == {}
    sends = w.on_partial(mei, "我和林去")
    assert [it["key"] for it in _items(sends, arjun)] == [f"who:{ids['lin_slug']}"]
    assert sends[arjun][0]["partial"] is True and mei not in sends


def test_pending_card_retracted_when_final_drops_the_name(live):
    ids, make = live
    w = make("arjun", "mei")
    mei, arjun = f"p{ids['mei']}", f"p{ids['arjun']}"
    before = w.kcache[(ids["arjun"], "person", ids["lin"])]
    w.on_partial(mei, "我和林")
    w.on_partial(mei, "我和林去")
    fr = w.on_final(mei, "我和他去攀岩了")
    assert _items(fr.sends, arjun, "glance_retract") == [{"type": "glance_retract", "keys": [f"who:{ids['lin_slug']}"]}]
    assert w.kcache[(ids["arjun"], "person", ids["lin"])] == before  # no shown evidence
    assert (arjun, f"who:{ids['lin_slug']}") not in w.sent
    w.close()
    with session_scope() as s:
        assert s.query(m.CardLog).count() == 0


def test_dedupe_per_listener(live):
    ids, make = live
    w = make("arjun", "mei", "dana")
    mei, arjun, dana = (f"p{ids[k]}" for k in ("mei", "arjun", "dana"))
    fr = w.on_final(mei, "我和林去攀岩了")
    gaps = {i: [(it["key"], it["gap"]) for it in _items(fr.sends, i) if it["kind"] == "who"] for i in (arjun, dana)}
    key = f"who:{ids['lin_slug']}"
    assert gaps == {arjun: [(key, "reminder")], dana: [(key, "new")]}  # Dana sees Lin through Mei's own tie fact
    again = w.on_final(mei, "林也喜欢攀岩")
    assert _items(again.sends, arjun) == [] and _items(again.sends, dana) == []
    assert w.guard_drops == 0


def test_refresh_after_new_fact_changes_next_card(live):
    ids, make = live
    w = make("arjun", "mei")
    mei, arjun = f"p{ids['mei']}", f"p{ids['arjun']}"
    assert _items(w.on_final(mei, "我和Bo去了").sends, arjun) == []
    with session_scope() as s:
        bo = m.Person(family_id=ids["space"], slug="p_bo_x", display_name="Bo")
        s.add(bo)
        s.flush()
        add_fact(s, ids["space"], ids["mei"], ids["mei"], "did", "met Bo at the gym",
                 [(ids["mei"], "said"), (ids["arjun"], "heard")], clock.now() - timedelta(days=40),
                 refs=[("person", bo.id)])
    w.refresh()
    items = _items(w.on_final(mei, "我和Bo去了").sends, arjun)
    assert [(it["key"], it["gap"]) for it in items] == [("who:p_bo_x", "new")]


def test_on_partial_p95_under_10ms_for_8_listeners_over_500_people(mock_world_llm):  # noqa: F811
    reset_engine()
    init_db()
    now = clock.now()
    with session_scope() as s:
        users = [create_user(s, f"User{i}", "zh" if i % 2 else "en")[1].id for i in range(9)]
        space = s.get(m.Person, users[0]).family_id
        people = [m.Person(family_id=space, slug=f"p_name{i}", display_name=f"Name{i}",
                           aliases=[m.Alias(alias=f"Nick{i}", lang="en", kind="asr"),
                                    m.Alias(alias=f"Nm{i}x", lang="en", kind="asr")]) for i in range(500)]
        s.add_all(people)
        s.flush()
        for i, p in enumerate(people):
            add_fact(s, space, users[i % 9], users[i % 9], "did", f"saw Name{i}", [(u, "heard") for u in users],
                     now - timedelta(days=i % 90), refs=[("person", p.id)])
        call = new_call(s, space)
    loop = asyncio.new_event_loop()
    w = LiveWorld(call, space, lambda i, msg: asyncio.sleep(0), loop)
    try:
        for i, u in enumerate(users):
            w.join(f"p{u}", u, "zh" if i % 2 else "en")
        sp, text = f"p{users[0]}", "I saw Name17 and Nick250 at the gym with Name499 yesterday"
        times = []
        for _ in range(60):
            w.on_partial(sp, text)  # primes the stability gate
            w.sent, w.pending, w.delivered = frozenset(), {}, {}  # full work on every timed partial
            t = time.perf_counter()
            sends = w.on_partial(sp, text)
            times.append((time.perf_counter() - t) * 1000)
        # 3 names x 8 listeners, minus the 3 listeners who authored a fact about one of them (structural)
        assert len(sends) == 8 and sum(len(v[0]["items"]) for v in sends.values()) == 21
        times.sort()
        print(f"on_partial p50={times[30]:.2f} ms p95={times[57]:.2f} ms")
        assert times[int(0.95 * len(times))] < 10.0, times
    finally:
        w.close()
        loop.close()


# ---- review fixes: translator, extraction after leave, render context, privacy, concurrency-free state ------------
import json  # noqa: E402

import httpx  # noqa: E402

from app import llm as llm_mod  # noqa: E402
from app.world import cards as C  # noqa: E402
from app.world.view import WorldView  # noqa: E402
from tests.test_cg_cards import add_job_story, add_tie  # noqa: E402


@pytest.fixture
def world_reply(monkeypatch, mock_world_llm):  # noqa: F811  (after the demo's mock, so this one wins)
    """Mock LLM whose WorldUpdateOut reply the test sets; LocalizeOut echoes. List it before `live`."""
    box = {"update": {"entities": [], "ties": [], "facts": []}}

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        name = body["response_format"]["json_schema"]["name"]
        if name == "LocalizeOut":
            items = json.loads(body["messages"][-1]["content"])
            reply = {"items": [{"key": i["key"], "body": "L10N " + i["body"]} for i in items]}
        else:
            reply = box["update"]
        return httpx.Response(200, json={"id": "x", "object": "chat.completion", "created": 0, "model": "m",
                                         "choices": [{"index": 0, "finish_reason": "stop",
                                                      "message": {"role": "assistant", "content": json.dumps(reply)}}],
                                         "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})
    monkeypatch.setattr(llm_mod, "_default", llm_mod.LLM(api_key="k", base_url="https://api.meta.ai/v1", model="m",
                                                         transport=httpx.MockTransport(handler)))
    yield box  # monkeypatch restores the demo's mock


def _fact(subject, text, lines, refs=()):
    return {"subject": subject, "predicate": "started", "text_en": text, "text_src": text, "keys": [["pottery"]],
            "refs": list(refs), "lines": lines, "sensitive_kind": "", "same_as": None, "contradicts": None,
            "storyline": None}


def test_translator_is_keyed_by_speaker_language_and_works_without_a_view(live):
    ids, make = live
    w = make("arjun", "mei")
    zh, en = w.translator("zh"), w.translator("en")
    assert zh is w.translator("zh") and zh is not en and zh.linker is not en.linker
    loop = asyncio.new_event_loop()
    try:
        bare = LiveWorld(ids["call"], ids["space"], lambda i, msg: asyncio.sleep(0), loop)
        assert bare.translator("zh") is not None  # a failed join leaves translation working
    finally:
        loop.close()


def test_call_end_extraction_after_everyone_left_keeps_participants(world_reply, live):
    ids, make = live
    w = make("arjun", "mei")
    arjun, mei = f"p{ids['arjun']}", f"p{ids['mei']}"
    with session_scope() as s:
        slug = s.get(m.Person, ids["arjun"]).slug
    world_reply["update"] = {"entities": [], "ties": [], "facts": [_fact(slug, "started pottery", [0])]}
    for n in range(2):
        w.on_final(arjun, "I started pottery")
        w.on_translated(arjun, n, "I started pottery", {"zh": "我开始做陶艺"}, [ids["mei"]])
    w.leave(arjun)
    w.leave(mei)
    w.close()
    with session_scope() as s:
        assert s.query(m.Fact).filter_by(text="started pottery", subject_id=ids["arjun"]).count() == 1


def test_render_uses_the_speaker_who_mentioned_the_node(live):
    ids, make = live
    w = make("arjun", "mei")
    arjun, mei = f"p{ids['arjun']}", f"p{ids['mei']}"
    w.on_final(mei, "我和林去攀岩了")
    w.on_final(arjun, "nice")  # the latest final is now the listener's own
    assert w.render(arjun, ids["lin_slug"]).startswith("Mei's friend Lin")


def test_relational_reference_never_resolves_through_a_hidden_tie(live):
    ids, make = live
    w = make("arjun", "mei")
    arjun, mei = f"p{ids['arjun']}", f"p{ids['mei']}"
    fr = w.on_final(arjun, "I saw Priya yesterday and her friend was there")
    assert not any(sp["node_id"] == ids["lin_slug"] for sp in fr.spans)  # Priya's tie is visible to Priya only
    assert _items(fr.sends, mei) == []


def test_late_ask_card_goes_only_to_the_line_audience(world_reply, live):
    ids, make = live
    w = make("arjun", "mei", "dana")
    arjun, mei, dana = (f"p{ids[k]}" for k in ("arjun", "mei", "dana"))
    with session_scope() as s:
        slug = s.get(m.Person, ids["arjun"]).slug
    ent = {"ref": "e1", "name": "Kofi", "native": "", "forms": ["Kofi"], "kind": "person", "existing_id": None}
    world_reply["update"] = {"entities": [ent], "ties": [], "facts": [_fact(slug, "met Kofi at pottery", [0], ["e1"])]}
    w.on_translated(arjun, 0, "I met Kofi at pottery", {"zh": "我在陶艺课认识了Kofi"}, [ids["mei"]])  # Dana not there
    got = []
    w.emit = lambda i, msg: (got.append((i, msg)), asyncio.sleep(0))[1]
    res = w._extract(0, 1)
    assert res is not None
    w._after_extract(res, w._rebuild())
    who = {i for i, msg in got if msg["type"] == "glance"}
    assert mei in who and dana not in who


def test_told_fast_path_on_a_private_fact_only_blocks_the_bridge(live):
    ids, make = live
    w = make("arjun", "mei", "dana")
    arjun = f"p{ids['arjun']}"
    w.on_final(arjun, "I started bouldering")
    w.on_translated(arjun, 1, "I started bouldering", {"zh": "我开始抱石了"}, [ids["mei"]])  # Dana not in the line
    aud = w.view.audience[ids["boulder"]]
    assert ids["mei"] not in aud and ids["dana"] not in aud  # SMS fact (shareable=False) never becomes visible
    told = [r for r in w._log_rows if r.kind == "told"]
    assert [(r.listener_id, r.target_id, r.key) for r in told] == [(ids["arjun"], ids["mei"], f"bridge:{ids['boulder']}")]
    v = w.view
    assert C.bridges(v, {}, ids["arjun"], ids["mei"], ["climbing"], [], clock.now(), C.CardLogView(1, w._log_rows)) == []


def test_told_overlay_survives_a_view_rebuilt_before_the_write(live):
    ids, make = live
    w = make("arjun", "mei")
    with session_scope() as s:
        fid = add_fact(s, ids["space"], ids["arjun"], ids["arjun"], "started", "started pottery",
                       [(ids["arjun"], "said")], clock.now(), keys=[("pottery",)])
    w.refresh()
    stale = w._rebuild()  # built before the told row exists
    w._submit = lambda fn, *a: None  # the async write never lands
    arjun = f"p{ids['arjun']}"
    w.on_final(arjun, "I started pottery")
    w.on_translated(arjun, 1, "I started pottery", {"zh": "我开始做陶艺"}, [ids["mei"]])
    w._swap(stale)
    assert ids["mei"] in w.view.audience[fid]


def test_ambiguous_name_gets_an_ask_card_not_a_who_card(live):
    ids, make = live
    with session_scope() as s:
        lin2 = m.Person(family_id=ids["space"], slug="p_lin_two", display_name="Lin",
                        aliases=[m.Alias(alias="林", lang="zh", kind="translit")])
        s.add(lin2)
        s.flush()
        add_tie(s, ids["space"], ids["mei"], lin2.id, "friend", "from work", [(ids["mei"], "said"),
                                                                              (ids["arjun"], "heard")], ids["t0"])
    w = make("arjun", "mei")
    fr = w.on_final(f"p{ids['mei']}", "我和林去攀岩了")
    kinds = [it["kind"] for it in _items(fr.sends, f"p{ids['arjun']}")]
    assert "ask" in kinds and "who" not in kinds


def test_storyline_card_once_per_call_through_on_translated(live):
    ids, make = live
    with session_scope() as s:
        add_job_story(s, ids)
    w = make("arjun", "mei")
    mei, arjun = f"p{ids['mei']}", f"p{ids['arjun']}"
    text = "我的工作面试进入第二轮了"
    first = w.on_translated(mei, 1, text, {"en": "My job interview went to the second round"}, [ids["arjun"]])
    assert [it["kind"] for it in _items(first, arjun)] == ["storyline"]
    again = w.on_translated(mei, 2, text, {"en": "My job interview went to the second round"}, [ids["arjun"]])
    assert _items(again, arjun) == []


def test_guard_catches_a_render_through_a_hidden_hop(live, monkeypatch):
    ids, make = live
    with session_scope() as s:
        add_tie(s, ids["space"], ids["arjun"], ids["priya"], "friend", "", [(ids["arjun"], "said"),
                                                                            (ids["priya"], "heard")], ids["t0"])
    w = make("arjun", "dana")
    monkeypatch.setattr(WorldView, "_hop_ok", lambda self, *a: True)  # a hop-visibility regression in view.py
    fr = w.on_final(f"p{ids['dana']}", "I saw Lin")
    assert _items(fr.sends, f"p{ids['arjun']}") == [] and w.guard_drops == 1
