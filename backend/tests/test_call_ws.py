"""End-to-end call over the WebSocket transport with mock ASR/TTS and a mocked LLM."""
import json
import httpx
import pytest
from fastapi.testclient import TestClient

from app import llm as llm_mod
from app.main import app


@pytest.fixture
def mock_llm(monkeypatch):
    def handler(req: httpx.Request):
        body = json.loads(req.content)
        user = body["messages"][-1]["content"]
        reply = {"translation": "Your uncle Ravi mama called yesterday." if "மாமா" in user else "Okay, Paatti.",
                 "grounded_spans": [{"source": "மாமா", "rendered": "your uncle Ravi mama (Mom's younger brother)", "node_id": "p_ravi_mama"}] if "மாமா" in user else [],
                 "pragmatics_cards": [], "passthrough_kept": [], "confidence": 0.9}
        return httpx.Response(200, json={"id": "x", "object": "chat.completion", "created": 0, "model": "m",
                                         "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": json.dumps(reply)}}],
                                         "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})
    fake = llm_mod.LLM(api_key="k", base_url="https://api.meta.ai/v1", model="m", transport=httpx.MockTransport(handler))
    monkeypatch.setattr(llm_mod, "_default", fake)
    yield fake
    monkeypatch.setattr(llm_mod, "_default", None)


def _drain_until(ws, typ, limit=20):
    seen = []
    for _ in range(limit):
        msg = ws.receive()
        if "text" in msg:
            data = json.loads(msg["text"])
            seen.append(data)
            if data.get("type") == typ:
                return data, seen
        else:
            seen.append({"type": "_bytes", "n": len(msg["bytes"])})
    raise AssertionError(f"never saw {typ}: {seen}")


def test_text_utterance_is_translated_grounded_and_voiced_to_peer(mock_llm):
    with TestClient(app) as c:
        cid = c.post("/api/calls", json={"family_id": 1}).json()["id"]
        with c.websocket_connect(f"/ws/call/{cid}?role=grandparent&person=p_kamala") as gp, \
             c.websocket_connect(f"/ws/call/{cid}?role=grandchild&person=p_arjun") as gc:
            assert gp.receive_json()["type"] == "joined"
            assert gc.receive_json()["type"] == "joined"
            gp.send_json({"type": "text", "text": "உன் மாமா நேத்து போன் பண்ணான்."})
            tr, seen = _drain_until(gc, "transcript")
            assert tr["speaker"] == "p_kamala" and tr["listener"] == "p_arjun"
            assert tr["translation"].startswith("Your uncle Ravi mama")
            assert tr["grounded_spans"][0]["node_id"] == "p_ravi_mama"
            assert {"link_ms", "mt_ms"} <= set(tr["latencies"])
            end, seen2 = _drain_until(gc, "audio_end")
            assert any(s.get("type") == "_bytes" and s["n"] > 0 for s in seen2), "peer must receive TTS audio bytes"
            lat, _ = _drain_until(gc, "latency")
            assert {"link_ms", "mt_ms", "tts_first_byte_ms", "total_ms", "asr_ms"} <= set(lat["latencies"])
            # speaker side sees its own transcript too (no audio)
            own, _ = _drain_until(gp, "transcript")
            assert own["src_text"].startswith("உன் மாமா")
        utts = c.get(f"/api/calls/{cid}/utterances").json()
        assert len(utts) == 1 and utts[0]["latencies"]["mt_ms"] >= 0


def test_reverse_direction_targets_heritage_language(mock_llm):
    with TestClient(app) as c:
        cid = c.post("/api/calls", json={"family_id": 1}).json()["id"]
        with c.websocket_connect(f"/ws/call/{cid}?role=grandparent&person=p_kamala") as gp, \
             c.websocket_connect(f"/ws/call/{cid}?role=grandchild&person=p_arjun") as gc:
            gp.receive_json(); gc.receive_json()
            gc.send_json({"type": "text", "text": "I will call you on Sunday, Paatti."})
            tr, _ = _drain_until(gp, "transcript")
            assert tr["speaker"] == "p_arjun" and tr["listener"] == "p_kamala" and tr["target_lang"] == "ta"


def test_compare_endpoint_returns_generic_and_grounded(mock_llm):
    with TestClient(app) as c:
        r = c.post("/api/translate/compare", json={"text": "உன் மாமா நேத்து போன் பண்ணான்.", "speaker": "p_kamala", "listener": "p_arjun"})
        assert r.status_code == 200
        j = r.json()
        assert "generic" in j and "grounded" in j and j["grounded"]["grounded_spans"][0]["node_id"] == "p_ravi_mama"
