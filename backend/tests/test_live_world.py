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
    box = {"update": {"entities": [], "ties": [], "facts": []}, "prompts": []}

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        name = body["response_format"]["json_schema"]["name"]
        if name == "LocalizeOut":
            items = json.loads(body["messages"][-1]["content"])
            reply = {"items": [{"key": i["key"], "body": "L10N " + i["body"]} for i in items]}
        else:
            box["prompts"].append(json.dumps(body["messages"], ensure_ascii=False))
            reply = box["update"]
        return httpx.Response(200, json={"id": "x", "object": "chat.completion", "created": 0, "model": "m",
                                         "choices": [{"index": 0, "finish_reason": "stop",
                                                      "message": {"role": "assistant", "content": json.dumps(reply)}}],
                                         "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})
    monkeypatch.setattr(llm_mod, "_default", llm_mod.LLM(api_key="k", base_url="https://api.meta.ai/v1", model="m",
                                                         transport=httpx.MockTransport(handler)))
    yield box  # monkeypatch restores the demo's mock


def _utt(ids, who, text):
    """A real utterance row: extraction skips lines whose utterance was deleted or redacted (section 10)."""
    with session_scope() as s:
        u = m.Utterance(call_id=ids["call"], speaker_id=ids[who], src_text=text)
        s.add(u)
        s.flush()
        return u.id


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
    for _ in range(2):
        w.on_final(arjun, "I started pottery")
        w.on_translated(arjun, _utt(ids, "arjun", "I started pottery"), "I started pottery", {"zh": "我开始做陶艺"},
                        [ids["mei"]])
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
    w.on_translated(arjun, _utt(ids, "arjun", "I met Kofi at pottery"), "I met Kofi at pottery",
                    {"zh": "我在陶艺课认识了Kofi"}, [ids["mei"]])  # Dana not there
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


# 4C: a bridge chip clears when the owner tells the listener on the call.
def test_bridge_retracted_when_owner_tells_and_never_resent(live):  # noqa: F811
    ids, make = live
    w = make("arjun", "mei")
    mei, arjun = f"p{ids['mei']}", f"p{ids['arjun']}"
    key = f"bridge:{ids['boulder']}"
    line, tr = "我和林去攀岩了", {"en": "I went climbing with Lin."}
    w.on_final(mei, line)
    first = w.on_translated(mei, 1, line, tr, [ids["arjun"]])
    assert key in [it["key"] for it in _items(first, arjun)]

    w.on_final(arjun, "I started bouldering")
    told = w.on_translated(arjun, 2, "I started bouldering", {"zh": "我开始抱石了"}, [ids["mei"]])
    assert _items(told, arjun, "glance_retract") == [{"type": "glance_retract", "keys": [key]}]
    assert mei not in told or _items(told, mei, "glance_retract") == []

    w.on_final(mei, line)
    again = w.on_translated(mei, 3, line, tr, [ids["arjun"]])
    assert key not in [it["key"] for it in _items(again, arjun)]
    w.on_final(arjun, "I started bouldering")  # telling again does not retract twice
    assert _items(w.on_translated(arjun, 4, "I started bouldering", {"zh": "我开始抱石了"}, [ids["mei"]]),
                  arjun, "glance_retract") == []


# ---- verified-findings fixes (live-engine group) ------------------------------------------------------------------
import concurrent.futures  # noqa: E402

from sqlalchemy import event, select  # noqa: E402

from app.db.session import get_engine  # noqa: E402
from app.world import knowledge as kn  # noqa: E402
from app.world import privacy  # noqa: E402
from app.world.apply import place_person  # noqa: E402
from app.world.contracts import NewPerson  # noqa: E402
from app.world.sms import write_evidence  # noqa: E402


def _keys(sends, ident):
    return [it["key"] for it in _items(sends, ident)]


def test_owner_echoing_the_topic_word_has_not_told_the_news(live):
    ids, make = live
    w = make("arjun", "mei")
    mei, arjun = f"p{ids['mei']}", f"p{ids['arjun']}"
    key, line = f"bridge:{ids['boulder']}", "我和林去攀岩了"
    w.on_final(mei, line)
    assert key in _keys(w.on_translated(mei, 1, line, {"en": "I went climbing with Lin."}, [ids["arjun"]]), arjun)
    reply = "Oh nice, how was the climbing?"
    w.on_final(arjun, reply)
    echo = w.on_translated(arjun, 2, reply, {"zh": "哦不错，攀岩怎么样？"}, [ids["mei"]])
    assert _items(echo, arjun, "glance_retract") == [] and not [r for r in w._log_rows if r.kind == "told"]
    news = "I started bouldering last week."
    w.on_final(arjun, news)
    told = w.on_translated(arjun, 3, news, {"zh": "我上周开始抱石了"}, [ids["mei"]])
    assert _items(told, arjun, "glance_retract") == [{"type": "glance_retract", "keys": [key]}]


def test_non_english_owner_tells_through_the_english_translation(live):
    ids, make = live
    with session_scope() as s:
        fid = add_fact(s, ids["space"], ids["mei"], ids["mei"], "started", "started pottery",
                       [(ids["mei"], "authored")], clock.now(), keys=[("pottery", "陶艺")], source_kind="message",
                       shareable=False)
    w = make("arjun", "mei")
    mei, arjun = f"p{ids['mei']}", f"p{ids['arjun']}"
    first = w.on_translated(arjun, 1, "I went to a pottery class", {"zh": "我去上了陶艺课"}, [ids["mei"]])
    assert f"bridge:{fid}" in _keys(first, mei)
    told = w.on_translated(mei, 2, "我开始做陶艺了", {"en": "I started pottery"}, [ids["arjun"]])
    assert _items(told, mei, "glance_retract") == [{"type": "glance_retract", "keys": [f"bridge:{fid}"]}]


def test_partial_card_survives_a_final_that_shifts_the_name(live):
    ids, make = live
    w = make("arjun", "mei")
    mei, arjun = f"p{ids['mei']}", f"p{ids['arjun']}"
    key = f"who:{ids['lin_slug']}"
    w.on_partial(mei, "我和林")
    assert _keys(w.on_partial(mei, "我和林去"), arjun) == [key]
    fr = w.on_final(mei, "嗯，我和林去攀岩了。")  # a filler moves 林 by two characters
    assert _items(fr.sends, arjun, "glance_retract") == [] and key not in _keys(fr.sends, arjun)
    assert (arjun, key) in w.sent and w.kcache[(ids["arjun"], "person", ids["lin"])].n_shown == 1


def test_my_friend_never_resolves_to_the_person_on_the_call(live):
    ids, make = live
    with session_scope() as s:
        add_tie(s, ids["space"], ids["arjun"], ids["mei"], "friend", "", [(ids["arjun"], "said"),
                                                                          (ids["mei"], "heard")], ids["t0"])
    w = make("arjun", "mei")
    fr = w.on_final(f"p{ids['arjun']}", "My friend told me about this place")
    assert not [sp for sp in fr.spans if sp["method"] == "relational"]


def test_privacy_delete_mid_call_never_writes_knowledge_back(live):
    ids, make = live
    w = make("arjun", "mei")
    w.on_final(f"p{ids['mei']}", "我和林去攀岩了")
    st = w.kcache[(ids["arjun"], "person", ids["lin"])]
    with session_scope() as s:
        privacy.delete_person(s, ids["lin"])
    # a flush taken before the delete lands after it: the deleted item is skipped, the rest is written
    LiveWorld._upsert({(ids["arjun"], "person", ids["lin"]): st, (ids["arjun"], "person", ids["priya"]): st})
    with session_scope() as s:
        assert s.query(m.Knowledge).filter_by(item_kind="person", item_id=ids["lin"]).count() == 0
        assert s.query(m.Knowledge).filter_by(knower_id=ids["arjun"], item_id=ids["priya"]).count() == 1
    w.refresh()
    assert not [k for k in (*w.kcache, *w._dirty) if k[1:] == ("person", ids["lin"])]
    w.close()
    with session_scope() as s:
        assert s.query(m.Knowledge).filter_by(item_kind="person", item_id=ids["lin"]).count() == 0


def test_account_delete_mid_call_keeps_the_others_facts_and_never_resends_its_lines(world_reply, live):
    ids, make = live
    w = make("arjun", "mei")
    mei, arjun = f"p{ids['mei']}", f"p{ids['arjun']}"
    world_reply["update"] = {"entities": [], "ties": [], "facts": [_fact(ids["mei_slug"], "started pottery", [0])]}
    for who, ident, text, other in (("mei", mei, "我开始做陶艺了", "arjun"),
                                    ("arjun", arjun, "I adopted a cat, Mochi", "mei"),
                                    ("mei", mei, "我妹妹的秘密", "arjun")):
        w.on_translated(ident, _utt(ids, who, text), text, {}, [ids[other]])
    with session_scope() as s:
        redacted = s.scalars(select(m.Utterance).where(m.Utterance.src_text == "我妹妹的秘密")).one()
        redacted.src_text = ""  # what deleting the fact cut from it does (privacy._purge_facts)
        privacy.delete_account(s, s.scalars(select(m.User).where(m.User.person_id == ids["arjun"])).one())
    w.refresh()
    w.close()
    prompts = "".join(world_reply["prompts"])
    assert "我开始做陶艺了" in prompts and "Mochi" not in prompts and "秘密" not in prompts
    with session_scope() as s:
        assert s.query(m.Fact).filter_by(subject_id=ids["mei"], text="started pottery").count() == 1


def test_place_during_the_call_survives_the_next_flush(live):
    ids, make = live
    w = make("arjun", "mei")
    with session_scope() as s:  # what POST /world/place does when Arjun answers "Who is Lin?"
        write_evidence(s, [(ids["arjun"], "person", ids["lin"], "confirmed")], clock.now())
    w.refresh()
    w.on_final(f"p{ids['mei']}", "林也喜欢攀岩")
    w.close()
    with session_scope() as s:
        row = s.query(m.Knowledge).filter_by(knower_id=ids["arjun"], item_kind="person", item_id=ids["lin"]).one()
        assert (row.n_confirmed, row.n_heard) == (1, 2) and row.half_life_days >= 90


def test_ask_suggestions_are_always_placeable(live):
    ids, make = live
    w = make("arjun", "mei")
    mei, arjun = f"p{ids['mei']}", f"p{ids['arjun']}"
    rels = {"Kofi": "boss", "Ravi": "uncle", "Ana": "mother", "Bea": "close friend", "Cy": ""}
    sends = w.asks(mei, [arjun], [NewPerson(source=n, name=n, owner="speaker", owner_name="Mei", relation=r,
                                            context="") for n, r in rels.items()])
    sugg = {it["title"]: it["suggestions"] for it in _items(sends, arjun)}
    assert set(sugg) == set(rels) and sugg["Ravi"] == []
    assert [(sg["relation"], sg["label"]) for sg in sugg["Kofi"]] == [("coworker", "Mei's coworker")]
    with session_scope() as s:
        for name, sgs in sugg.items():
            for sg in sgs:
                owner = s.scalars(select(m.Person).where(m.Person.slug == sg["owner"])).one()
                place_person(s, ids["space"], ids["arjun"], name, owner.id, sg["relation"])  # ValueError if not


def test_late_who_card_reads_knowledge_before_the_heard_evidence(world_reply, live):
    ids, make = live
    with session_scope() as s:
        kofi = m.Person(family_id=ids["space"], slug="p_kofi_x", display_name="Kofi")
        s.add(kofi)
        s.flush()
        kofi_id = kofi.id
        add_fact(s, ids["space"], ids["arjun"], ids["arjun"], "did", "met Kofi", [(ids["arjun"], "said")], ids["t0"],
                 refs=[("person", kofi_id)])  # Mei has never heard of Kofi
        arjun_slug = s.get(m.Person, ids["arjun"]).slug
    w = make("arjun", "mei")
    arjun, mei = f"p{ids['arjun']}", f"p{ids['mei']}"
    ent = {"ref": "e1", "name": "Kofi", "native": "", "forms": ["Kofi"], "kind": "person", "existing_id": kofi_id}
    world_reply["update"] = {"entities": [ent], "ties": [],
                             "facts": [_fact(arjun_slug, "Kofi is a coworker at the lab", [0], ["e1"])]}
    text = "I met Kofi, my coworker at the lab"  # the alias index missed him: only extraction finds him
    w.on_translated(arjun, _utt(ids, "arjun", text), text, {"zh": "我认识了Kofi"}, [ids["mei"]])
    got = []
    w.emit = lambda i, msg: (got.append((i, msg)), asyncio.sleep(0))[1]
    res = w._extract(0, 1)
    assert res is not None
    w._after_extract(res, w._rebuild())
    late = [(i, it["key"], it["gap"]) for i, msg in got for it in msg.get("items", [])]
    assert late == [(mei, "who:p_kofi_x", "new")]
    assert w.kcache[(ids["mei"], "person", kofi_id)].n_shown == 1


def test_prewarm_renders_through_the_other_participant(live):
    ids, make = live
    with session_scope() as s:
        kofi = m.Person(family_id=ids["space"], slug="p_kofi_x", display_name="Kofi")
        s.add(kofi)
        s.flush()
        add_fact(s, ids["space"], ids["dana"], ids["dana"], "tie", "coworker", [(ids["dana"], "said")], ids["t0"],
                 refs=[("person", kofi.id)])  # Mei can see Kofi only when Dana names him (D9)
    w = make("dana", "mei")
    concurrent.futures.wait(list(w._jobs))
    card = [it for it in _items(w.on_final(f"p{ids['dana']}", "I saw Kofi today").sends, f"p{ids['mei']}")
            if it["key"] == "who:p_kofi_x"]
    assert len(card) == 1 and card[0]["body"].startswith("L10N ")  # Mei's first sight of the card is localized


def test_an_older_view_build_never_replaces_a_newer_one(live):
    ids, make = live
    w = make("arjun", "mei")
    old, new = w._rebuild(), w._rebuild()
    w._swap(new)
    w._swap(old)  # e.g. leave()'s rebuild finishing after a rejoin's
    assert w._snap.seq == new.seq


def test_knowledge_flush_survives_another_writer_inserting_the_same_new_row(live):
    ids, make = live
    key, now = (ids["mei"], "person", ids["priya"]), clock.now()
    fired = []

    def race(conn, cursor, statement, params, context, executemany):
        if not fired and statement.lstrip().upper().startswith("INSERT INTO KNOWLEDGE"):
            fired.append(True)  # another flush inserts the same new key just before this one does
            LiveWorld._upsert({key: kn.update(None, "shown", now)})

    eng = get_engine()
    event.listen(eng, "before_cursor_execute", race)
    try:
        LiveWorld._upsert({key: kn.update(None, "heard", now)})
    finally:
        event.remove(eng, "before_cursor_execute", race)
    with session_scope() as s:
        row = s.query(m.Knowledge).filter_by(knower_id=key[0], item_kind="person", item_id=key[2]).one()
        assert fired and (row.n_heard, row.n_shown) == (1, 0)  # last write wins, nothing rolled back


def test_overlap_lines_are_context_only_but_keep_aliases_and_synthesized_ties(world_reply, live):
    """D14: the second window starts 3 lines back. A fact citing only those lines was written last time and is
    dropped; a known entity no fact cites still teaches its new form (3.3); a tie the model sent without its tie
    fact, said by the only speaker, still lands (validate puts its fact on the speaker's first line, an overlap one)."""
    ids, make = live
    w = make("arjun", "mei")
    arjun = f"p{ids['arjun']}"
    for text in ("I started pottery", "the class is on Tuesdays", "we glaze on Thursdays", "Lin came by",
                 "and we fire the pots on Fridays, Kofi from the lab too"):
        w.on_translated(arjun, _utt(ids, "arjun", text), text, {}, [ids["mei"]])
    concurrent.futures.wait(list(w._jobs))  # lines 0-3 went out with the empty default reply
    with session_scope() as s:
        slug = s.get(m.Person, ids["arjun"]).slug
    lin = {"ref": "e2", "name": "Lin", "native": "林", "forms": ["Linh"], "kind": "person", "existing_id": ids["lin"]}
    kofi = {"ref": "e1", "name": "Kofi", "native": "", "forms": ["Kofi"], "kind": "person", "existing_id": None}
    world_reply["update"] = {  # window = lines 1..4, so window line 3 is the only new one
        "entities": [lin, kofi], "ties": [{"a": "speaker", "b": "e1", "kind": "coworker", "context": "at the lab"}],
        "facts": [_fact(slug, "has class on Tuesdays", [0]), _fact(slug, "fires pots on Fridays", [3])]}
    w.close()  # the call-end extraction of line 4
    with session_scope() as s:
        texts = set(s.scalars(select(m.Fact.text).where(m.Fact.subject_id == ids["arjun"])))
        assert "fires pots on Fridays" in texts and "has class on Tuesdays" not in texts
        assert "Linh" in {a.alias for a in s.get(m.Person, ids["lin"]).aliases}
        kofi_id = s.scalars(select(m.Person.id).where(m.Person.display_name == "Kofi")).one()
        assert s.query(m.Tie).filter_by(src_person=ids["arjun"], dst_person=kofi_id, kind="coworker").count() == 1


def test_overlap_drop_log_never_carries_fact_text(caplog):
    """Fact text is user content: the D14 overlap drop logs only the fact's index, length and lines."""
    from app.world.contracts import FactOut, WorldUpdateOut
    from app.world.live_jobs import _new_only
    secret = "Mei's mom has surgery on Friday"
    fact = FactOut(subject="speaker", predicate="said", text_en=secret, text_src="", keys=[], refs=[], lines=[0],
                   sensitive_kind="", same_as=None, contradicts=None, storyline=None)
    upd = WorldUpdateOut(entities=[], ties=[], facts=[fact])
    with caplog.at_level("DEBUG", logger="kin"):
        assert _new_only(upd, upd, 2, None).facts == []
    assert "fact #0 (31 chars)" in caplog.text and "surgery" not in caplog.text and "Mei" not in caplog.text
