"""KIN call app (LiveKit): join mints a room token that says who this person is, and starts the KIN agent."""
import jwt
from fastapi.testclient import TestClient

from app.main import app


def test_grandchild_starts_a_call_grandparent_joins_it(monkeypatch):
    from app.rtc import agent as agent_mod
    started = []
    monkeypatch.setattr(agent_mod.agents, "ensure", lambda call_id: started.append(call_id))
    with TestClient(app) as c:
        a = c.post("/api/rtc/join", json={"family_id": 1, "role": "grandchild"}).json()
        b = c.post("/api/rtc/join", json={"family_id": 1, "role": "grandparent", "call_id": a["call_id"]}).json()
    assert a["room"] == b["room"] == f"kin-call-{a['call_id']}" and started == [a["call_id"], a["call_id"]]
    assert (a["person"], b["person"]) == ("p_arjun", "p_kamala")
    claims = jwt.decode(b["token"], "secret", algorithms=["HS256"], options={"verify_aud": False})
    assert claims["sub"] == f"grandparent-{a['call_id']}" and claims["video"]["room"] == b["room"] and claims["video"]["roomJoin"]
    assert '"role": "grandparent"' in claims["metadata"] and '"person": "p_kamala"' in claims["metadata"]


def test_join_rejects_unknown_family_and_foreign_call(monkeypatch):
    from app.rtc import agent as agent_mod
    monkeypatch.setattr(agent_mod.agents, "ensure", lambda call_id: None)
    with TestClient(app) as c:
        assert c.post("/api/rtc/join", json={"family_id": 999, "role": "grandchild"}).status_code == 404
        assert c.post("/api/rtc/join", json={"family_id": 1, "role": "grandparent", "call_id": 999}).status_code == 404


def test_legacy_body_never_reaches_the_world_space(monkeypatch):
    """The legacy body has no user: pointed at the world space (or a world call in it) it must mint nothing."""
    from sqlalchemy import select

    from app.db import models as m
    from app.db.session import session_scope
    from app.rtc import agent as agent_mod
    from app.world.users import create_user, get_space
    monkeypatch.setattr(agent_mod.agents, "ensure", lambda call_id: None)
    with TestClient(app) as c:
        with session_scope() as s:
            _, _, tok = create_user(s, "Arjun", "en")
        world = c.post("/api/rtc/join", json={}, headers={"X-KIN-User": tok}).json()
        with session_scope() as s:
            space = get_space(s).id
            calls_before = s.scalars(select(m.Call.id)).all()
        for body in ({"family_id": space, "role": "grandchild"},
                     {"family_id": space, "role": "grandchild", "call_id": world["call_id"]},
                     {"family_id": space, "role": "grandparent", "call_id": world["call_id"]}):
            r = c.post("/api/rtc/join", json=body)
            assert r.status_code == 404 and "token" not in r.json(), body
        with session_scope() as s:
            assert s.scalars(select(m.Call.id)).all() == calls_before  # no legacy call was created in the space


def test_world_join_matches_its_contract(monkeypatch):
    """docs/ARCHITECTURE.md 9.2: the world join body and reply are exactly RtcJoinWorldIn / JoinWorldOut."""
    from app.api.rtc import WorldJoinIn
    from app.rtc import agent as agent_mod
    from app.db.session import session_scope
    from app.world import contracts as c
    from app.world.users import create_user
    monkeypatch.setattr(agent_mod.agents, "ensure", lambda call_id: None)
    assert WorldJoinIn.model_fields.keys() == c.RtcJoinWorldIn.model_fields.keys()
    with TestClient(app) as cl:
        with session_scope() as s:
            _, _, a = create_user(s, "Arjun", "en")
            _, _, b = create_user(s, "Mei", "zh")
        first = cl.post("/api/rtc/join", json={}, headers={"X-KIN-User": a}).json()
        assert first.keys() == c.JoinWorldOut.model_fields.keys()
        second = cl.post("/api/rtc/join", json=c.RtcJoinWorldIn(call_id=first["call_id"], invite=first["invite"]).model_dump(),
                         headers={"X-KIN-User": b})
        assert second.status_code == 200 and c.JoinWorldOut.model_validate(second.json()).invite == first["invite"]
