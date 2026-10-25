"""Translator/linker additive changes for world calls (docs/ARCHITECTURE.md 8.4); legacy prompts stay byte-identical."""
import hashlib
import json
import re

import httpx

from app import llm as llm_mod
from app.graph.kinship import FamilyGraph, Node
from app.graph.linker import Linker
from app.mt.schemas import CardsOut
from app.mt.translate import Translator
from tests.graph_fixtures import graph  # noqa: F401

SPEECH = {"a_translation": "ok", "grounded_spans": [], "passthrough_kept": [], "confidence": 0.9}
LIN = {"source": "Lin", "name": "Lin", "owner": "speaker", "owner_name": "Mei", "relation": "friend", "context": "climbing"}
HIST = [("p_arjun", "Hi Paatti", None)]
# sha256[:16] of (system, user) captured from the pre-change translate.py with these exact inputs
GOLDEN = {("en", "SpeechOut"): ("a9a0ab5bf29403f0", "23cc2f9b68531468"), ("en", "CardsOut"): ("a9a0ab5bf29403f0", "34ddc751aaf4ebe3"),
          ("ta", "SpeechOut"): ("4f7bdf740322fdbf", "1880b01893e5f32b"), ("ta", "CardsOut"): ("4f7bdf740322fdbf", "14429256d6619634")}


def _llm(seen: list, cards: dict | None = None):
    def handler(req: httpx.Request):
        body = json.loads(req.content)
        seen.append(body)
        reply = (cards or {"pragmatics_cards": []}) if body["response_format"]["json_schema"]["name"] == "CardsOut" else SPEECH
        return httpx.Response(200, json={"id": "x", "object": "chat.completion", "created": 0, "model": "m",
                                         "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": json.dumps(reply)}}],
                                         "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})
    return llm_mod.LLM(api_key="k", base_url="https://api.meta.ai/v1", model="m", transport=httpx.MockTransport(handler))


def _by_call(seen: list) -> dict:
    return {b["response_format"]["json_schema"]["name"]: b for b in seen}


def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def test_legacy_prompts_and_cache_key_are_byte_identical(graph):
    for tl, sp, li, text in [("en", "p_kamala", "p_arjun", "உன் மாமா நேத்து போன் பண்ணான்."), ("ta", "p_arjun", "p_kamala", "Ravi mama called me yesterday.")]:
        seen = []
        Translator(graph, _llm(seen)).translate(text, speaker=sp, listener=li, history=HIST, target_lang=tl)
        for name, b in _by_call(seen).items():
            assert (_h(b["messages"][0]["content"]), _h(b["messages"][-1]["content"])) == GOLDEN[(tl, name)], (tl, name)
            assert b["prompt_cache_key"] == f"kin-{graph.family_id}-{li}"
            assert "new_people" not in b["messages"][-1]["content"] and "new_people" not in json.dumps(b["response_format"])
        if tl == "ta":
            assert "(natural spoken Tamil, Tamil script)" in _by_call(seen)["SpeechOut"]["messages"][-1]["content"]


def test_hindi_target_names_hindi_script(graph):
    seen = []
    Translator(graph, _llm(seen)).translate("Ravi mama called.", speaker="p_arjun", listener="p_kamala", target_lang="hi")
    user = _by_call(seen)["SpeechOut"]["messages"][-1]["content"]
    assert "(natural spoken Hindi, Hindi script)" in user and "Tamil script" not in user


def test_roster_replaces_roster_block_and_keys_cache(graph):
    seen = []
    roster = "p_mei | Mei | 美 | Arjun's friend Mei | Mei"
    res = Translator(graph, _llm(seen, {"pragmatics_cards": [], "new_people": [LIN]})).translate_speech(
        "I went climbing with Lin.", "p_arjun", "p_kamala", target_lang="ta", roster=roster)
    cards, _b_ms, people = res.cards.result()  # resolve B first: it runs on another thread
    calls = _by_call(seen)
    system = calls["SpeechOut"]["messages"][0]["content"]
    assert roster in system and "FAMILY ROSTER" not in system
    key = f"kin-{graph.family_id}-ta-{hashlib.sha1(roster.encode()).hexdigest()[:10]}"
    assert calls["SpeechOut"]["prompt_cache_key"] == key == calls["CardsOut"]["prompt_cache_key"]
    assert "new_people" in calls["CardsOut"]["messages"][-1]["content"]
    assert "new_people" not in calls["SpeechOut"]["messages"][-1]["content"]
    assert "new_people" in json.dumps(calls["CardsOut"]["response_format"])
    assert "DISHES / PLACES / EVENTS" not in system  # graph things are not listener-scoped
    assert cards == [] and people[0].name == "Lin" and people[0].owner == "speaker"
    out = Translator.with_cards(res)  # 3-tuple still folds in
    assert "b_error" not in out.latencies and "b_ms" in out.latencies and out.result.pragmatics_cards == []


def test_several_listeners_adds_neutral_line(graph):
    seen = []
    Translator(graph, _llm(seen)).translate_speech("Ravi mama called.", "p_arjun", None, roster="p_x | X | | X | ").cards.result()
    calls = _by_call(seen)
    assert 'Several listeners: use names, never "your".' in calls["SpeechOut"]["messages"][-1]["content"]
    assert "several listeners" in calls["SpeechOut"]["messages"][0]["content"]
    seen.clear()
    Translator(graph, _llm(seen)).translate("Ravi mama called.", speaker="p_arjun", listener="p_kamala")
    assert "Several listeners" not in _by_call(seen)["SpeechOut"]["messages"][-1]["content"]


def test_unknown_slugs_do_not_raise(graph):
    seen = []
    tr = Translator(graph, _llm(seen))
    res = tr.translate("hello there", speaker="p_nobody", listener="p_ghost")
    assert res.error is None
    user = _by_call(seen)["SpeechOut"]["messages"][-1]["content"]
    assert user.startswith("Speaker: p_nobody. Listener: p_ghost.")
    assert tr.system_prompt(None) and tr.user_prompt("x", "p_nobody", None, [], [("p_nobody", "a", None)], [])


def test_extra_spans_join_the_prompt_without_overlap_duplicates(graph):
    seen = []
    text = "我和林去攀岩了 Ravi mama"
    extra = [{"start": 2, "end": 3, "source": "林", "node_id": "p_lin_17", "type": "person", "rendered": "Mei's friend Lin", "confidence": 0.95},
             {"start": 8, "end": 12, "source": "Ravi", "node_id": "p_bogus", "type": "person", "rendered": "dup", "confidence": 0.95}]
    res = Translator(graph, _llm(seen)).translate_speech(text, "p_arjun", "p_kamala", extra_spans=extra, roster="r")
    user = _by_call(seen)["SpeechOut"]["messages"][-1]["content"]
    assert "'林' → p_lin_17: Mei's friend Lin" in user and "p_bogus" not in user
    assert [s.node for s in res.spans].count("p_lin_17") == 1 and "p_bogus" not in {s.node for s in res.spans}
    assert any(g.node_id == "p_lin_17" for g in res.result.grounded_spans)  # _reconcile keeps the world span


def test_malformed_extra_spans_are_dropped(graph):
    seen = []
    text = "I had rasam with Lin"
    extra = [{"start": 17, "end": 99, "source": "Lin", "node_id": "p_far"}, {"start": 17, "end": 20, "source": "", "node_id": "p_empty"},
             {"source": "Lin", "node_id": "p_nokeys"}, {"start": 17, "end": 20, "source": "Lin", "node_id": "p_lin"}]
    res = Translator(graph, _llm(seen)).translate_speech(text, "p_arjun", "p_kamala", extra_spans=extra, roster="r")
    res.cards.result()
    nodes = {s.node for s in res.spans}
    assert "p_lin" in nodes and not nodes & {"p_far", "p_empty", "p_nokeys"}
    assert not any(s.node and s.node in graph.thing_by_slug for s in res.spans)  # unscoped graph things skipped on world calls


def test_cards_out_parses_without_new_people():
    assert CardsOut.model_validate({"pragmatics_cards": []}).new_people == []


def test_linker_lang_and_keyterms_include_names(graph):
    assert Linker(graph, lang="hi").table.code == "hi"
    assert Linker(graph, lang="xx").table.code == "ta"  # unknown language: today's fallback
    lin = Node(99, "p_lin_99", "Lin", "", "", None, False, False, "", [])
    g = FamilyGraph(1, "zh", [lin], [], [])
    assert "Lin" in Linker(g).keyterms()
    assert not [k for k in Linker(graph).keyterms() if re.search(r"[^\x00-\x7f]", k)]
