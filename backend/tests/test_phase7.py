"""Phase 7: glossary audio artifact, latency summary endpoint."""
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app import llm as llm_mod
from app.main import app
from tests.test_call_ws import _drain_until


@pytest.fixture
def card_llm(monkeypatch):
    def handler(req: httpx.Request):
        reply = {"translation": "I'm lonely, time just doesn't pass.", "grounded_spans": [],
                 "pragmatics_cards": [{"kind": "idiom", "source": "பொழுதே போகலை", "literal": "The time isn't passing at all", "meaning": "I'm lonely and bored", "why_it_matters": "A gentle plea for company, not a complaint about clocks."}],
                 "passthrough_kept": [], "confidence": 0.9}
        return httpx.Response(200, json={"id": "x", "object": "chat.completion", "created": 0, "model": "m",
                                         "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": json.dumps(reply)}}],
                                         "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})
    fake = llm_mod.LLM(api_key="k", base_url="https://api.meta.ai/v1", model="m", transport=httpx.MockTransport(handler))
    monkeypatch.setattr(llm_mod, "_default", fake)
    yield fake
    monkeypatch.setattr(llm_mod, "_default", None)


def test_card_gets_audio_clip_served_from_media(card_llm, monkeypatch):
    monkeypatch.setenv("GLOSSARY_AUDIO", "1")
    from app.config import get_settings
    get_settings.cache_clear()
    with TestClient(app) as c:
        cid = c.post("/api/calls", json={"family_id": 1}).json()["id"]
        with c.websocket_connect(f"/ws/call/{cid}?role=grandparent&person=p_kamala") as gp:
            gp.receive_json()
            gp.send_json({"type": "text", "text": "பொழுதே போகலை."})
            tr, _ = _drain_until(gp, "transcript")
            assert tr["pragmatics_cards"][0]["kind"] == "idiom"
        rows = []
        for _ in range(40):
            rows = c.get("/api/glossary").json()
            if rows and rows[0]["audio_url"]:
                break
            time.sleep(0.1)
        assert rows and rows[0]["audio_url"].startswith("/media/glossary/")
        r = c.get(rows[0]["audio_url"])
        assert r.status_code == 200 and r.content[:4] == b"RIFF"


def test_latency_summary_has_percentiles_and_budget(card_llm):
    with TestClient(app) as c:
        cid = c.post("/api/calls", json={"family_id": 1}).json()["id"]
        with c.websocket_connect(f"/ws/call/{cid}?role=grandparent&person=p_kamala") as gp:
            gp.receive_json()
            for t in ("பொழுதே போகலை.", "இன்னைக்கு வெயில்."):
                gp.send_json({"type": "text", "text": t}); _drain_until(gp, "latency")
        j = c.get("/api/latency/summary").json()
        assert j["n"] == 2
        assert {"asr_ms", "link_ms", "mt_ms", "tts_first_byte_ms", "total_ms"} <= set(j["stages"])
        assert j["stages"]["mt_ms"]["p50"] >= 0 and j["stages"]["mt_ms"]["p95"] >= j["stages"]["mt_ms"]["p50"]
        assert j["budget"]["total_p50_ms"] == 2000 and j["budget"]["total_p95_ms"] == 3000
