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


# ---- legacy leak fixes (ARCHITECTURE section 10) ----------------------------------------------------------------

def _other_family_call(extracted: dict) -> int:
    from app.db import models as m
    from app.db.session import init_db, session_scope
    init_db()
    with session_scope() as s:
        fam = m.Family(name="Chen", heritage_lang="zh")
        s.add(fam); s.flush()
        s.add_all([m.Person(family_id=fam.id, slug="p_nainai", display_name="Nainai", birth_year_approx=1950),
                   m.Person(family_id=fam.id, slug="p_wei", display_name="Wei", is_learner=True)])
        call = m.Call(family_id=fam.id)
        s.add(call); s.flush()
        s.add(m.CallSummary(call_id=call.id, summary="", extracted=extracted))
        return call.id


def test_approve_in_a_non_krishnan_family_uses_that_familys_slugs(monkeypatch):
    from app.graph.linker import Linker
    from app.memory.service import approve_call
    seen = []
    orig = Linker.link
    def spy(self, text, speaker, listener, context=None):
        seen.append((speaker, listener)); return orig(self, text, speaker, listener, context)
    monkeypatch.setattr(Linker, "link", spy)
    cid = _other_family_call({"people": [{"name": "Lin", "how_referred": "Lin", "inferred_relation": "friend", "sensitive": False}],
                              "dishes": [{"name": "jiaozi", "note": "", "sensitive": False}], "places": [], "events": [], "topics": []})
    r = approve_call(cid, [])
    assert r["added_people"] == ["p_lin"] and r["added_things"] == ["d_jiaozi"]
    assert seen and set(seen) == {("p_nainai", "p_wei")}


def test_two_chinese_names_get_distinct_slugs():
    from app.memory.service import approve_call
    ppl = [{"name": n, "how_referred": n, "inferred_relation": "friend", "sensitive": False} for n in ("林", "王")]
    cid = _other_family_call({"people": ppl, "dishes": [], "places": [], "events": [], "topics": []})
    r = approve_call(cid, [])
    assert len(r["added_people"]) == 2 and len(set(r["added_people"])) == 2 and "p_x" not in r["added_people"]


def test_fade_learner_lookup_is_family_scoped():
    from app.db import models as m
    from app.db.session import init_db, session_scope
    from app.fade.service import _learner_id
    init_db()
    with session_scope() as s:
        a, b = m.Family(name="A", heritage_lang="ta"), m.Family(name="B", heritage_lang="zh")
        s.add_all([a, b]); s.flush()
        pa, pb = m.Person(family_id=a.id, slug="p_kid", display_name="Kid"), m.Person(family_id=b.id, slug="p_kid", display_name="Kid")
        s.add_all([pa, pb]); s.flush()
        assert _learner_id(s, "p_kid", b.id) == pb.id and _learner_id(s, "p_kid", a.id) == pa.id
        with pytest.raises(ValueError):
            _learner_id(s, "p_kid", b.id + 99)


def test_fade_verification_by_utterance_writes_the_listeners_own_family():
    from sqlalchemy import select
    from app.db import models as m
    from app.db.session import init_db, session_scope
    from app.fade.service import record_verification
    init_db()
    with session_scope() as s:
        a, b = m.Family(name="A", heritage_lang="ta"), m.Family(name="B", heritage_lang="ta")
        s.add_all([a, b]); s.flush()
        pa, pb = m.Person(family_id=a.id, slug="p_kid", display_name="Kid"), m.Person(family_id=b.id, slug="p_kid", display_name="Kid")
        s.add_all([pa, pb]); s.flush()
        call = m.Call(family_id=b.id)
        s.add(call); s.flush()
        u = m.Utterance(call_id=call.id, listener_id=pb.id, src_text="சாப்பிட்டியா கண்ணா")
        s.add(u); s.flush()
        ids = (pa.id, pb.id, u.id)
    r = record_verification({"utterance_id": ids[2], "understood": True})
    assert r["lemmas"]
    with session_scope() as s:
        learners = set(s.scalars(select(m.Mastery.learner_id)))
    assert learners == {ids[1]}
