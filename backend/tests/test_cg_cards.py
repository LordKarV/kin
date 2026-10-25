"""Card selection (ARCHITECTURE 8.6, 5, 6.5) on the demo probe and on random views. No network: the LLM is mocked."""
import asyncio
import json
import random
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app import llm as llm_mod
from app.db import models as m
from app.db.session import init_db, reset_engine, session_scope
from app.graph.kinship import FamilyGraph, Node
from app.world import cards as C
from app.world import clock
from app.world import knowledge as kn
from app.world.apply import world_slug
from app.world.live import LiveWorld
from app.world.match import AliasIndex
from app.world.users import create_user
from app.world.view import PersonV, WorldView
from app.world.visibility import FactV


@pytest.fixture
def mock_world_llm(monkeypatch):
    """Answers LocalizeOut by echoing bodies with a prefix, extraction with an empty update."""
    def handler(req: httpx.Request):
        body = json.loads(req.content)
        name = body["response_format"]["json_schema"]["name"]
        if name == "LocalizeOut":
            items = json.loads(body["messages"][-1]["content"])
            reply = {"items": [{"key": i["key"], "body": "L10N " + i["body"]} for i in items]}
        elif name == "WorldUpdateOut":
            reply = {"entities": [], "ties": [], "facts": []}
        else:
            reply = {}
        return httpx.Response(200, json={"id": "x", "object": "chat.completion", "created": 0, "model": "m",
                                         "choices": [{"index": 0, "finish_reason": "stop",
                                                      "message": {"role": "assistant", "content": json.dumps(reply)}}],
                                         "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})
    fake = llm_mod.LLM(api_key="k", base_url="https://api.meta.ai/v1", model="m", transport=httpx.MockTransport(handler))
    monkeypatch.setattr(llm_mod, "_default", fake)
    yield fake
    monkeypatch.setattr(llm_mod, "_default", None)


@pytest.fixture
def offset():
    yield clock.set_offset_days
    clock.set_offset_days(0)


def add_fact(s, space, subject, speaker, predicate, text, audience, at, refs=(), keys=(), **kw):
    f = m.Fact(family_id=space, subject_id=subject, speaker_id=speaker, predicate=predicate, text=text, lang="en",
               keys=[list(k) for k in keys], source_kind=kw.pop("source_kind", "call"), said_at=at, **kw)
    s.add(f)
    s.flush()
    s.add_all([m.FactAudience(fact_id=f.id, person_id=p, via=via, at=at) for p, via in audience])
    s.add_all([m.FactRef(fact_id=f.id, kind=k, ref_id=i) for k, i in refs])
    s.flush()
    return f.id


def add_tie(s, space, src, dst, kind, context, audience, at):
    fid = add_fact(s, space, src, src, "tie", f"{kind} {context}".strip(), audience, at, refs=[("person", dst)])
    s.add(m.Tie(family_id=space, src_person=src, dst_person=dst, kind=kind, context=context, fact_id=fid))
    s.flush()


def new_call(s, space):
    c = m.Call(family_id=space, mode="world")
    s.add(c)
    s.flush()
    return c.id


@pytest.fixture
def demo(mock_world_llm, offset):
    """The PRODUCT demo, built like 2A's fixture. Day 0 is now; the probe runs at clock offset 42 days."""
    reset_engine()
    init_db()
    t0 = clock.now()
    ids = {"t0": t0}
    with session_scope() as s:
        for name, lang in [("Arjun", "en"), ("Mei", "zh"), ("Priya", "en")]:
            _, p, _ = create_user(s, name, lang)
            ids[name.lower()] = p.id
        space = s.get(m.Person, ids["arjun"]).family_id
        lin = m.Person(family_id=space, slug="tmp_lin", display_name="Lin")
        lin.aliases = [m.Alias(alias="林", lang="zh", kind="translit"), m.Alias(alias="Lynn", lang="en", kind="asr")]
        s.add(lin)
        s.flush()
        lin.slug = world_slug("p", "Lin", lin.id)
        a, mei, priya = ids["arjun"], ids["mei"], ids["priya"]
        ids.update(lin=lin.id, lin_slug=lin.slug, space=space, mei_slug=s.get(m.Person, mei).slug)
        add_tie(s, space, mei, lin.id, "friend", "from the Fudan climbing wall", [(mei, "said"), (a, "heard")], t0)
        add_tie(s, space, priya, lin.id, "friend", "", [(priya, "said")], t0 + timedelta(days=30))
        st = kn.update(None, "heard", t0)
        s.add(m.Knowledge(knower_id=a, item_kind="person", item_id=lin.id, p=st.p, half_life_days=st.half_life_days,
                          first_at=st.first_at, last_at=st.last_at, last_day=st.last_day, n_heard=1))
        ids["boulder"] = add_fact(s, space, a, a, "started", "started bouldering", [(a, "authored"), (priya, "told")],
                                  t0 + timedelta(days=36), keys=[("bouldering", "climbing", "攀岩")],
                                  source_kind="message", shareable=False)
        ids["call"] = new_call(s, space)
        ids["call2"] = new_call(s, space)
    return ids


def run_probe(ids, call_id, speaker="mei", partials=("我和林", "我和林去攀岩"), final="我和林去攀岩了",
              translation="I went climbing with Lin.", who=("arjun", "mei", "priya")):
    loop = asyncio.new_event_loop()
    w = LiveWorld(call_id, ids["space"], lambda i, msg: asyncio.sleep(0), loop)
    try:
        for k in who:
            w.join(f"p{ids[k]}", ids[k], "zh" if k == "mei" else "en")
        sp = f"p{ids[speaker]}"
        sends = []
        for p in partials:
            sends.append(w.on_partial(sp, p))
        fr = w.on_final(sp, final)
        sends.append(fr.sends)
        sends.append(w.on_translated(sp, 0, final, {"en": translation}, [ids[k] for k in who if k != speaker]))
        w.close()
    finally:
        loop.close()
    items = {k: [it for s in sends for msg in s.get(f"p{ids[k]}", []) if msg["type"] == "glance" for it in msg["items"]]
             for k in who}
    return w, items, fr


def test_demo_probe_reminder_and_bridge_then_nothing_next_day(demo, offset):
    offset(42)
    w, items, fr = run_probe(demo, demo["call"])
    arjun = {it["key"]: it for it in items["arjun"]}
    lin = arjun[f"who:{demo['lin_slug']}"]
    assert demo["lin_slug"].startswith("p_lin_") and lin["gap"] == "reminder" and lin["kind"] == "who"
    assert lin["body"].startswith("Mei's friend Lin (from the Fudan climbing wall)")
    bridge = arjun[f"bridge:{demo['boulder']}"]
    assert bridge["target"] == demo["mei_slug"] and bridge["private"] and bridge["body"] == "started bouldering"
    assert bridge["title"] == "You haven't told Mei"
    assert items["priya"] == [] and items["mei"] == []
    assert w.guard_drops == 0
    assert any(s["node_id"] == demo["lin_slug"] and s["source"] == "林" for s in fr.spans)
    st = w.kcache[(demo["arjun"], "person", demo["lin"])]
    assert (st.n_shown, st.n_heard) == (1, 2) and round(st.p, 3) == 0.892

    offset(43)
    w2, items2, _ = run_probe(demo, demo["call2"])
    assert items2 == {"arjun": [], "mei": [], "priya": []}
    with session_scope() as s:
        logged = s.query(m.CardLog).filter(m.CardLog.kind == "bridge").all()
    assert [(r.listener_id, r.target_id) for r in logged] == [(demo["arjun"], demo["mei"])]


def test_bridge_never_targets_someone_who_heard_it(demo, offset):
    offset(42)
    _w, items, _ = run_probe(demo, demo["call"], speaker="priya", partials=(), final="I went climbing yesterday",
                             translation="我昨天去攀岩了")
    assert not any(it["kind"] == "bridge" for it in items["arjun"])
    offset(42.1)  # past the 90 s rate limit: the same words from Mei, who has not heard it, do bridge
    _w, items, _ = run_probe(demo, demo["call2"], speaker="mei", partials=(), final="I went climbing yesterday")
    assert [it["target"] for it in items["arjun"] if it["kind"] == "bridge"] == [demo["mei_slug"]]


# ---- property test: bridges only ever cite the listener's own facts -------------------------------------------------
NOW = datetime(2026, 10, 26, tzinfo=timezone.utc)
TEXTS = ["我和林去攀岩了", "I went climbing and cooking today"]
KEYS = [(("climbing", "攀岩"),), (("cooking", "做饭"),), (("bouldering",), ("gym",))]


def _random_view(rng: random.Random, L: int, S: int, other: int) -> WorldView:
    ids = [L, S, other] + list(range(10, 10 + rng.randint(0, 4)))
    nodes = [Node(i, f"p_{i}", f"P{i}", "", "", None, False, False, "", []) for i in ids]
    people = {i: PersonV(i, f"p_{i}", f"P{i}", "", i in (L, S, other), "en", ()) for i in ids}
    facts, aud = {}, {}
    for fid in range(1, rng.randint(2, 25)):
        subject = rng.choice(ids)
        speaker = rng.choice(ids + [None])
        facts[fid] = FactV(fid, subject, speaker, rng.choice(["started", "did", "tie", "lives_in"]), f"fact {fid}",
                           rng.choice(KEYS), rng.choice(["active", "active", "superseded"]),
                           rng.choice(["", "", "health"]), rng.random() < 0.2, rng.random() < 0.7, False, None, False,
                           None, NOW - timedelta(days=rng.randint(0, 200)), frozenset())
        aud[fid] = frozenset(rng.sample(ids, rng.randint(0, len(ids))))
    # always plant: a fact about L said by someone else (never a bridge), and a valid self fact (non-vacuous)
    facts[100] = FactV(100, L, other, "started", "planted other", KEYS[0], "active", "", False, True, False, None,
                       False, None, NOW, frozenset())
    aud[100] = frozenset({L, other})
    facts[101] = FactV(101, L, L, "started", "planted self", KEYS[0], "active", "", False, False, False, None,
                       False, None, NOW, frozenset())
    aud[101] = frozenset({L})
    return WorldView(1, frozenset({L, S, other}), FamilyGraph(1, "en", nodes, [], []), people, {}, {}, {}, facts, aud,
                     {}, {}, NOW)


def test_bridges_property_only_self_facts_and_no_guard_drops():
    rng = random.Random(7)
    total = 0
    for _ in range(50):
        v = _random_view(rng, 1, 2, 3)
        for L in (1, 2, 3):
            for S in (1, 2, 3):
                for text in TEXTS:
                    for card in C.bridges(v, {}, L, S, [text], [], NOW, C.CardLogView(1)):
                        f = v.facts[card.fact_ids[0]]
                        assert f.subject_id == L and f.speaker_id == L and S not in v.audience[f.id]
                        assert C.deliver_ok(v, card, L, S, frozenset(), NOW)
                        assert card.fact_ids != (100,)
                        total += 1
    assert total > 50


# ---- storylines and term cards --------------------------------------------------------------------------------------
def add_job_story(s, demo, f2_audience=None, status="active", unresolved=False, labels=("applied", "second round")):
    """Mei's job search: state 1 heard by Arjun, state 2 (30 days later) by `f2_audience` (default Mei only)."""
    t0, space, mei, a = demo["t0"], demo["space"], demo["mei"], demo["arjun"]
    add_tie(s, space, a, mei, "friend", "from high school", [(a, "said")], t0)
    story = m.Storyline(family_id=space, slug="s_job", owner_id=mei, title="job search", unresolved=unresolved,
                        keys=[["job", "工作", "interview", "面试"]], created_at=t0, updated_at=t0)
    s.add(story)
    s.flush()
    f1 = add_fact(s, space, mei, mei, "state", labels[0], [(mei, "said"), (a, "heard")], t0, storyline_id=story.id,
                  status=status)
    f2 = add_fact(s, space, mei, mei, "state", labels[1], f2_audience or [(mei, "said")], t0 + timedelta(days=30),
                  storyline_id=story.id, status=status)
    s.add_all([m.StorylineState(storyline_id=story.id, seq=1, label=labels[0], fact_id=f1, at=t0, status=status),
               m.StorylineState(storyline_id=story.id, seq=2, label=labels[1], fact_id=f2,
                                at=t0 + timedelta(days=30), status=status)])
    s.flush()
    return story.id, f1, f2, s.query(m.StorylineState).filter_by(fact_id=f2).one().id


def _story_view(demo, **kw):
    with session_scope() as s:
        sid, f1, f2, sid2 = add_job_story(s, demo, **kw)
        now = demo["t0"] + timedelta(days=31)
        v = WorldView.build(s, demo["space"], [demo["arjun"], demo["mei"]], now)
    kw_idx = AliasIndex(v.fact_forms() + [(st.title, "storyline", st.id) for st in v.storylines.values()])
    return v, kw_idx, now, sid, f1, f2, sid2


def test_storyline_card_when_behind_none_when_current(demo):
    a, mei = demo["arjun"], demo["mei"]
    v, kw, now, sid, f1, f2, sid2 = _story_view(demo)
    kw_hits = kw.scan("我的工作面试进入第二轮了")
    cards = C.storylines(v, {}, a, mei, kw_hits, [], now)
    assert [c.key for c in cards] == [f"story:{sid}"]
    assert cards[0].payload["body"].startswith("Mei's job search: applied (")
    assert "second round" in cards[0].payload["body"] and set(cards[0].fact_ids) == {f1, f2}
    current = {(a, "state", sid2): kn.update(None, "heard", now)}
    assert C.storylines(v, current, a, mei, kw_hits, [], now) == []
    assert C.storylines(v, {}, a, mei, kw.scan("今天天气不错"), [], now) == []


def test_storyline_unclear_only_when_both_contradicting_facts_are_usable(demo):
    a, mei, priya = demo["arjun"], demo["mei"], demo["priya"]
    both = [(mei, "said"), (a, "heard")]
    v, kw, now, sid, f1, f2, _ = _story_view(demo, f2_audience=both, status="contradicted", unresolved=True,
                                             labels=("Beijing", "Shanghai"))
    hits = kw.scan("她的工作")
    cards = C.storylines(v, {}, a, priya, hits, [], now)
    assert [c.payload["body"] for c in cards] == ["Mei's job search: unclear: Beijing or Shanghai"]
    assert set(cards[0].fact_ids) == {f1, f2} and C.deliver_ok(v, cards[0], a, priya, frozenset(), now)


def test_storyline_unclear_hidden_when_one_fact_is_not_visible(demo):
    a, priya = demo["arjun"], demo["priya"]
    v, kw, now, *_ = _story_view(demo, status="contradicted", unresolved=True, labels=("Beijing", "Shanghai"))
    assert C.storylines(v, {}, a, priya, kw.scan("她的工作"), [], now) == []


# ---- relevance, rate limits and the guard on small views ------------------------------------------------------------
def _tiny_view(facts: dict, aud: dict, L=1, S=2) -> WorldView:
    nodes = [Node(i, f"p_{i}", f"P{i}", "", "", None, False, False, "", []) for i in (L, S)]
    people = {i: PersonV(i, f"p_{i}", f"P{i}", "", True, "en", ()) for i in (L, S)}
    return WorldView(1, frozenset({L, S}), FamilyGraph(1, "en", nodes, [], []), people, {}, {}, {}, facts, aud,
                     {}, {}, NOW)


def _self_fact(fid, keys, at=NOW, **kw):
    return FactV(fid, 1, 1, "started", f"fact {fid}", keys, "active", "", False, kw.get("shareable", True), False,
                 None, False, None, at, frozenset())


def test_relevant_applies_tamil_suffix_rules_with_the_text_language():
    f = _self_fact(1, (("அர்ஜுன்",), ("gym",)))  # neither form is strong alone
    texts = ["அர்ஜுனுக்கு", "gym"]
    assert C.relevant([f], texts, [], ["ta", "en"]) == [f]
    assert C.relevant([f], texts, []) == []  # without the language the inflected form misses


def test_bridge_rate_limits_90s_and_three_per_call():
    facts = {i: _self_fact(i, (("climbing",),), at=NOW - timedelta(days=i)) for i in range(1, 6)}
    v = _tiny_view(facts, {i: frozenset({1}) for i in facts})
    row = lambda k, at, call=1: C.LogRow(call, 1, 2, "bridge", f"bridge:{k}", at)  # noqa: E731
    first = C.bridges(v, {}, 1, 2, ["climbing"], [], NOW, C.CardLogView(1))
    assert [c.key for c in first] == ["bridge:1"]
    recent = C.CardLogView(1, (row(1, NOW - timedelta(seconds=60)),))
    assert C.bridges(v, {}, 1, 2, ["climbing"], [], NOW, recent) == []
    later = C.CardLogView(1, (row(1, NOW - timedelta(seconds=120)),))
    assert [c.key for c in C.bridges(v, {}, 1, 2, ["climbing"], [], NOW, later)] == ["bridge:2"]
    three = C.CardLogView(1, tuple(row(k, NOW - timedelta(minutes=10 * k)) for k in (1, 2, 3)))
    assert C.bridges(v, {}, 1, 2, ["climbing"], [], NOW, three) == []
    told = C.CardLogView(1, (C.LogRow(1, 1, 2, "told", "bridge:1", NOW - timedelta(seconds=5)),))
    assert [c.key for c in C.bridges(v, {}, 1, 2, ["climbing"], [], NOW, told)] == ["bridge:2"]  # no rate limit


def test_guard_drops_a_card_citing_a_fact_outside_the_audience():
    f = FactV(1, 3, 3, "lives_in", "lives in Pune", (), "active", "", False, True, False, None, False, None, NOW,
              frozenset())
    v = _tiny_view({1: f}, {1: frozenset({3})})
    card = C.Card("who:p_3", "who", {"kind": "person", "id": 3}, (1,), {})
    assert not C.deliver_ok(v, card, 1, 2, frozenset({3}), NOW)
    assert C.deliver_ok(replace(v, audience={1: frozenset({1, 3})}), card, 1, 2, frozenset({3}), NOW)


def test_term_card_only_across_languages(mock_world_llm):
    reset_engine()
    init_db()
    with session_scope() as s:
        ids = {}
        for name, lang in [("Paatti", "ta"), ("Arjun", "en"), ("Selvi", "ta")]:
            _, p, _ = create_user(s, name, lang)
            ids[name] = (p.id, lang)
        space = s.get(m.Person, ids["Arjun"][0]).family_id
        call = new_call(s, space)
    loop = asyncio.new_event_loop()
    try:
        w = LiveWorld(call, space, lambda i, msg: asyncio.sleep(0), loop)
        for name, (pid, lang) in ids.items():
            w.join(f"p{pid}", pid, lang)
        fr = w.on_final(f"p{ids['Paatti'][0]}", "இன்னைக்கு சாம்பார் செஞ்சேன்")
        w.close()
    finally:
        loop.close()
    arjun = [it for msg in fr.sends.get(f"p{ids['Arjun'][0]}", []) for it in msg["items"]]
    assert [(it["kind"], it["key"]) for it in arjun] == [("term", "lex:ta:sambar")]
    assert f"p{ids['Selvi'][0]}" not in fr.sends and f"p{ids['Paatti'][0]}" not in fr.sends

