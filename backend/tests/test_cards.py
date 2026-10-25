"""Instant glance cards: lexicon validation, matcher (scripts, nesting, budget), live glance events, pictures. No network."""
import asyncio
import json
import statistics
import time

import pytest
from fastapi.testclient import TestClient

from app.audio.asr import ASREvent
from app.audio.pipeline import CallSession
from app.audio.tts import MockTTS
from app.cards import glance as glance_mod
from app.cards import lexicon as lex_mod
from app.cards.images import Pictures, set_pictures
from app.cards.lexicon import LexEntry, LexiconBatchOut, load_lexicon, validate_entries
from app.cards.matcher import Matcher
from app.mt.translate import Translator
from tests.graph_fixtures import graph  # noqa: F401
from tests.test_call_ws import mock_llm  # noqa: F401


@pytest.fixture(autouse=True)
def fake_pictures(tmp_path):
    calls = []

    def fetch(title):
        calls.append(title)
        if title == "Missing page":
            return None
        return {"title": title, "extract": f"{title} is a thing.", "image_url": f"https://img.test/{title}.jpg",
                "source_url": f"https://en.wikipedia.org/wiki/{title}", "image_credit": f"Wikipedia: {title}"}

    p = Pictures(tmp_path / "pictures.json", fetcher=fetch)
    p.calls = calls
    set_pictures(p)
    glance_mod.reset_engines()
    yield p
    set_pictures(None)
    glance_mod.reset_engines()


def E(key, forms, cat="food", wiki=""):
    return LexEntry(key, tuple(forms), key.replace("_", " "), cat, "why it matters", wiki)


# ---- lexicon ---------------------------------------------------------------
def test_validate_drops_bad_entries_and_mixed_script_forms():
    raw = [
        {"key": "Pongal Dish", "forms": ["பொங்கல்", "pongal"], "translate_as": "pongal", "category": "food", "note": "n", "wiki_title": "Pongal (dish)"},
        {"key": "pongal_dish", "forms": ["x"], "translate_as": "dup", "category": "food"},           # duplicate key
        {"key": "nokey_forms", "forms": [], "translate_as": "t", "category": "food"},                 # no forms
        {"key": "badcat", "forms": ["a"], "translate_as": "t", "category": "dance"},                  # unknown category
        {"key": "notr", "forms": ["a"], "translate_as": "", "category": "food"},                      # no meaning
        {"key": "oonjal", "forms": ["ஊஞ்ಚல்", "oonjal"], "translate_as": "swing", "category": "object"},  # Kannada ಚ in a Tamil word
        "garbage",
    ]
    out, dropped = validate_entries(raw)
    assert [e.key for e in out] == ["pongal_dish", "oonjal"]
    assert out[0].native == "பொங்கல்" and out[1].forms == ("oonjal",)
    assert len(dropped) == 6


def test_committed_lexicons_load_and_are_flagged_unverified():
    for lang in ("ta", "hi"):
        lex = load_lexicon(lang)
        assert len(lex.entries) >= 120 and lex.verified is False
        assert set(lex.counts()) == set(lex_mod.CATEGORIES)


def test_ensure_lexicon_generates_once_and_caches(tmp_path, monkeypatch):
    monkeypatch.setattr(lex_mod, "DIR", tmp_path)
    lex_mod.reset_lexicon_cache()
    calls = []

    class FakeLLM:
        model = "fake"

        def structured(self, schema, system, user, reasoning_effort=None, max_completion_tokens=0):
            calls.append((reasoning_effort, max_completion_tokens))
            cat = user.split("Categories: ")[1].split(",")[0].rstrip(".")
            return LexiconBatchOut.model_validate({"entries": [{"key": f"k_{cat}", "forms": [f"w{cat}"], "translate_as": cat, "category": cat,
                                                                 "note": "n", "wiki_title": ""}]})

    lex = lex_mod.ensure_lexicon("te", llm=FakeLLM())
    assert len(lex.entries) == len(lex_mod.BATCHES) and (tmp_path / "te.json").exists()
    assert all(c == ("low", lex_mod.GEN_MAX_TOKENS) for c in calls)
    lex_mod.ensure_lexicon("te", llm=FakeLLM())
    assert len(calls) == len(lex_mod.BATCHES)  # second call is a cache hit
    lex_mod.reset_lexicon_cache()


# ---- matcher ---------------------------------------------------------------
def test_longest_form_wins_and_nested_spans_are_suppressed():
    m = Matcher([E("puja", ["puja", "பூஜை"]), E("saraswati_puja", ["saraswati puja", "சரஸ்வதி பூஜை"], "festival")])
    assert [(x.entry.key, x.source) for x in m.match("naalaikku saraswati puja, apram puja")] == [("saraswati_puja", "saraswati puja"), ("puja", "puja")]
    assert [x.entry.key for x in m.match("நாளைக்கு சரஸ்வதி பூஜை")] == ["saraswati_puja"]


def test_devanagari_vowel_signs_are_significant_and_whole_word():
    m = Matcher([E("nani_word", ["नानी"]), E("nana_word", ["नाना"]), E("dal", ["दाल", "dal"])])
    assert [x.entry.key for x in m.match("मेरी नानी ने दाल बनाई")] == ["nani_word", "dal"]
    assert [x.entry.key for x in m.match("नाना आए")] == ["nana_word"]
    assert m.match("dalda aur dalia") == []  # no substring hits


def test_tamil_combining_marks_and_case_suffixes():
    m = Matcher([E("pongal", ["பொங்கல்", "pongal"]), E("pal", ["பால்", "paal"])],
                suffixes=("ுக்கு", "ukku", "ல"), final_strip=("்",))
    got = m.match("பொங்கலுக்கு பால் வேணும், pongalukku paal")
    assert [(x.entry.key, x.source, x.method) for x in got] == [("pongal", "பொங்கலுக்கு", "suffix"), ("pal", "பால்", "exact")]  # one hit per key
    assert [(x.source, x.method) for x in m.match("pongalukku paal")] == [("pongalukku", "suffix"), ("paal", "exact")]
    assert m.match("பாலம் கட்டினாங்க") == []  # பால் is not a prefix hit inside பாலம் (bridge)


def test_romanized_spelling_variants_collapse_long_vowels():
    m = Matcher([E("paayasam", ["payasam"])])
    assert [x.source for x in m.match("Paayasam ready!")] == ["Paayasam"]


def test_fuzzy_only_for_sayings_and_never_on_a_short_partial():
    saying = E("flood", ["thalaikku mel vellam ponaal saan enna muzham enna"], "saying")
    short = E("kolam", ["kolam podu"], "ritual")
    m = Matcher([saying, short])
    got = m.match("paatti sonna thalaiku mel vellam ponal saan enna muzham enna nu")
    assert [(x.entry.key, x.method) for x in got] == [("flood", "fuzzy")]
    assert m.match("kolam podunga") == []           # short phrase: exact only
    assert m.match("thalaikku mel vellam") == []    # partial shorter than the saying: no fuzzy hit


def test_matcher_under_5ms_on_large_lexicon():
    entries = list(load_lexicon("ta").entries) + list(load_lexicon("hi").entries)
    entries += [E(f"syn_{i}", [f"word{i}", f"வார்த்தை{i}", f"phrase {i} goes here"], "saying" if i % 10 == 0 else "food") for i in range(5000)]
    m = Matcher(entries, suffixes=("ுக்கு", "ukku", "ல", "யில", "la", "s"), final_strip=("்",))
    line = ("பொங்கலுக்கு சீடை பண்ணணும் amma said the payasam was ready and saraswati puja is tomorrow so "
            "please come early naalaikku kolam podanum word42 and phrase 7 goes here ok bye now")
    assert 28 <= len(line.split()) <= 32
    m.match(line)
    ts = []
    for _ in range(30):
        t = time.perf_counter(); m.match(line); ts.append((time.perf_counter() - t) * 1000)
    assert statistics.median(ts) < 5.0, ts


# ---- live glance events ------------------------------------------------------
class _Sink:
    def __init__(self):
        self.json = []

    async def send_json(self, m):
        self.json.append(m)

    async def send_bytes(self, b):
        pass


def _session(graph, mock_llm):
    from app.db import models as m
    from app.db.session import session_scope
    with session_scope() as s:
        c = m.Call(family_id=graph.family_id); s.add(c); s.flush(); cid = c.id
    return CallSession(call_id=cid, family_id=graph.family_id, translator=Translator(graph, mock_llm), tts=MockTTS())


async def _two_sides(cs):
    gp, gc = _Sink(), _Sink()
    await cs.join("grandparent", "p_kamala", gp.send_json, gp.send_bytes, start_asr=False)
    await cs.join("grandchild", "p_arjun", gc.send_json, gc.send_bytes, start_asr=False)
    return gp, gc


def _glances(sink, typ="glance"):
    return [m for m in sink.json if m["type"] == typ]


def test_partials_dedupe_and_picture_follows_once(graph, mock_llm, fake_pictures):
    async def run():
        cs = _session(graph, mock_llm)
        gp, gc = await _two_sides(cs)

        class FakeASR:
            async def events(self):
                for t in ["ரவி மாமா", "ரவி மாமா சீடை", "ரவி மாமா சீடை பண்ணான்"]:
                    yield ASREvent(t, final=False)
                yield ASREvent("ரவி மாமா சீடை பண்ணான்.", final=True)

            async def finish(self):
                pass

        side = cs.sides["grandparent"]
        side.asr = FakeASR()
        await cs._asr_loop(side)
        await asyncio.gather(*list(cs.glance_tasks))
        g = _glances(gc)
        keys = [it["key"] for m in g for it in m["items"]]
        assert keys == ["p_ravi_mama", "lex:ta:seedai"]  # each key once across 3 partials + the final
        who = g[0]["items"][0]
        assert who["kind"] == "who" and who["title"] == "ரவி மாமா" and "Ravi" in who["body"] and g[0]["role"] == "grandparent"
        seedai = g[1]["items"][0]
        assert seedai["kind"] == "term" and seedai["native"] == "சீடை" and seedai["image_url"] == ""
        imgs = _glances(gc, "glance_image")
        assert imgs == [{"type": "glance_image", "key": "lex:ta:seedai", "image_url": "https://img.test/Seedai.jpg",
                         "image_credit": "Wikipedia: Seedai", "source_url": "https://en.wikipedia.org/wiki/Seedai"}]
        assert fake_pictures.calls == ["Seedai"]
        # partials reach the listener before translation: the first glance precedes the transcript
        order = [m["type"] for m in gc.json]
        assert order.index("glance") < order.index("transcript")
    asyncio.run(run())


def test_second_call_gets_picture_instantly_from_cache(graph, mock_llm, fake_pictures):
    async def run():
        for expect_followup in (True, False):
            cs = _session(graph, mock_llm)
            gp, gc = await _two_sides(cs)
            await cs._glance(cs.sides["grandparent"], "சீடை பண்ணான்")
            await asyncio.gather(*list(cs.glance_tasks))
            item = _glances(gc)[0]["items"][0]
            assert bool(item["image_url"]) is (not expect_followup)
            assert bool(_glances(gc, "glance_image")) is expect_followup
    asyncio.run(run())


def test_unknown_relative_becomes_ask_item(graph, mock_llm):
    async def run():
        cs = _session(graph, mock_llm)
        gp, gc = await _two_sides(cs)
        await cs.on_text("grandparent", "உன் சித்தப்பா நாளைக்கு வருவான்.")
        asks = [it for m in _glances(gc) for it in m["items"] if it["kind"] == "ask"]
        assert asks and asks[0]["term"] == "சித்தப்பா" and asks[0]["guess"] == "உன்" and asks[0]["key"] == "ask:சித்தப்பா"
        order = [m["type"] for m in gc.json]
        assert order.index("glance") < order.index("transcript")  # typed text: glance before translation
    asyncio.run(run())


def test_grandchild_side_sends_no_glance(graph, mock_llm):
    async def run():
        cs = _session(graph, mock_llm)
        gp, gc = await _two_sides(cs)
        await cs._glance(cs.sides["grandchild"], "pongal and seedai")
        assert _glances(gp) == [] and _glances(gc) == []
    asyncio.run(run())


def test_past_glossary_card_becomes_instant_term(graph, mock_llm):
    from app.db import models as m
    from app.db.session import session_scope
    with session_scope() as s:
        s.add(m.GlossaryEntry(family_id=graph.family_id, card={"kind": "idiom", "source": "கை நிறைய காசு", "literal": "hand full of money",
                                                               "meaning": "earning well", "why_it_matters": "praise, not greed"}))
    eng = glance_mod.engine_for(Translator(graph, mock_llm))
    items = [it for it, _ in eng.items("அவன் இப்போ கை நிறைய காசு சம்பாதிக்கிறான்", "p_kamala", "p_arjun")]
    g = [it for it in items if it["key"].startswith("gloss:")]
    assert g and g[0]["kind"] == "saying" and g[0]["body"].startswith("earning well")


# ---- REST ----------------------------------------------------------------------
def test_rest_lexicon_and_glance(fake_pictures):
    from app.main import app
    with TestClient(app) as c:
        r = c.get("/api/cards/lexicon/ta").json()
        assert r["available"] and r["count"] >= 120 and r["verified"] is False and "food" in r["by_category"]
        assert c.get("/api/cards/lexicon/xx").status_code == 404
        r = c.post("/api/cards/glance", json={"text": "பொங்கலுக்கு சீடை பண்ணணும்"}).json()
        kinds = {it["key"]: it["kind"] for it in r["items"]}
        assert kinds.get("lex:ta:seedai") == "term"
        assert "Seedai" in fake_pictures.calls  # first sighting queued a background fetch
        json.dumps(r, ensure_ascii=False)
