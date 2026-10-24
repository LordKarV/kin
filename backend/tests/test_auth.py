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
