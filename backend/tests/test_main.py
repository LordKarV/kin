from fastapi.testclient import TestClient
from app.main import app

def test_health_ok():
    with TestClient(app) as c:
        r = c.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_invite_link_opens_the_app():
    """Share sends http(s)://<server>/?call=N; the page must hand the app kin://join with the same query."""
    with TestClient(app) as c:
        r = c.get("/?call=5&key=k%26y&code=abc&evil=%3Cscript%3E")
        bare = c.get("/")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert 'href="kin://join?call=5&amp;key=k%26y&amp;code=abc"' in r.text and "refresh" in r.text
    assert "evil" not in r.text and "<script>" not in r.text
    assert bare.status_code == 200 and "kin://" not in bare.text


def test_shutdown_closes_live_world_calls(monkeypatch):
    """A restart mid-call must still run each live world's final extraction and flush (LiveWorld.close)."""
    from types import SimpleNamespace

    from app.audio import pipeline
    closed = []
    live = SimpleNamespace(call_id=7, world=SimpleNamespace(close=lambda: closed.append(7)))
    broken = SimpleNamespace(call_id=8, world=SimpleNamespace(close=lambda: 1 / 0))
    legacy = SimpleNamespace(call_id=9, world=None)
    monkeypatch.setattr(pipeline.registry, "active", lambda: [live, broken, legacy])
    with TestClient(app):
        pass
    assert closed == [7]  # the broken one is logged, not raised, and the legacy session has no world
