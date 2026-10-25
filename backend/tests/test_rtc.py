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
