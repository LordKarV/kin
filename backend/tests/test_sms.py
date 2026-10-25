"""SMS ingest and the Twilio webhook (docs/ARCHITECTURE.md section 7). Mock LLM keyed on schema name SmsOut."""
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api import sms as sms_api
from app.db import models as m
from app.db.session import session_scope
from app.main import app
from app.world import sms as sms_mod
from tests.test_world_api import _reset_clock, befriend, mock_llm, plant_lin, sign_up  # noqa: F401

ARJUN = "+15125550101"


@pytest.fixture(autouse=True)
def _fresh_rate_limit():
    sms_api._sent.clear()
    yield
    sms_api._sent.clear()


def post(c, body, sid="SM1", frm=ARJUN, **kw):
    return c.post("/twilio/sms", data={"From": frm, "To": "+15550000000", "Body": body, "MessageSid": sid}, **kw)


def _audience(fid):
    with session_scope() as s:
        return {a.person_id: a.via for a in s.scalars(select(m.FactAudience).where(m.FactAudience.fact_id == fid))}


def test_valid_post_returns_twiml_ack_and_a_private_fact(mock_llm):
    with TestClient(app) as c:
        arjun = sign_up(c, "Arjun", phone=ARJUN)
        r = post(c, "started bouldering!")
        assert r.status_code == 200 and r.headers["content-type"].startswith("application/xml")
        assert r.text.endswith("<Response><Message>Nice: you started bouldering &amp; &lt;loving&gt; it.</Message></Response>")
    with session_scope() as s:
        f = s.scalars(select(m.Fact)).one()
        assert (f.subject_id, f.speaker_id, f.source_kind, f.shareable, f.text) == (arjun["id"], arjun["id"], "message", False, "started bouldering")
        msg = s.scalars(select(m.Message)).one()
        assert msg.body == "" and msg.status == "parsed" and msg.fact_ids == [f.id] and msg.provider_sid == "SM1"
    assert _audience(f.id) == {arjun["id"]: "authored"}


def test_told_priya_adds_priya_via_told(mock_llm):
    with TestClient(app) as c:
        arjun, priya = sign_up(c, "Arjun", phone=ARJUN), sign_up(c, "Priya")
        befriend(c, arjun, priya)
        post(c, "started bouldering, told Priya")
    with session_scope() as s:
        f = s.scalars(select(m.Fact).where(m.Fact.source_kind == "message")).one()
    assert _audience(f.id) == {arjun["id"]: "authored", priya["id"]: "told"}


def test_bad_signature_is_403_when_auth_token_set(mock_llm, monkeypatch):
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok")
    from app.config import get_settings
    get_settings.cache_clear()
    with TestClient(app) as c:
        sign_up(c, "Arjun", phone=ARJUN)
        assert post(c, "started bouldering", headers={"X-Twilio-Signature": "bogus"}).status_code == 403
    with session_scope() as s:
        assert s.scalars(select(m.Message)).all() == []


def test_unknown_number_gets_the_link_reply_and_stores_nothing(mock_llm):
    with TestClient(app) as c:
        sign_up(c, "Arjun", phone=ARJUN)
        r = post(c, "started bouldering", frm="+15559999999")
        assert sms_mod.UNKNOWN_REPLY in r.text
    with session_scope() as s:
        assert s.scalars(select(m.Message)).all() == [] and s.scalars(select(m.Fact)).all() == []
    assert "SmsOut" not in mock_llm.calls


def test_duplicate_message_sid_returns_the_same_reply_once(mock_llm):
    with TestClient(app) as c:
        sign_up(c, "Arjun", phone=ARJUN)
        first, again = post(c, "started bouldering"), post(c, "started bouldering")
        assert first.text == again.text
    with session_scope() as s:
        assert len(s.scalars(select(m.Message)).all()) == 1 and len(s.scalars(select(m.Fact)).all()) == 1
    assert mock_llm.calls.count("SmsOut") == 1


def test_rate_limit_replies_slow_down(mock_llm, monkeypatch):
    monkeypatch.setattr(sms_api, "RATE_LIMIT", 2)
    with TestClient(app) as c:
        sign_up(c, "Arjun", phone=ARJUN)
        replies = [post(c, "hi", sid=f"SM{i}").text for i in range(3)]
    assert sms_mod.SLOW_REPLY not in replies[1] and sms_mod.SLOW_REPLY in replies[2]


def test_dev_sms_gives_the_same_result(mock_llm):
    with TestClient(app) as c:
        arjun = sign_up(c, "Arjun", phone=ARJUN)
        r = c.post("/api/dev/sms", json={"from": "512-555-0101", "body": "started bouldering"}).json()
        assert r["reply"] == "Nice: you started bouldering & <loving> it." and r["message_id"]
        assert [f["text"] for f in r["facts"]] == ["started bouldering"]
        assert _audience(r["facts"][0]["id"]) == {arjun["id"]: "authored"}
        assert c.post("/api/dev/sms", json={"from": "+15550000001", "body": "x"}).json()["reply"] == sms_mod.UNKNOWN_REPLY
    with session_scope() as s:
        assert s.get(m.Message, r["message_id"]).body == ""


def test_slow_parse_replies_got_it_and_finishes_in_background(mock_llm, monkeypatch):
    real = sms_mod._parse
    monkeypatch.setattr(sms_mod, "_parse", lambda ctx: (time.sleep(0.3), real(ctx))[1])
    monkeypatch.setattr(sms_mod, "BUDGET_S", 0.05)
    monkeypatch.setattr(sms_mod.ingest, "__defaults__", (None, 0.05))
    with TestClient(app) as c:
        sign_up(c, "Arjun", phone=ARJUN)
        assert sms_mod.FALLBACK in post(c, "started bouldering").text
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with session_scope() as s:
            msg = s.scalars(select(m.Message)).one()
            if msg.status == "parsed":
                break
        time.sleep(0.05)
    assert msg.status == "parsed" and msg.body == "" and msg.reply == sms_mod.FALLBACK and len(msg.fact_ids) == 1


def _facts():
    with session_scope() as s:
        return {f.id: f.text for f in s.scalars(select(m.Fact).where(m.Fact.source_kind == "message"))}


def _wait_status(want, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with session_scope() as s:
            msg = s.scalars(select(m.Message)).one()
            if msg.status == want:
                return msg
        time.sleep(0.05)
    return msg


def test_validator_drops_news_about_others_and_unknown_predicates(mock_llm):
    with TestClient(app) as c:
        arjun = sign_up(c, "Arjun", phone=ARJUN)
        for name in ("Priya", "Will"):
            befriend(c, arjun, sign_up(c, name))
        post(c, "news")
    assert list(_facts().values()) == ["will start a new job"]


def test_told_needs_the_whole_name(mock_llm):
    with TestClient(app) as c:
        arjun, priya = sign_up(c, "Arjun", phone=ARJUN), sign_up(c, "Priya")
        befriend(c, arjun, priya)
        post(c, "started bouldering, told Priya's mom")
    assert _audience(next(iter(_facts()))) == {arjun["id"]: "authored"}


def test_told_in_another_script_resolves_a_visible_person(mock_llm):
    with TestClient(app) as c:
        mei, arjun = sign_up(c, "Mei", "zh"), sign_up(c, "Arjun", phone=ARJUN)
        lin = plant_lin(c, mei, [arjun])["entities"][0]
        post(c, "started bouldering, told 林")
    assert _audience(next(iter(_facts()))) == {arjun["id"]: "authored", lin["id"]: "told"}


def test_told_a_hidden_person_adds_nobody(mock_llm):
    with TestClient(app) as c:
        mei, arjun = sign_up(c, "Mei", "zh"), sign_up(c, "Arjun", phone=ARJUN)
        plant_lin(c, mei, [])  # Arjun never heard of Lin
        post(c, "started bouldering, told 林")
    assert _audience(next(iter(_facts()))) == {arjun["id"]: "authored"}


def test_ambiguous_told_name_adds_nobody():
    ctx = sms_mod._Ctx(1, 9, "en", "", "", sms_mod.AliasIndex([("Sam", "person", 1), ("Sam", "person", 2)]), None)
    assert sms_mod._resolve_told(ctx, "Sam") is None
    one = sms_mod._Ctx(1, 9, "en", "", "", sms_mod.AliasIndex([("Sam", "person", 1)]), None)
    assert sms_mod._resolve_told(one, "Sam") == 1 and sms_mod._resolve_told(one, "Sam's dad") is None


def test_parse_failing_twice_marks_failed_and_clears_body(mock_llm):
    with TestClient(app) as c:
        sign_up(c, "Arjun", phone=ARJUN)
        assert sms_mod.FALLBACK in post(c, "explode " + "x" * 2000).text
    msg = _wait_status("failed")
    assert msg.status == "failed" and msg.body == "" and msg.reply == sms_mod.FALLBACK


def test_store_error_marks_failed_and_clears_body(mock_llm, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("apply broke")
    monkeypatch.setattr(sms_mod, "apply_update", boom)
    with TestClient(app) as c:
        sign_up(c, "Arjun", phone=ARJUN)
        r = post(c, "started bouldering")
        assert r.status_code == 200 and sms_mod.FALLBACK in r.text
    msg = _wait_status("failed")
    assert msg.status == "failed" and msg.body == "" and _facts() == {}


def test_body_is_truncated_to_1600(mock_llm, monkeypatch):
    monkeypatch.setattr(sms_mod, "_store", lambda s, ctx, msg, out, now: [])  # keep the body to measure it
    with TestClient(app) as c:
        sign_up(c, "Arjun", phone=ARJUN)
        post(c, "y" * 5000)
    with session_scope() as s:
        assert len(s.scalars(select(m.Message)).one().body) == sms_mod.MAX_BODY


def _sensitive_parse(ctx):
    fact = {"predicate": "started", "text_en": "started seeing a therapist for anxiety", "keys": [["therapist"]],
            "sensitive_kind": "health", "storyline": None, "told": []}
    return sms_mod.SmsOut.model_validate({"facts": [fact], "ack": "Thanks for sharing that you started seeing a therapist."})


def test_sensitive_sms_keeps_only_the_topic_word_anywhere(mock_llm, monkeypatch):
    monkeypatch.setattr(sms_mod, "_parse", _sensitive_parse)
    with TestClient(app) as c:
        sign_up(c, "Arjun", phone=ARJUN)
        assert "therapist" in post(c, "started seeing a therapist for my anxiety").text  # the author's own reply
    with session_scope() as s:
        assert [f.text for f in s.scalars(select(m.Fact))] == ["health"]
        msg = s.scalars(select(m.Message)).one()
        assert (msg.body, msg.reply) == ("", sms_mod.FALLBACK)


def test_deleting_an_sms_fact_clears_the_stored_ack(mock_llm):
    with TestClient(app) as c:
        arjun = sign_up(c, "Arjun", phone=ARJUN)
        post(c, "started bouldering!")
        fid = next(iter(_facts()))
        assert c.delete(f"/api/me/facts/{fid}", headers=arjun["h"]).status_code == 200
    with session_scope() as s:
        msg = s.scalars(select(m.Message)).one()
        assert (msg.fact_ids, msg.reply) == ([], "")


def test_dropped_sms_fact_is_logged_without_its_text(mock_llm, caplog):
    with TestClient(app) as c:
        arjun = sign_up(c, "Arjun", phone=ARJUN)
        befriend(c, arjun, sign_up(c, "Priya"))
        post(c, "news")
    assert "sms fact dropped" in caplog.text and "internship" not in caplog.text


@pytest.fixture
def no_dev(monkeypatch):
    monkeypatch.setenv("DEV_ENDPOINTS", "0")
    from app.config import get_settings
    get_settings.cache_clear()


def test_a_typed_number_links_nothing_until_its_code_is_texted_from_it(mock_llm, no_dev):
    with TestClient(app) as c:
        eve = sign_up(c, "Eve", phone=ARJUN)  # Eve types Arjun's number
        assert c.get("/api/me", headers=eve["h"]).json()["phone"] is None
        assert c.patch("/api/me", headers=eve["h"], json={"phone": ARJUN}).status_code == 403
        arjun = sign_up(c, "Arjun", phone=ARJUN)  # no 409: the number is not Eve's
        code = c.get("/api/me/phone-code", headers=arjun["h"]).json()
        assert code["text"] == f"KIN {code['code']}" and code["linked"] is False
        assert sms_mod.UNKNOWN_REPLY in post(c, "started bouldering", sid="SM0").text
        eve_code = c.get("/api/me/phone-code", headers=eve["h"]).json()["code"]
        assert eve_code != code["code"]
        assert sms_mod.UNKNOWN_REPLY in post(c, "KIN 000000", sid="SM1").text  # a wrong code links nothing
        assert sms_mod.LINKED_REPLY in post(c, f"kin {code['code'].upper()}", sid="SM2").text
        assert c.get("/api/me", headers=arjun["h"]).json()["phone"] == ARJUN
        assert c.get("/api/me/phone-code", headers=arjun["h"]).json()["linked"] is True
        post(c, "started bouldering", sid="SM3")
        assert c.patch("/api/me", headers=arjun["h"], json={"phone": ""}).json()["phone"] is None  # unlinking is fine
    with session_scope() as s:
        assert [(f.subject_id, f.text) for f in s.scalars(select(m.Fact))] == [(arjun["id"], "started bouldering")]
        assert len(s.scalars(select(m.Message)).all()) == 1  # link texts store nothing
    assert eve["id"] != arjun["id"]


def test_link_attempts_are_rate_limited_per_number(mock_llm, no_dev, monkeypatch):
    monkeypatch.setattr(sms_api, "RATE_LIMIT", 2)
    with TestClient(app) as c:
        arjun = sign_up(c, "Arjun")
        code = c.get("/api/me/phone-code", headers=arjun["h"]).json()["code"]
        replies = [post(c, f"KIN {x}", sid=f"SM{i}").text for i, x in enumerate(("000000", "111111", code))]
    assert sms_mod.SLOW_REPLY in replies[2]
    with session_scope() as s:
        assert s.scalars(select(m.User).where(m.User.person_id == arjun["id"])).one().phone is None


def test_link_text_sent_again_after_linking_gets_linked_and_stores_nothing(mock_llm, no_dev):
    with TestClient(app) as c:
        arjun = sign_up(c, "Arjun")
        code = c.get("/api/me/phone-code", headers=arjun["h"]).json()["code"]
        replies = [post(c, f"KIN {code}", sid="SM9").text for _ in range(2)]  # a Twilio retry of the link text
        again = post(c, f"KIN {code}", sid="SM10").text  # or the code sent a second time
    assert all(sms_mod.LINKED_REPLY in r for r in replies + [again])
    assert "SmsOut" not in mock_llm.calls
    with session_scope() as s:
        assert s.scalars(select(m.Message)).all() == []
