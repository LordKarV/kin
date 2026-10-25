"""In-app Messages (api/messages.py): the same ingest as a text to KIN's number, for the X-KIN-User. LLM mocked on the
schema name SmsOut, as in test_sms.py."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api import sms as sms_api
from app.db import models as m
from app.db.session import session_scope
from app.main import app
from app.world import sms as sms_mod
from tests.test_sms import _audience, _sensitive_parse
from tests.test_world_api import _reset_clock, befriend, mock_llm, sign_up  # noqa: F401


@pytest.fixture(autouse=True)
def _fresh_rate_limit():
    sms_api._sent.clear()
    yield
    sms_api._sent.clear()


def say(c, who, text):
    return c.post("/api/me/messages", headers=who["h"], json={"text": text})


def test_a_message_is_a_private_self_fact_with_the_sms_ack(mock_llm):
    with TestClient(app) as c:
        arjun = sign_up(c, "Arjun")  # no phone: the caller is the author
        r = say(c, arjun, "  started bouldering!  ")
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["reply"] == "Nice: you started bouldering & <loving> it."
        about_me = c.get("/api/me/facts", headers=arjun["h"]).json()["about_me"]
        assert out["facts"] == about_me  # same FactRow shape as GET /api/me/facts
        assert [(f["text"], f["source_kind"], f["subject"]) for f in out["facts"]] == [("started bouldering", "message", arjun["slug"])]
    fid = out["facts"][0]["id"]
    assert _audience(fid) == {arjun["id"]: "authored"}
    with session_scope() as s:
        f = s.get(m.Fact, fid)
        assert (f.subject_id, f.speaker_id, f.shareable) == (arjun["id"], arjun["id"], False)
        msg = s.scalars(select(m.Message)).one()
        assert (msg.body, msg.status, msg.fact_ids, msg.provider_sid, msg.author_id) == ("", "parsed", [fid], None, arjun["id"])


def test_another_user_never_sees_it(mock_llm):
    with TestClient(app) as c:
        arjun, priya = sign_up(c, "Arjun"), sign_up(c, "Priya")
        befriend(c, arjun, priya)
        assert say(c, arjun, "started bouldering").status_code == 200
        world = c.get("/api/world", headers=priya["h"])
        facts = c.get("/api/me/facts", headers=priya["h"])
        assert world.status_code == facts.status_code == 200
        assert "bouldering" not in world.text and "bouldering" not in facts.text


def test_sensitive_news_keeps_only_the_topic_word(mock_llm, monkeypatch):
    monkeypatch.setattr(sms_mod, "_parse", _sensitive_parse)
    with TestClient(app) as c:
        arjun = sign_up(c, "Arjun")
        out = say(c, arjun, "started seeing a therapist for my anxiety").json()
    assert "therapist" in out["reply"]  # the author's own reply, as over SMS
    assert [f["text"] for f in out["facts"]] == ["health"]
    with session_scope() as s:
        assert (s.scalars(select(m.Message)).one().reply) == sms_mod.FALLBACK


def test_needs_a_user_token(mock_llm):
    with TestClient(app) as c:
        r = c.post("/api/me/messages", json={"text": "started bouldering"})
        assert r.status_code == 401
    with session_scope() as s:
        assert s.scalars(select(m.Message)).all() == []


@pytest.mark.parametrize("text", ["", "   ", "x" * 501])
def test_empty_or_too_long_is_422(mock_llm, text):
    with TestClient(app) as c:
        arjun = sign_up(c, "Arjun")
        assert say(c, arjun, text).status_code == 422
    assert "SmsOut" not in mock_llm.calls
