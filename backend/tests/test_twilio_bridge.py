"""Phase 5: Twilio ConversationRelay bridge. TwiML builder + relay WebSocket protocol (VERIFIED message shapes in docs/DECISIONS.md)."""
import json
import xml.etree.ElementTree as ET

import httpx
import pytest
from fastapi.testclient import TestClient

from app import llm as llm_mod
from app.audio.twilio_bridge import relay_twiml
from app.main import app
from tests.test_call_ws import _drain_until, mock_llm  # noqa: F401


def test_relay_twiml_has_verified_attributes():
    xml = relay_twiml(ws_url="wss://abc.ngrok.app/twilio/relay", role="grandparent", language="ta-IN", welcome="Vanakkam")
    root = ET.fromstring(xml)
    cr = root.find("Connect/ConversationRelay")
    assert cr is not None and cr.get("url") == "wss://abc.ngrok.app/twilio/relay"
    assert cr.get("welcomeGreeting") == "Vanakkam" and cr.get("interruptible") == "any" and cr.get("dtmfDetection") == "true"
    assert cr.get("ttsProvider") == "ElevenLabs" and cr.get("transcriptionProvider") == "Deepgram"
    langs = {l.get("code") for l in cr.findall("Language")}
    assert {"ta-IN", "en-US"} <= langs
    params = {p.get("name"): p.get("value") for p in cr.findall("Parameter")}
    assert params["role"] == "grandparent"


def test_voice_webhook_returns_twiml_and_creates_call(monkeypatch):
    monkeypatch.setenv("PUBLIC_WSS_HOST", "abc.ngrok.app")
    from app.config import get_settings
    get_settings.cache_clear()
    with TestClient(app) as c:
        r = c.post("/twilio/voice", data={"From": "+15550001", "To": "+15550002", "CallSid": "CA1"})
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
