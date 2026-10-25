"""World LiveKit join (ARCHITECTURE 8.7): X-KIN-User body, p<id> identities, metadata parsing. No LiveKit, no CallSession."""
import asyncio
import json
from types import SimpleNamespace

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import models as m
from app.db.session import session_scope
from app.main import app
from app.rtc.agent import participant_from_meta
from app.world.users import create_user, get_space


@pytest.fixture
def client(monkeypatch):
    from app.rtc import agent as agent_mod
    started = []
    monkeypatch.setattr(agent_mod.agents, "ensure", lambda call_id: started.append(call_id))
    with TestClient(app) as c:
        c.started = started
        yield c


def _user(name, lang):
    with session_scope() as s:
        _, p, tok = create_user(s, name, lang)
        return p.id, p.slug, tok


def _claims(token):
    return jwt.decode(token, "secret", algorithms=["HS256"], options={"verify_aud": False})


def test_world_join_creates_call_and_second_user_joins(client):
    arjun_id, arjun_slug, arjun_tok = _user("Arjun", "en")
    mei_id, mei_slug, mei_tok = _user("Mei", "zh")
    a = client.post("/api/rtc/join", json={}, headers={"X-KIN-User": arjun_tok})
    assert a.status_code == 200, a.text
    a = a.json()
    assert (a["identity"], a["person"], a["name"], a["lang"], a["participants"]) == (f"p{arjun_id}", arjun_slug, "Arjun", "en", [])
    claims = _claims(a["token"])
    meta = json.loads(claims["metadata"])
    assert claims["sub"] == f"p{arjun_id}" and claims["video"]["room"] == a["room"] == f"kin-call-{a['call_id']}"
    assert meta == {"person": arjun_slug, "person_id": arjun_id, "lang": "en", "name": "Arjun"}

    b = client.post("/api/rtc/join", json={"call_id": a["call_id"], "invite": a["invite"]},
                    headers={"X-KIN-User": mei_tok}).json()
    assert b["call_id"] == a["call_id"] and _claims(b["token"])["sub"] == f"p{mei_id}" and b["invite"] == a["invite"]
    assert b["participants"] == [{"identity": f"p{arjun_id}", "person": arjun_slug, "name": "Arjun", "lang": "en"}]
    assert client.started == [a["call_id"], a["call_id"]]
    # rejoin keeps one row per person, and a seat already taken needs no invite
    assert client.post("/api/rtc/join", json={"call_id": a["call_id"]}, headers={"X-KIN-User": mei_tok}).status_code == 200
    with session_scope() as s:
        call = s.get(m.Call, a["call_id"])
        assert (call.mode, call.transport, call.participants) == ("world", "livekit", [arjun_id, mei_id])
        rows = s.scalars(select(m.CallParticipant).where(m.CallParticipant.call_id == call.id)).all()
        assert sorted((r.identity, r.lang) for r in rows) == sorted([(f"p{arjun_id}", "en"), (f"p{mei_id}", "zh")])


def test_world_join_rejects_legacy_call_unknown_call_and_missing_token(client):
    _, _, tok = _user("Arjun", "en")
    legacy = client.post("/api/rtc/join", json={"family_id": 1, "role": "grandchild"}).json()
    h = {"X-KIN-User": tok}
    assert client.post("/api/rtc/join", json={"call_id": legacy["call_id"]}, headers=h).status_code == 404
    with session_scope() as s:  # a non-world call in the user's own space: only the mode check rejects it
        c = m.Call(family_id=get_space(s).id, transport="livekit")
        s.add(c)
        s.flush()
        same_space = c.id
    assert client.post("/api/rtc/join", json={"call_id": same_space}, headers=h).status_code == 404
    assert client.post("/api/rtc/join", json={"call_id": 9999}, headers=h).status_code == 404
    assert client.post("/api/rtc/join", json={}).status_code == 401
    assert client.post("/api/rtc/join", json={}, headers={"X-KIN-User": "nope"}).status_code == 401
    assert client.post("/api/rtc/join", json={"family_id": 1, "role": "boss"}).status_code == 422


def test_world_join_needs_the_invite_code_to_take_a_new_seat(client):
    _, _, a_tok = _user("Arjun", "en")
    _, _, m_tok = _user("Mei", "zh")
    priya_id, _, p_tok = _user("Priya", "en")
    a = client.post("/api/rtc/join", json={}, headers={"X-KIN-User": a_tok}).json()
    assert len(a["invite"]) == 16
    joined = client.post("/api/rtc/join", json={"call_id": a["call_id"], "invite": a["invite"]},
                         headers={"X-KIN-User": m_tok})
    assert joined.status_code == 200
    # Priya was not invited: no code, a wrong code, or another call's code all look like a missing call
    other = client.post("/api/rtc/join", json={}, headers={"X-KIN-User": p_tok}).json()
    for invite in (None, "", "0" * 16, other["invite"], "\u00e9"):  # non-ASCII must not reach a str compare_digest
        r = client.post("/api/rtc/join", json={"call_id": a["call_id"], "invite": invite}, headers={"X-KIN-User": p_tok})
        assert r.status_code == 404, invite
    with session_scope() as s:
        seated = s.scalars(select(m.CallParticipant.person_id).where(m.CallParticipant.call_id == a["call_id"])).all()
        assert priya_id not in seated and s.get(m.Call, a["call_id"]).participants == [p for p in seated]


def test_participant_from_meta():
    world = json.dumps({"person": "p_mei_5", "person_id": 5, "lang": "zh", "name": "Mei"})
    assert participant_from_meta("p5", world) == ("p5", "p_mei_5", "zh", 5)
    legacy = json.dumps({"role": "grandparent", "person": "p_kamala"})
    assert participant_from_meta("grandparent-3", legacy) == ("grandparent", "p_kamala", None, None)
    for junk in (None, "", "{", "[]", '"x"', '{"role": "boss", "person": "x"}', '{"person_id": 5, "lang": "zh"}',
                 '{"person": "p", "person_id": "5", "lang": "zh"}', '{"person": "p", "person_id": 5}'):
        assert participant_from_meta("x", junk) is None, junk


def test_join_lists_only_participants_still_present(client):
    from app.rtc.agent import RoomAgent
    a_id, _, a_tok = _user("Arjun", "en")
    _, _, b_tok = _user("Mei", "zh")
    _, _, c_tok = _user("Paatti", "ta")
    a = client.post("/api/rtc/join", json={}, headers={"X-KIN-User": a_tok}).json()
    call_id, invite = a["call_id"], a["invite"]
    client.post("/api/rtc/join", json={"call_id": call_id, "invite": invite}, headers={"X-KIN-User": b_tok})
    RoomAgent._mark_left(SimpleNamespace(call_id=call_id), f"p{a_id}")  # what _leave does for a world leg
    c = client.post("/api/rtc/join", json={"call_id": call_id, "invite": invite}, headers={"X-KIN-User": c_tok}).json()
    assert [x["name"] for x in c["participants"]] == ["Mei"]


def test_join_binds_real_callsession_signature():
    """_join passes these exact arguments; a FakeSession would hide a mismatch (3B owns the signature)."""
    import inspect
    from app.audio.pipeline import CallSession
    sig = inspect.signature(CallSession.join)
    if "person_id" not in sig.parameters:
        pytest.xfail("3B has not landed CallSession.join(..., *, lang, person_id) yet")
    f = lambda *_: None  # noqa: E731
    sig.bind(None, "p5", "p_mei_5", f, f, lang="zh", person_id=5)
    sig.bind(None, "grandparent", "p_kamala", f, f)


class _FakeRoom:
    def __init__(self, log):
        async def publish_track(track, _opts):
            await asyncio.sleep(0)  # let a concurrent caller race the lock
            log.append(("publish", track.name))
            return SimpleNamespace(sid="TR_1")

        async def unpublish_track(sid):
            log.append(("unpublish", sid))

        async def publish_data(*_a, **_kw):
            log.append(("data",))

        self.local_participant = SimpleNamespace(publish_track=publish_track, unpublish_track=unpublish_track,
                                                 publish_data=publish_data)
        self.remote_participants = {}


class _FakeSession:
    def __init__(self, log):
        self.log = log

    async def join(self, *args, **kw):
        self.log.append(("join", args[:2], kw))
        return SimpleNamespace(token="t")

    async def leave(self, key, token=None):
        self.log.append(("leave", key, token))


def _agent(log, monkeypatch):
    from app.rtc.agent import RoomAgent
    ag = RoomAgent(1)
    ag.room, ag.session = _FakeRoom(log), _FakeSession(log)
    monkeypatch.setattr(ag, "_mark_left", lambda identity: log.append(("left", identity)))
    return ag


def _part(identity, meta):
    return SimpleNamespace(identity=identity, track_publications={}, metadata=json.dumps(meta))


WORLD_META = {"person": "p_mei_5", "person_id": 5, "lang": "zh", "name": "Mei"}


def test_agent_world_leg_publishes_once_on_voice_and_keys_by_identity(monkeypatch):
    from app.rtc.agent import FRAME_SAMPLES
    log = []

    async def run():
        ag = _agent(log, monkeypatch)
        p = _part("p5", WORLD_META)
        await ag._join(p)
        assert log == [("join", ("p5", "p_mei_5"), {"lang": "zh", "person_id": 5})]
        leg = ag.legs["p5"]
        assert leg.key == "p5" and not leg.published
        await leg.send_json({"type": "transcript"})
        assert ("publish", "kin-to-p5") not in log  # captions alone never publish the voice track
        frames = []
        leg.source = SimpleNamespace(capture_frame=lambda f: asyncio.sleep(0, frames.append(f)))
        await asyncio.gather(leg.send_json({"type": "audio_start", "utterance_id": 1}),
                             leg.send_bytes(b"\0" * FRAME_SAMPLES * 2), leg.send_bytes(b"\0" * FRAME_SAMPLES * 2))
        assert log.count(("publish", "kin-to-p5")) == 1 and leg.published and len(frames) == 2
        await ag._leave(p)
        assert ("leave", "p5", "t") in log and ("left", "p5") in log
        assert len([e for e in log if e[0] == "unpublish"]) == 1

    asyncio.run(run())


def test_agent_world_leg_without_voice_never_unpublishes(monkeypatch):
    log = []

    async def run():
        ag = _agent(log, monkeypatch)
        p = _part("p5", WORLD_META)
        await ag._join(p)
        await ag._leave(p)
        assert ("leave", "p5", "t") in log and not [e for e in log if e[0] in ("publish", "unpublish")]

    asyncio.run(run())


def test_agent_legacy_leg_keys_by_role_and_publishes_before_join(monkeypatch):
    log = []

    async def run():
        ag = _agent(log, monkeypatch)
        p = _part("grandparent-3", {"role": "grandparent", "person": "p_kamala"})
        await ag._join(p)
        assert log == [("publish", "kin-to-grandparent-3"), ("join", ("grandparent", "p_kamala"), {})]
        assert ag.legs["grandparent-3"].key == "grandparent"
        await ag._leave(p)
        assert ("leave", "grandparent", "t") in log and ("left", "grandparent-3") not in log

    asyncio.run(run())


def test_agent_failed_join_is_logged_not_raised(monkeypatch, caplog):
    log = []

    async def run():
        ag = _agent(log, monkeypatch)

        async def boom(*_a, **_kw):
            raise TypeError("bad signature")

        ag.session.join = boom
        await ag._safe_join(_part("p5", WORLD_META))
        assert "p5" not in ag.legs

    asyncio.run(run())
    assert "KIN join failed for p5" in caplog.text
