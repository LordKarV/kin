"""Review fix pass: when a real key or a public host is configured, /api and /ws require the key; dev stays open."""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app


def test_dev_mode_is_open_but_dial_always_needs_key():
    with TestClient(app) as c:
        assert c.get("/api/family/graph").status_code == 200
        assert c.post("/api/phone/dial", json={"to": "+15550001"}).status_code == 401


def test_real_key_locks_api_and_ws(monkeypatch):
    monkeypatch.setenv("KIN_API_KEY", "s3cret")
    from app.config import get_settings
    get_settings.cache_clear()
    with TestClient(app) as c:
        assert c.get("/health").status_code == 200
        assert c.get("/connectors/muse.md").status_code == 200
        assert c.get("/api/family/graph").status_code == 401
        assert c.get("/api/family/graph", headers={"X-KIN-Key": "s3cret"}).status_code == 200
        cid = c.post("/api/calls", json={}, headers={"X-KIN-Key": "s3cret"}).json()["id"]
        with pytest.raises(WebSocketDisconnect):
            with c.websocket_connect(f"/ws/call/{cid}?role=grandparent&person=p_kamala") as ws:
                ws.receive_json()
        with c.websocket_connect(f"/ws/call/{cid}?role=grandparent&person=p_kamala&key=s3cret") as ws:
            assert ws.receive_json()["type"] == "joined"


def test_refuses_to_start_publicly_with_default_key(monkeypatch):
    monkeypatch.setenv("PUBLIC_WSS_HOST", "abc.ngrok.app")
    from app.config import get_settings
    get_settings.cache_clear()
    with pytest.raises(RuntimeError):
        with TestClient(app):
            pass


# ---- legacy routes never reach the world space or a world call (D2) ---------------------------------------------

@pytest.fixture
def offline_llm(monkeypatch):
    """Sign-up asks Muse for name forms in the background; answer with none so nothing leaves the machine."""
    import json
    import httpx
    from app import llm as llm_mod
    def handler(req: httpx.Request):
        msg = {"role": "assistant", "content": json.dumps({"forms": []})}
        return httpx.Response(200, json={"id": "x", "object": "chat.completion", "created": 0, "model": "m",
                                         "choices": [{"index": 0, "finish_reason": "stop", "message": msg}]})
    monkeypatch.setattr(llm_mod, "_default", llm_mod.LLM(api_key="k", base_url="https://api.meta.ai/v1", model="m",
                                                         transport=httpx.MockTransport(handler)))


def _world_call_with_a_line() -> tuple[int, int]:
    """The space is family 1 here (no seed): a world call holding one transcript line and a summary."""
    from app.db import models as m
    from app.db.session import session_scope
    with session_scope() as s:
        space = s.query(m.Family).filter_by(kind="space").one()
        mei = s.query(m.Person).filter_by(family_id=space.id).first()
        call = m.Call(family_id=space.id, transport="livekit", mode="world")
        s.add(call); s.flush()
        s.add(m.Utterance(call_id=call.id, speaker_id=mei.id, src_text="我和林去攀岩了"))
        s.add(m.CallSummary(call_id=call.id, summary="climbing with Lin", extracted={}))
        return space.id, call.id


def test_legacy_routes_404_for_the_space_and_world_calls(monkeypatch, offline_llm):
    monkeypatch.setenv("SEED_DEMO_FAMILY", "0")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.memory import service
    def no_llm():
        raise AssertionError("a world transcript reached the legacy summarizer")
    monkeypatch.setattr(service, "get_llm", no_llm)
    key = {"X-KIN-Key": "change-me"}
    with TestClient(app) as c:
        assert c.post("/api/users", json={"name": "Mei", "lang": "zh"}).status_code == 200
        sid, wid = _world_call_with_a_line()
        assert sid == get_settings().demo_family_id  # the probe from the review: every default lands on the space
        assert c.get("/api/calls").json() == []
        for path in (f"/api/calls/{wid}/utterances", f"/api/calls/{wid}/summary", "/api/family/graph",
                     f"/api/family/graph?family_id={sid}", "/api/glossary", f"/api/family/suggest?term=x&family_id={sid}"):
            assert c.get(path).status_code == 404, path
        for path, body in ((f"/api/calls/{wid}/end", None), (f"/api/calls/{wid}/approve", {"remember_topics": []}),
                           ("/api/calls", {}), ("/api/cards/glance", {"text": "Lin"}), ("/api/translate/compare", {"text": "Lin"}),
                           ("/api/translate/grounded", {"text": "Lin"}),
                           ("/api/family/relative", {"family_id": sid, "path": "mother", "name": "X"})):
            assert c.post(path, json=body).status_code == 404, path
        assert c.patch("/api/family/language", json={"code": "hi"}).status_code == 404
        for path in ("/api/v1/family/graph", "/api/v1/calls/recent", "/api/v1/memory/search?q=Lin", "/api/v1/glossary"):
            assert c.get(path, headers=key).status_code == 404, path
        assert all(f["id"] != sid for f in c.get("/api/family/all").json())
        # a real legacy family next to the space still works
        fid = c.post("/api/family/setup", json={"language": "ta", "your_name": "Arjun", "their_name": "Kamala"}).json()["family_id"]
        assert c.get(f"/api/family/graph?family_id={fid}").status_code == 200
        lid = c.post("/api/calls", json={"family_id": fid}).json()["id"]
        assert [x["id"] for x in c.get("/api/calls").json()] == [lid]
    from app.db import models as m
    from app.db.session import session_scope
    with session_scope() as s:
        assert s.get(m.Family, sid).heritage_lang == "zh"
        assert s.get(m.Call, wid).ended_at is None
