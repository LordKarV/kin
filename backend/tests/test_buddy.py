"""Hey-Buddy-style merged call: KIN is the third leg, hears both people on one Twilio Media Stream, speaks into the call."""
import asyncio
import base64
import json

from fastapi.testclient import TestClient

from app.audio.buddy import BuddyLine
from app.audio.pipeline import CallSession
from app.audio.tts import MockTTS
from app.main import app
from app.mt.translate import Translator
from tests.graph_fixtures import graph  # noqa: F401
from tests.test_call_ws import mock_llm  # noqa: F401


def _session(graph, mock_llm):
    from app.db import models as m
    from app.db.session import session_scope
    with session_scope() as s:
        c = m.Call(family_id=graph.family_id, transport="phone-merge"); s.add(c); s.flush(); cid = c.id
    return CallSession(call_id=cid, family_id=graph.family_id, translator=Translator(graph, mock_llm), tts=MockTTS())


def test_direction_decides_speaker_and_kin_speaks_into_the_call(graph, mock_llm):
    async def run():
        cs = _session(graph, mock_llm)
        spoken, seen = [], []
        cs.add_watcher(lambda m: _append(seen, m))
        line = BuddyLine(cs, send_audio=lambda b: _append(spoken, b), grandparent="p_kamala", learner="p_arjun")
        await line.attach()
        assert cs.sides["grandparent"].asr is None and cs.sides["grandchild"].asr is None  # one shared ASR, not one per side

        await line.on_final("உன் மாமா நேத்து போன் பண்ணான்.")
        t1 = next(m for m in seen if m["type"] == "transcript")
        assert (t1["role"], t1["listener"], t1["target_lang"]) == ("grandparent", "p_arjun", "en")
        assert spoken and all(len(b) > 0 for b in spoken)  # mu-law frames went back into the call

        await line.on_final("Tell her I passed my exams.")
        t2 = [m for m in seen if m["type"] == "transcript"][-1]
        assert (t2["role"], t2["target_lang"]) == ("grandchild", graph.heritage_lang)
    asyncio.run(run())


async def _append(xs, x):
    xs.append(x)


def test_twiml_connects_a_bidirectional_stream_without_query_string(monkeypatch):
    monkeypatch.setenv("PUBLIC_WSS_HOST", "kin.example.com")
    monkeypatch.setenv("KIN_API_KEY", "real-key")
    from app import config
    config.get_settings.cache_clear()
    with TestClient(app) as c:
        r = c.post("/twilio/buddy", data={"CallSid": "CA1", "From": "+15550001111"})
    assert r.status_code == 200
    assert '<Connect><Stream url="wss://kin.example.com/twilio/buddy/stream/' in r.text
    assert "?" not in r.text.split('url="')[1].split('"')[0]  # Twilio rejects query strings on stream urls


def test_stream_websocket_greets_and_accepts_media(mock_llm):
    with TestClient(app) as c:
        cid = c.post("/api/calls", json={"transport": "phone-merge"}).json()["id"]
        with c.websocket_connect(f"/twilio/buddy/stream/{cid}") as ws:
            ws.send_text(json.dumps({"event": "connected", "protocol": "Call", "version": "1.0.0"}))
            ws.send_text(json.dumps({"event": "start", "streamSid": "MZ1", "start": {"streamSid": "MZ1", "callSid": "CA1"}}))
            silence = base64.b64encode(b"\xff" * 160).decode()
            ws.send_text(json.dumps({"event": "media", "streamSid": "MZ1", "media": {"track": "inbound", "payload": silence}}))
            out = json.loads(ws.receive_text())  # the greeting, spoken into the call
            assert out["event"] == "media" and out["streamSid"] == "MZ1" and base64.b64decode(out["media"]["payload"])
            ws.send_text(json.dumps({"event": "stop", "streamSid": "MZ1"}))


def test_live_call_lookup_and_watch_socket(mock_llm):
    with TestClient(app) as c:
        assert c.get("/api/phone/live").json() == {"call_id": None}
        cid = c.post("/api/calls", json={"transport": "phone-merge"}).json()["id"]
        with c.websocket_connect(f"/twilio/buddy/stream/{cid}") as stream:
            stream.send_text(json.dumps({"event": "start", "streamSid": "MZ2", "start": {"streamSid": "MZ2"}}))
            json.loads(stream.receive_text())  # greeting audio
            assert c.get("/api/phone/live").json() == {"call_id": cid}
            with c.websocket_connect(f"/ws/watch/{cid}") as watch:
                assert json.loads(watch.receive_text())["type"] == "watching"
        assert c.get("/phone").status_code == 200


def test_asr_start_is_retried_so_a_slow_handshake_does_not_drop_the_call(monkeypatch):
    from app.api import buddy as api_buddy
    monkeypatch.setattr(api_buddy, "ASR_RETRY_DELAY_S", 0)

    class Flaky:
        def __init__(self):
            self.starts = 0

        async def start(self):
            self.starts += 1
            if self.starts < 3:
                raise TimeoutError("timed out during opening handshake")

        async def events(self):
            return
            yield

    async def run():
        asr, ready = Flaky(), asyncio.Event()
        await api_buddy._run_asr(asr, line=None, ready=ready)
        return asr.starts, ready.is_set()
    assert asyncio.run(run()) == (3, True)


def test_audio_that_arrives_while_asr_connects_is_buffered_not_dropped(monkeypatch, mock_llm):
    from app.api import buddy as api_buddy

    class SlowASR:
        def __init__(self):
            self.got, self.gate = [], asyncio.Event()

        async def start(self):
            await self.gate.wait()  # the provider handshake is still in flight

        async def send_audio(self, pcm):
            self.got.append(pcm)

        async def finish(self):
            return None

        async def events(self):
            return
            yield

    slow = SlowASR()
    monkeypatch.setattr(api_buddy, "make_bilingual_asr", lambda *_: slow)
    with TestClient(app) as c:
        cid = c.post("/api/calls", json={"transport": "phone-merge"}).json()["id"]
        with c.websocket_connect(f"/twilio/buddy/stream/{cid}") as ws:
            ws.send_text(json.dumps({"event": "start", "streamSid": "MZ3", "start": {"streamSid": "MZ3"}}))
            frame = base64.b64encode(b"\x7f" * 160).decode()
            for _ in range(3):  # grandma starts talking before the ASR is up
                ws.send_text(json.dumps({"event": "media", "streamSid": "MZ3", "media": {"payload": frame}}))
            json.loads(ws.receive_text())  # greeting audio: the server has processed the frames above
            slow.gate.set()
            ws.send_text(json.dumps({"event": "media", "streamSid": "MZ3", "media": {"payload": frame}}))
            ws.send_text(json.dumps({"event": "stop", "streamSid": "MZ3"}))
    assert len(slow.got) == 4


def test_merged_call_before_any_family_exists_is_refused_politely(monkeypatch):
    monkeypatch.setenv("SEED_DEMO_FAMILY", "0")
    monkeypatch.setenv("PUBLIC_WSS_HOST", "kin.example.com")
    monkeypatch.setenv("KIN_API_KEY", "real-key")
    from app import config
    from app.db.session import reset_engine
    config.get_settings.cache_clear(); reset_engine()
    with TestClient(app) as c:
        r = c.post("/twilio/buddy", data={"CallSid": "CA9"})
    assert r.status_code == 200 and "<Say>" in r.text and "<Stream" not in r.text
