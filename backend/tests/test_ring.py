"""Ringing (in-app calling): /ws/events channel, POST /api/calls/ring and answer/decline/cancel/missed. Offline:
TestClient websockets, no LiveKit (agents.ensure is stubbed), no LLM."""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api import calls as calls_api
from app.api import events as events_api
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


def _pair(tied=True):
    """Arjun and Mei, friends (a tie) unless tied=False. Returns (arjun, mei) as (person_id, slug, token)."""
    with session_scope() as s:
        a_user, a, a_tok = create_user(s, "Arjun", "en")
        _, b, b_tok = create_user(s, "Mei", "zh")
        if tied:
            s.add(m.Tie(family_id=a.family_id, src_person=a.id, dst_person=b.id, kind="friend"))
        return (a.id, a.slug, a_tok), (b.id, b.slug, b_tok)


def _events(client, tok):
    return client.websocket_connect("/ws/events", headers={"X-KIN-User": tok})


def _ring(client, tok, to, video=True):
    return client.post("/api/calls/ring", json={"to": to, "video": video}, headers={"X-KIN-User": tok})


def test_ring_answer_then_both_join_without_invite(client):
    (a_id, a_slug, a_tok), (b_id, b_slug, b_tok) = _pair()
    with _events(client, a_tok) as a_ws, _events(client, b_tok) as b_ws:
        r = _ring(client, a_tok, b_slug, video=False)
        assert r.status_code == 200, r.text
        call_id = r.json()["call_id"]
        assert r.json()["delivered"] is True
        assert b_ws.receive_json() == {"type": "call.incoming", "call_id": call_id,
                                       "from": {"slug": a_slug, "name": "Arjun"}, "video": False}
        assert client.post(f"/api/calls/{call_id}/answer", headers={"X-KIN-User": a_tok}).status_code == 403  # caller
        assert client.post(f"/api/calls/{call_id}/answer", headers={"X-KIN-User": b_tok}).json() == {"ok": True}
        assert a_ws.receive_json() == {"type": "call.answered", "call_id": call_id}
    assert client.post(f"/api/calls/{call_id}/answer", headers={"X-KIN-User": b_tok}).status_code == 409
    # held seats: both join with only the call id, and nobody shows as in the room before they join
    a = client.post("/api/rtc/join", json={"call_id": call_id}, headers={"X-KIN-User": a_tok})
    assert a.status_code == 200 and a.json()["participants"] == []
    b = client.post("/api/rtc/join", json={"call_id": call_id}, headers={"X-KIN-User": b_tok})
    assert b.status_code == 200 and [p["person"] for p in b.json()["participants"]] == [a_slug]
    with session_scope() as s:
        call = s.get(m.Call, call_id)
        assert (call.mode, call.ended_at, call.participants) == ("world", None, [a_id, b_id])


def test_decline_and_cancel_end_the_call(client):
    (_, _, a_tok), (_, b_slug, b_tok) = _pair()
    with _events(client, a_tok) as a_ws, _events(client, b_tok) as b_ws:
        declined = _ring(client, a_tok, b_slug).json()["call_id"]
        b_ws.receive_json()
        assert client.post(f"/api/calls/{declined}/decline", headers={"X-KIN-User": b_tok}).status_code == 200
        assert a_ws.receive_json() == {"type": "call.declined", "call_id": declined}

        cancelled = _ring(client, a_tok, b_slug).json()["call_id"]
        b_ws.receive_json()
        assert client.post(f"/api/calls/{cancelled}/cancel", headers={"X-KIN-User": b_tok}).status_code == 403
        assert client.post(f"/api/calls/{cancelled}/cancel", headers={"X-KIN-User": a_tok}).status_code == 200
        assert b_ws.receive_json() == {"type": "call.cancelled", "call_id": cancelled}
    with session_scope() as s:
        assert all(s.get(m.Call, cid).ended_at is not None for cid in (declined, cancelled))
    for cid in (declined, cancelled):  # an ended ring cannot be reopened with its held seat
        for tok in (a_tok, b_tok):
            assert client.post("/api/rtc/join", json={"call_id": cid}, headers={"X-KIN-User": tok}).status_code == 404


def test_no_answer_is_missed_for_both(client, monkeypatch):
    monkeypatch.setattr(calls_api, "RING_TIMEOUT_S", 0.2)
    (_, _, a_tok), (_, b_slug, b_tok) = _pair()
    with _events(client, a_tok) as a_ws, _events(client, b_tok) as b_ws:
        call_id = _ring(client, a_tok, b_slug).json()["call_id"]
        assert b_ws.receive_json()["type"] == "call.incoming"
        assert b_ws.receive_json() == {"type": "call.missed", "call_id": call_id}
        assert a_ws.receive_json() == {"type": "call.missed", "call_id": call_id}
    # 403, not 409: an ended ring takes its held seats with it
    assert client.post(f"/api/calls/{call_id}/answer", headers={"X-KIN-User": b_tok}).status_code == 403
    with session_scope() as s:
        assert s.get(m.Call, call_id).ended_at is not None


def test_ring_rules_and_late_connect_replays_the_ring(client):
    (a_id, a_slug, a_tok), (b_id, b_slug, b_tok) = _pair(tied=False)
    assert _ring(client, a_tok, b_slug).status_code == 404  # not a contact
    assert _ring(client, a_tok, "p_nobody_99").status_code == 404
    assert client.post("/api/calls/ring", json={"to": b_slug}).status_code == 401
    with session_scope() as s:  # Mei calls Arjun her friend: a tie either way makes them contacts
        s.add(m.Tie(family_id=s.get(m.Person, a_id).family_id, src_person=b_id, dst_person=a_id, kind="friend"))
    r = _ring(client, a_tok, b_slug)  # Mei's app is closed: nothing delivered, but the ring waits
    assert r.json()["delivered"] is False
    with _events(client, b_tok) as b_ws:
        assert b_ws.receive_json() == {"type": "call.incoming", "call_id": r.json()["call_id"],
                                       "from": {"slug": a_slug, "name": "Arjun"}, "video": True}


def test_events_socket_rejects_bad_token(client):
    with client.websocket_connect("/ws/events?token=nope") as ws:
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
    assert e.value.code == 4401


def test_a_socket_that_was_away_hears_how_the_ring_ended(client):
    (_, _, a_tok), (_, b_slug, b_tok) = _pair()
    answered = _ring(client, a_tok, b_slug).json()["call_id"]  # neither app is open
    assert client.post(f"/api/calls/{answered}/answer", headers={"X-KIN-User": b_tok}).status_code == 200
    with _events(client, a_tok) as a_ws:  # the caller comes back and still joins
        assert a_ws.receive_json() == {"type": "call.answered", "call_id": answered}
    cancelled = _ring(client, a_tok, b_slug).json()["call_id"]
    with _events(client, b_tok) as b_ws:
        assert b_ws.receive_json()["call_id"] == cancelled
    assert client.post(f"/api/calls/{cancelled}/cancel", headers={"X-KIN-User": a_tok}).status_code == 200
    with _events(client, b_tok) as b_ws:  # the stale "Arjun is calling" cover clears; the ring is not replayed
        assert b_ws.receive_json() == {"type": "call.cancelled", "call_id": cancelled}


def test_locked_server_needs_the_key_by_header_or_query(client, monkeypatch):
    monkeypatch.setenv("KIN_API_KEY", "s3cret")
    from app.config import get_settings
    get_settings.cache_clear()
    (_, _, a_tok), (_, b_slug, b_tok) = _pair()
    key = {"X-KIN-Key": "s3cret"}
    call_id = client.post("/api/calls/ring", json={"to": b_slug}, headers={"X-KIN-User": a_tok, **key}).json()["call_id"]
    with client.websocket_connect("/ws/events", headers={"X-KIN-User": b_tok}) as ws:  # good token, no key
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
    assert e.value.code == 4401
    with client.websocket_connect("/ws/events", headers={"X-KIN-User": b_tok, "X-KIN-Key": "wrong"}) as ws:
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
    assert e.value.code == 4401
    with client.websocket_connect("/ws/events", headers={"X-KIN-User": b_tok, **key}) as ws:
        assert ws.receive_json()["call_id"] == call_id
    with client.websocket_connect(f"/ws/events?token={b_tok}&key=s3cret") as ws:
        assert ws.receive_json()["call_id"] == call_id


def test_deleted_person_leaves_no_ring_or_socket(client):
    (a_id, _, a_tok), (b_id, b_slug, b_tok) = _pair()
    with _events(client, a_tok) as a_ws, _events(client, b_tok) as b_ws:
        call_id = _ring(client, a_tok, b_slug).json()["call_id"]
        b_ws.receive_json()
        client.portal.call(calls_api.drop_person, a_id)
        assert b_ws.receive_json() == {"type": "call.cancelled", "call_id": call_id}
        with pytest.raises(WebSocketDisconnect) as e:
            a_ws.receive_json()
        assert e.value.code == 4401
    assert a_id not in events_api._sockets and calls_api.pending_rings(a_id) == []
    assert calls_api._rings == {} and calls_api.pending_rings(b_id) == [{"type": "call.cancelled", "call_id": call_id}]
