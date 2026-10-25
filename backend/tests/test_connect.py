"""Connect without a link: handles, requests, accept/decline, and ringing an accepted connection. Offline: TestClient,
no LiveKit (agents.ensure is stubbed), no LLM."""
import re

import pytest
from fastapi.testclient import TestClient

from app.api import calls as calls_api
from app.db import models as m
from app.db.session import session_scope
from app.main import app
from app.world.users import create_user


@pytest.fixture
def client(monkeypatch):
    from app.rtc import agent as agent_mod
    monkeypatch.setattr(agent_mod.agents, "ensure", lambda call_id: None)
    with TestClient(app) as c:
        yield c
    calls_api._rings.clear()
    calls_api._done.clear()


def _user(name, lang="en"):
    with session_scope() as s:
        _, p, tok = create_user(s, name, lang)
        return p.slug, {"X-KIN-User": tok}


def _handle(client, h):
    r = client.get("/api/me/handle", headers=h)
    assert r.status_code == 200, r.text
    return r.json()["handle"]


def _contacts(client, h):
    return {c["person"] for c in client.get("/api/contacts", headers=h).json()}


def _ring(client, h, to):
    return client.post("/api/calls/ring", json={"to": to}, headers=h)


def test_handle_is_stable_and_shaped(client):
    _, a = _user("Arjun Kumar")
    _, b = _user("Mei")
    ha = _handle(client, a)
    assert re.fullmatch(r"arjun-\d{4}", ha) and _handle(client, a) == ha
    assert _handle(client, b) != ha
    assert client.get("/api/me/handle").status_code == 401


def test_request_accept_makes_contacts_and_ring_works(client):
    a_slug, a = _user("Arjun")
    b_slug, b = _user("Mei", "zh")
    hb = _handle(client, b)
    assert _ring(client, a, b_slug).status_code == 404  # strangers: no ring
    with client.websocket_connect("/ws/events", headers=b) as b_ws:
        r = client.post("/api/connect", json={"handle": hb.upper()}, headers=a)
        assert r.status_code == 200 and r.json()["status"] == "pending", r.text
        assert b_ws.receive_json() == {"type": "contact.request", "from": {"slug": a_slug, "name": "Arjun"}}
    assert client.post("/api/connect", json={"handle": hb}, headers=a).json()["status"] == "pending"  # idempotent
    reqs = client.get("/api/connect/requests", headers=b).json()
    assert [q["from"] for q in reqs] == [{"slug": a_slug, "name": "Arjun"}] and reqs[0]["created_at"]
    assert client.get("/api/connect/requests", headers=a).json() == []
    assert _ring(client, a, b_slug).status_code == 404  # pending is not a contact
    assert client.post(f"/api/connect/{a_slug}/accept", headers=a).status_code == 404  # only the target accepts
    with client.websocket_connect("/ws/events", headers=a) as a_ws:
        assert client.post(f"/api/connect/{a_slug}/accept", headers=b).status_code == 200
        assert a_ws.receive_json() == {"type": "contact.accepted", "user": {"slug": b_slug, "name": "Mei"}}
    assert b_slug in _contacts(client, a) and a_slug in _contacts(client, b)
    assert client.get("/api/connect/requests", headers=b).json() == []
    assert _ring(client, a, b_slug).status_code == 200
    assert _ring(client, b, a_slug).status_code == 200
    with session_scope() as s:
        assert s.query(m.Tie).count() == 0  # no fake relationship in the world graph


def test_decline_keeps_them_strangers(client):
    a_slug, a = _user("Arjun")
    b_slug, b = _user("Mei", "zh")
    client.post("/api/connect", json={"handle": _handle(client, b)}, headers=a)
    assert client.post(f"/api/connect/{a_slug}/decline", headers=b).status_code == 200
    assert client.post(f"/api/connect/{a_slug}/accept", headers=b).status_code == 404  # no longer pending
    assert client.get("/api/connect/requests", headers=b).json() == []
    assert _ring(client, a, b_slug).status_code == 404
    assert b_slug not in _contacts(client, a)


def test_mutual_requests_auto_accept(client):
    a_slug, a = _user("Arjun")
    b_slug, b = _user("Mei", "zh")
    ha, hb = _handle(client, a), _handle(client, b)
    assert client.post("/api/connect", json={"handle": hb}, headers=a).json()["status"] == "pending"
    with client.websocket_connect("/ws/events", headers=a) as a_ws:
        r = client.post("/api/connect", json={"handle": ha}, headers=b)
        assert r.json() == {"status": "accepted", "user": {"slug": a_slug, "name": "Arjun"}}
        assert a_ws.receive_json() == {"type": "contact.accepted", "user": {"slug": b_slug, "name": "Mei"}}
    assert _ring(client, b, a_slug).status_code == 200


def test_unknown_handle_self_and_no_token(client):
    _, a = _user("Arjun")
    ha = _handle(client, a)
    r = client.post("/api/connect", json={"handle": "nobody-0000"}, headers=a)
    assert r.status_code == 404 and r.json() == {"detail": "no one with that handle"}
    assert client.post("/api/connect", json={"handle": ha}, headers=a).status_code == 422
    assert client.post("/api/connect", json={"handle": ha}).status_code == 401
    assert client.get("/api/connect/requests").status_code == 401
    assert client.post("/api/connect/p_x_1/accept").status_code == 401
