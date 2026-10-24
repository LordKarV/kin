"""Phase 6: post-call summary + extraction with sensitivity rules, memory search, Muse connector endpoints."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import llm as llm_mod
from app.main import app

SUMMARY = "Paatti said her knee is better; Ravi mama is visiting Madurai; she wants Arjun home for Pongal."
EXTRACTION = {"people": [{"name": "Saroja", "how_referred": "chinna paatti", "inferred_relation": "Paatti's younger sister", "sensitive": False}],
              "dishes": [{"name": "adai", "note": "lentil crepe Paatti made on Friday", "sensitive": False}],
              "places": [], "events": [{"name": "Pongal", "when": "January", "sensitive": False}],
              "topics": [{"topic": "knee", "kind": "health", "sensitive": True, "detail": "knee pain improving, new tablets", "lines": [1]}]}


@pytest.fixture
def mock_llm(monkeypatch):
    def handler(req: httpx.Request):
        body = json.loads(req.content)
        rf = body.get("response_format")
        if rf and rf["json_schema"]["name"] == "ExtractionOut":
            content = json.dumps(EXTRACTION)
        elif rf:
            content = json.dumps({"translation": "ok", "grounded_spans": [], "pragmatics_cards": [], "passthrough_kept": [], "confidence": 0.9})
        else:
            content = SUMMARY
        return httpx.Response(200, json={"id": "x", "object": "chat.completion", "created": 0, "model": "m",
                                         "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
                                         "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})
    fake = llm_mod.LLM(api_key="k", base_url="https://api.meta.ai/v1", model="m", transport=httpx.MockTransport(handler))
    monkeypatch.setattr(llm_mod, "_default", fake)
    yield fake
    monkeypatch.setattr(llm_mod, "_default", None)


def _call_with_utterances(c):
    cid = c.post("/api/calls", json={"family_id": 1}).json()["id"]
    with c.websocket_connect(f"/ws/call/{cid}?role=grandparent&person=p_kamala") as gp:
        gp.receive_json()
        gp.send_json({"type": "text", "text": "என் முழங்கால் வலி கொஞ்சம் குறைஞ்சிருக்கு."})
        gp.receive_json()  # transcript
        gp.receive_json()  # latency
    return cid


def test_end_call_summarizes_and_extracts_with_sensitive_topics_reduced(mock_llm):
    with TestClient(app) as c:
        cid = _call_with_utterances(c)
        r = c.post(f"/api/calls/{cid}/end").json()
        assert r["summary"] == SUMMARY and r["approved"] is False
        topics = r["extracted"]["topics"]
        assert topics[0]["sensitive"] is True and topics[0]["topic"] == "knee" and "detail" not in topics[0]  # topic word only (plan §9)
        assert r["extracted"]["dishes"][0]["name"] == "adai"


def test_approve_applies_non_sensitive_upserts_and_remembered_topics(mock_llm):
    with TestClient(app) as c:
        cid = _call_with_utterances(c)
        c.post(f"/api/calls/{cid}/end")
        r = c.post(f"/api/calls/{cid}/approve", json={"remember_topics": ["knee"]}).json()
        assert r["approved"] is True and "d_adai" in r["added_things"]
        g = c.get("/api/family/graph").json()
        assert any(t["id"] == "d_adai" for t in g["things"])
        assert r["remembered_topics"] == ["knee"]


def test_memory_search_finds_utterances_and_summaries(mock_llm):
    with TestClient(app) as c:
        cid = _call_with_utterances(c)
        c.post(f"/api/calls/{cid}/end")
        hits = c.get("/api/v1/memory/search?q=knee", headers={"X-KIN-Key": "change-me"}).json()["results"]
        assert hits and any("knee" in h["text"].lower() or "முழங்கால்" in h["text"] for h in hits)
        assert all({"kind", "text", "when", "score"} <= set(h) for h in hits)


def test_connector_endpoints_require_key_and_brief_is_public():
    with TestClient(app) as c:
        assert c.get("/api/v1/family/graph").status_code == 401
        assert c.get("/api/v1/family/graph", headers={"X-KIN-Key": "wrong"}).status_code == 401
        assert c.get("/api/v1/family/graph", headers={"Authorization": "Bearer change-me"}).status_code == 200
        assert c.get("/api/v1/calls/recent?limit=5", headers={"X-KIN-Key": "change-me"}).status_code == 200
        assert c.get("/api/v1/glossary", headers={"X-KIN-Key": "change-me"}).status_code == 200
        brief = c.get("/connectors/muse.md")
        assert brief.status_code == 200 and "read-only" in brief.text.lower() and "/api/v1/memory/search" in brief.text


def test_sensitive_utterances_are_withheld_until_remembered(mock_llm):
    with TestClient(app) as c:
        cid = _call_with_utterances(c)
        c.post(f"/api/calls/{cid}/end")
        hdr = {"X-KIN-Key": "change-me"}
        hits = c.get("/api/v1/memory/search?q=முழங்கால்", headers=hdr).json()["results"]
        assert all("முழங்கால்" not in h["text"] for h in hits if h["kind"] == "utterance"), hits
        utts = c.get(f"/api/calls/{cid}/utterances").json()
        assert utts[0]["sensitive_topic"] == "knee" and "withheld" in utts[0]["src_text"]
        c.post(f"/api/calls/{cid}/approve", json={"remember_topics": ["knee"]})
        hits = c.get("/api/v1/memory/search?q=முழங்கால்", headers=hdr).json()["results"]
        assert any("முழங்கால்" in h["text"] for h in hits)


def test_summary_prompt_carries_the_sensitivity_rule(mock_llm, monkeypatch):
    seen = []
    orig = mock_llm.text
    def spy(system, user, **kw):
        seen.append(system); return orig(system, user, **kw)
    monkeypatch.setattr(mock_llm, "text", spy)
    with TestClient(app) as c:
        cid = _call_with_utterances(c)
        c.post(f"/api/calls/{cid}/end")
    assert seen and "health" in seen[0].lower() and "topic word" in seen[0].lower()
