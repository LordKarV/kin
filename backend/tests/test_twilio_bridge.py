"""Phase 5: Twilio ConversationRelay bridge. TwiML builder + relay WebSocket protocol (VERIFIED message shapes in docs/DECISIONS.md)."""
import json
import xml.etree.ElementTree as ET

import httpx
import pytest
from fastapi.testclient import TestClient

from app import llm as llm_mod
from app.audio.twilio_bridge import relay_twiml
from app.main import app
from tests.test_auth import offline_llm  # noqa: F401
from tests.test_call_ws import _drain_until, mock_llm  # noqa: F401


def test_relay_twiml_has_verified_attributes():
    xml = relay_twiml(ws_url="wss://abc.ngrok.app/twilio/relay", role="grandparent", language="ta-IN", welcome="Vanakkam")
    root = ET.fromstring(xml)
    cr = root.find("Connect/ConversationRelay")
    assert cr is not None and cr.get("url") == "wss://abc.ngrok.app/twilio/relay"
    assert cr.get("welcomeGreeting") == "Vanakkam" and cr.get("interruptible") == "any" and cr.get("dtmfDetection") == "true"
    assert cr.get("ttsProvider") == "ElevenLabs" and cr.get("transcriptionProvider") is None  # per-language below
    langs = {l.get("code"): l for l in cr.findall("Language")}
    assert {"ta-IN", "en-US"} <= set(langs)
    # VERIFIED: Twilio lists ta-IN with Google transcription + ElevenLabs TTS; Deepgram nova-3 only on the English leg
    assert langs["ta-IN"].get("transcriptionProvider") is None and langs["ta-IN"].get("ttsProvider") == "ElevenLabs"
    assert langs["en-US"].get("transcriptionProvider") == "Deepgram" and langs["en-US"].get("speechModel") == "nova-3-general"
    params = {p.get("name"): p.get("value") for p in cr.findall("Parameter")}
    assert params["role"] == "grandparent"


def _signed(form: dict, path: str = "/twilio/voice") -> dict:
    from twilio.request_validator import RequestValidator
    sig = RequestValidator("tok").compute_signature(f"https://abc.ngrok.app{path}", form)
    return {"X-Twilio-Signature": sig, "X-Forwarded-Proto": "https", "Host": "abc.ngrok.app"}


def _exposed(monkeypatch, token: str | None = "tok"):
    monkeypatch.setenv("PUBLIC_WSS_HOST", "abc.ngrok.app"); monkeypatch.setenv("KIN_API_KEY", "real-key")
    if token:
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", token)
    from app.config import get_settings
    get_settings.cache_clear()


def test_voice_webhook_returns_twiml_and_creates_call(monkeypatch):
    _exposed(monkeypatch)
    form = {"From": "+15550001", "To": "+15550002", "CallSid": "CA1"}
    with TestClient(app) as c:
        r = c.post("/twilio/voice", data=form, headers=_signed(form))
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/xml")
    assert "wss://abc.ngrok.app/twilio/relay?call_id=" in r.text and 'name="role"' in r.text


def test_phone_leg_bridges_to_laptop_peer_both_directions(mock_llm):
    with TestClient(app) as c:
        cid = c.post("/api/calls", json={"family_id": 1, "transport": "twilio"}).json()["id"]
        with c.websocket_connect(f"/twilio/relay?call_id={cid}&role=grandparent") as phone, \
             c.websocket_connect(f"/ws/call/{cid}?role=grandchild&person=p_arjun") as gc:
            phone.send_json({"type": "setup", "sessionId": "VX1", "callSid": "CA1", "from": "+15550001", "to": "+15550002", "customParameters": {"role": "grandparent"}})
            assert gc.receive_json()["type"] == "joined"
            # grandparent speaks on the phone → laptop gets the grounded transcript (+ audio)
            phone.send_json({"type": "prompt", "voicePrompt": "உன் மாமா நேத்து போன் பண்ணான்.", "lang": "ta-IN", "last": True})
            tr, _ = _drain_until(gc, "transcript")
            assert tr["speaker"] == "p_kamala" and tr["grounded_spans"][0]["node_id"] == "p_ravi_mama"
            # grandchild types English → phone leg receives a ConversationRelay text message in Tamil
            gc.send_json({"type": "text", "text": "I will call you on Sunday, Paatti."})
            for _ in range(10):
                msg = phone.receive_json()
                if msg.get("type") == "text":
                    break
            assert msg["type"] == "text" and msg["last"] is True and msg["lang"] == "ta-IN" and msg["token"]
            # partial prompts are ignored (no transcript)
            phone.send_json({"type": "prompt", "voicePrompt": "ரவி", "lang": "ta-IN", "last": False})
            phone.send_json({"type": "interrupt", "utteranceUntilInterrupt": "x", "durationUntilInterruptMs": 100})


def test_voice_webhook_rejects_bad_twilio_signature(monkeypatch):
    monkeypatch.setenv("PUBLIC_WSS_HOST", "abc.ngrok.app"); monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok"); monkeypatch.setenv("KIN_API_KEY", "real-key")
    from app.config import get_settings
    get_settings.cache_clear()
    with TestClient(app) as c:
        bad = c.post("/twilio/voice", data={"From": "+1", "CallSid": "CA1"}, headers={"X-Twilio-Signature": "nope"})
        assert bad.status_code == 403
        from twilio.request_validator import RequestValidator
        url = "https://abc.ngrok.app/twilio/voice"
        sig = RequestValidator("tok").compute_signature(url, {"From": "+1", "CallSid": "CA1"})
        ok = c.post("/twilio/voice", data={"From": "+1", "CallSid": "CA1"}, headers={"X-Twilio-Signature": sig, "X-Forwarded-Proto": "https", "Host": "abc.ngrok.app"})
        assert ok.status_code == 200


def test_locked_server_without_auth_token_rejects_unsigned_webhooks(monkeypatch):
    _exposed(monkeypatch, token=None)
    with TestClient(app) as c:
        assert c.post("/twilio/voice", data={"From": "+15550001", "CallSid": "CA1"}).status_code == 403
        assert c.post("/twilio/sms", data={"From": "+15550001", "Body": "hi", "MessageSid": "SM1"}).status_code == 403


def test_voice_webhook_never_opens_a_legacy_call_in_the_space(monkeypatch, offline_llm):
    _exposed(monkeypatch)
    monkeypatch.setenv("SEED_DEMO_FAMILY", "0")
    from app.config import get_settings
    get_settings.cache_clear()
    form = {"From": "+15550001", "CallSid": "CA1"}
    with TestClient(app) as c:
        assert c.post("/api/users", json={"name": "Mei", "lang": "zh"}, headers={"X-KIN-Key": "real-key"}).status_code == 200
        assert c.post("/twilio/voice", data=form, headers=_signed(form)).status_code == 404
    from app.db import models as m
    from app.db.session import session_scope
    with session_scope() as s:
        assert s.query(m.Call).count() == 0


def test_relay_socket_refuses_world_and_unknown_calls():
    from starlette.websockets import WebSocketDisconnect
    from app.db import models as m
    from app.db.session import session_scope
    from app.world.users import get_space
    with TestClient(app) as c:
        with session_scope() as s:
            call = m.Call(family_id=get_space(s, "zh").id, transport="livekit", mode="world")
            s.add(call); s.flush(); wid = call.id
            old = m.Call(family_id=get_space(s, "zh").id, transport="twilio")  # legacy mode, made in the space pre-guard
            s.add(old); s.flush(); lid = old.id
        assert c.get(f"/api/calls/{lid}/utterances").status_code == 404
        for cid in (wid, lid, wid + 99):
            with pytest.raises(WebSocketDisconnect) as e:
                with c.websocket_connect(f"/twilio/relay?call_id={cid}&role=grandparent") as ws:
                    ws.receive_json()
            assert e.value.code == 4404
