"""Latency split: call A (speech) returns without waiting for call B (cards); B lands as an `enrich` event; hedge races a slow A."""
import json
import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app import llm as llm_mod
from app.main import app
from app.mt import translate as tr_mod
from app.mt.schemas import SpeechOut
from app.mt.translate import Translator
from tests.graph_fixtures import graph  # noqa: F401
from tests.test_call_ws import _drain_until

SPEECH = {"a_translation": "I'm lonely, time just doesn't pass.", "grounded_spans": [], "passthrough_kept": [], "confidence": 0.9}
CARD = {"kind": "idiom", "source": "பொழுதே போகலை", "literal": "The time isn't passing at all", "meaning": "I'm lonely and bored",
        "why_it_matters": "A gentle plea for company."}


def _ok(reply: dict) -> httpx.Response:
    return httpx.Response(200, json={"id": "x", "object": "chat.completion", "created": 0, "model": "m",
                                     "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": json.dumps(reply)}}],
                                     "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})


def _llm(cards_handler, speech_handler=lambda: _ok(SPEECH), seen=None):
    def handler(req: httpx.Request):
        body = json.loads(req.content)
        if seen is not None:
            seen.append(body)
        return cards_handler() if body["response_format"]["json_schema"]["name"] == "CardsOut" else speech_handler()
    return llm_mod.LLM(api_key="k", base_url="https://api.meta.ai/v1", model="m", transport=httpx.MockTransport(handler))


@pytest.fixture
def use_llm(monkeypatch):
    def _set(fake):
        monkeypatch.setattr(llm_mod, "_default", fake)
    yield _set
    monkeypatch.setattr(llm_mod, "_default", None)


def _slow_cards(delay=0.6, fail=False):
    def h():
        time.sleep(delay)
        return httpx.Response(500, json={"error": {"message": "boom"}}) if fail else _ok({"pragmatics_cards": [CARD]})
    return h


def test_transcript_does_not_wait_for_cards_and_enrich_follows(use_llm):
    use_llm(_llm(_slow_cards(0.6)))
    with TestClient(app) as c:
        cid = c.post("/api/calls", json={"family_id": 1}).json()["id"]
        with c.websocket_connect(f"/ws/call/{cid}?role=grandparent&person=p_kamala") as gp:
            gp.receive_json()
            t0 = time.perf_counter()
            gp.send_json({"type": "text", "text": "பொழுதே போகலை."})
            tr, _ = _drain_until(gp, "transcript")
            assert time.perf_counter() - t0 < 0.5, "transcript must not wait for call B"
            assert tr["translation"].startswith("I'm lonely") and tr["pragmatics_cards"] == []
            assert {"a_ms", "mt_ms"} <= set(tr["latencies"])
            enrich, _ = _drain_until(gp, "enrich")
            assert enrich["utterance_id"] == tr["utterance_id"] and enrich["pragmatics_cards"][0]["kind"] == "idiom"
        rows = c.get("/api/glossary").json()
        assert rows and rows[0]["card"]["source"] == "பொழுதே போகலை"


def test_cards_failure_never_breaks_the_turn(use_llm):
    use_llm(_llm(_slow_cards(0.05, fail=True)))
    with TestClient(app) as c:
        cid = c.post("/api/calls", json={"family_id": 1}).json()["id"]
        with c.websocket_connect(f"/ws/call/{cid}?role=grandparent&person=p_kamala") as gp:
            gp.receive_json()
            gp.send_json({"type": "text", "text": "பொழுதே போகலை."})
            _, seen = _drain_until(gp, "latency")
            assert not any(m.get("type") == "error" for m in seen)
            gp.send_json({"type": "text", "text": "இன்னைக்கு வெயில்."})  # session still alive after a failed B
            tr, _ = _drain_until(gp, "transcript")
            assert tr["translation"]


def test_translate_merges_cards_and_tolerates_b_failure(graph):
    ok = Translator(graph, _llm(lambda: _ok({"pragmatics_cards": [CARD]})))
    res = ok.translate("பொழுதே போகலை.", speaker="p_kamala", listener="p_arjun")
    assert res.result.pragmatics_cards[0].kind == "idiom" and "b_ms" in res.latencies and res.cards is None
    bad = Translator(graph, _llm(lambda: httpx.Response(500, json={"error": {"message": "boom"}})))
    res = bad.translate("பொழுதே போகலை.", speaker="p_kamala", listener="p_arjun")
    assert res.error is None and res.result.pragmatics_cards == [] and "b_error" in res.latencies


def test_a_and_b_share_the_cached_prefix(graph):
    seen = []
    Translator(graph, _llm(lambda: _ok({"pragmatics_cards": []}), seen=seen)).translate("உன் மாமா நேத்து போன் பண்ணான்.", speaker="p_kamala", listener="p_arjun")
    a, b = sorted(seen, key=lambda r: r["response_format"]["json_schema"]["name"] == "CardsOut")
    assert a["messages"][0]["content"] == b["messages"][0]["content"]  # byte-identical system prompt
    assert a["prompt_cache_key"] == b["prompt_cache_key"] == f"kin-{graph.family_id}-p_arjun"
    assert a["reasoning_effort"] == tr_mod.SPEECH_EFFORT and b["reasoning_effort"] == tr_mod.CARDS_EFFORT
    assert "pragmatics_cards" not in a["response_format"]["json_schema"]["schema"]["properties"]


def test_hedge_fires_a_duplicate_when_a_is_slow():
    calls, lock = [], threading.Lock()

    def speech():
        with lock:
            calls.append(time.perf_counter())
            first = len(calls) == 1
        if first:
            time.sleep(1.0)  # the slow original
        return _ok(SPEECH)

    fake = _llm(lambda: _ok({"pragmatics_cards": []}), speech_handler=speech)
    t0 = time.perf_counter()
    out = fake.structured(SpeechOut, system="s", user="u", hedge_after_s=0.05)
    assert out.a_translation.startswith("I'm lonely")
    assert len(calls) == 2 and time.perf_counter() - t0 < 0.6


def test_no_hedge_when_a_is_fast():
    calls = []
    fake = _llm(lambda: _ok({}), speech_handler=lambda: calls.append(1) or _ok(SPEECH))
    fake.structured(SpeechOut, system="s", user="u", hedge_after_s=0.5)
    assert len(calls) == 1
