"""Review fix pass: provider/peer failures must not drop the speaker; sessions keyed by connection; unknown call ids rejected."""
import asyncio
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.audio.pipeline import CallSession
from app.audio.tts import MockTTS
from app.main import app
from app.mt.translate import Translator
from tests.graph_fixtures import graph  # noqa: F401
from tests.test_call_ws import mock_llm  # noqa: F401


class _Sink:
    def __init__(self, fail_bytes=False, fail_json=False):
        self.json, self.bytes, self.fail_bytes, self.fail_json = [], 0, fail_bytes, fail_json

    async def send_json(self, m):
        if self.fail_json:
            raise RuntimeError("peer gone")
        self.json.append(m)

    async def send_bytes(self, b):
        if self.fail_bytes:
            raise RuntimeError("peer gone")
        self.bytes += len(b)


def _session(graph, mock_llm):
    from app.db.session import session_scope
    from app.db import models as m
    with session_scope() as s:
        c = m.Call(family_id=graph.family_id); s.add(c); s.flush(); cid = c.id
    return CallSession(call_id=cid, family_id=graph.family_id, translator=Translator(graph, mock_llm), tts=MockTTS())


def test_peer_failure_mid_tts_does_not_raise_and_speaker_still_gets_transcript(graph, mock_llm):
    async def run():
        cs = _session(graph, mock_llm)
        gp, gc = _Sink(), _Sink(fail_bytes=True, fail_json=True)
        await cs.join("grandparent", "p_kamala", gp.send_json, gp.send_bytes)
        await cs.join("grandchild", "p_arjun", gc.send_json, gc.send_bytes)
        payload = await cs.process_utterance(cs.sides["grandparent"], "உன் மாமா நேத்து போன் பண்ணான்.")
        assert payload["translation"]
        assert any(m["type"] == "transcript" for m in gp.json) and any(m["type"] == "latency" for m in gp.json)
    asyncio.run(run())


def test_on_audio_swallows_dead_asr(graph, mock_llm):
    async def run():
        cs = _session(graph, mock_llm)
        gp = _Sink()
        side = await cs.join("grandparent", "p_kamala", gp.send_json, gp.send_bytes)

        class Dead:
            async def send_audio(self, b): raise ConnectionError("closed")
            async def finish(self): pass
        side.asr = Dead()
        await cs.on_audio("grandparent", b"\x00\x00" * 160)  # must not raise
        assert any(m.get("type") == "status" and m.get("asr") == "ended" for m in gp.json)
        await cs.on_audio("grandparent", b"\x00\x00" * 160)  # the next frame reopens, and says so (clears the banner)
        assert side.asr is not None and _statuses(gp)[-1] == "ok"
    asyncio.run(run())


def _statuses(sink):
    return [m["asr"] for m in sink.json if m.get("type") == "status"]


def test_failed_asr_connect_is_retried_after_backoff(graph, mock_llm, monkeypatch):
    """A failed connect used to leave the dead session in side.asr, so on_audio never reopened it: deaf all call."""
    from app.audio import pipeline
    from app.audio.asr import MockASR
    made = []

    class Flaky(MockASR):
        async def start(self):
            if len(made) == 1:
                raise OSError("wifi blip")
    monkeypatch.setattr(pipeline, "make_asr", lambda **kw: made.append(Flaky()) or made[-1])

    async def run():
        cs = _session(graph, mock_llm)
        gp = _Sink()
        side = await cs.join("grandparent", "p_kamala", gp.send_json, gp.send_bytes)
        assert side.asr is None and _statuses(gp) == ["unavailable"]
        await cs.on_audio("grandparent", b"\x00\x00" * 160)  # inside the backoff: no reconnect storm
        assert len(made) == 1
        side.asr_retry_at = 0.0  # backoff elapsed
        await cs.on_audio("grandparent", b"\x00\x00" * 160)
        assert len(made) == 2 and side.asr is made[1] and _statuses(gp) == ["unavailable", "ok"]
        await cs.leave("grandparent", token=side.token)
    asyncio.run(run())


def test_provider_close_reopens_with_ok_status(graph, mock_llm):
    async def run():
        cs = _session(graph, mock_llm)
        gp = _Sink()
        side = await cs.join("grandparent", "p_kamala", gp.send_json, gp.send_bytes)
        first = side.asr
        await first.finish()  # the provider closes the stream (idle, rejoin)
        await side.asr_task
        assert side.asr is None and _statuses(gp) == ["ended"]
        await cs.on_audio("grandparent", b"\x00\x00" * 160)
        assert side.asr is not None and side.asr is not first and _statuses(gp) == ["ended", "ok"]
        assert gp.json[0]["type"] == "joined"  # the first start stays quiet: clients read "joined" first
        await cs.leave("grandparent", token=side.token)
    asyncio.run(run())


def test_deliberate_asr_stop_is_silent(graph, mock_llm):
    """A reconnect or leave cancelled the loop, whose finally said "ended"; on LiveKit that reaches the rejoined client
    (same identity) and no "ok" follows, so the banner stayed up all call. Only a provider close says "ended"."""
    async def run():
        cs = _session(graph, mock_llm)
        a, b = _Sink(), _Sink()
        old = await cs.join("grandparent", "p_kamala", a.send_json, a.send_bytes)
        new = await cs.join("grandparent", "p_kamala", b.send_json, b.send_bytes)  # reconnect stops old's ASR
        await asyncio.wait({old.asr_task})
        task = new.asr_task
        await cs.leave("grandparent", token=new.token)
        await asyncio.wait({task})
        assert _statuses(a) == [] and _statuses(b) == []
    asyncio.run(run())


def test_failed_send_is_logged_not_swallowed(graph, mock_llm, caplog):
    async def run():
        cs = _session(graph, mock_llm)
        dead = _Sink(fail_json=True)
        side = await cs.join("grandparent", "p_kamala", dead.send_json, dead.send_bytes, start_asr=False)
        await cs._safe_send(side, {"type": "glance"})
    asyncio.run(run())
    assert any("send glance to grandparent failed: peer gone" in r.getMessage() for r in caplog.records)


def test_rejoin_same_role_does_not_let_old_connection_evict_new_one(graph, mock_llm):
    async def run():
        cs = _session(graph, mock_llm)
        a, b = _Sink(), _Sink()
        old = await cs.join("grandparent", "p_kamala", a.send_json, a.send_bytes)
        new = await cs.join("grandparent", "p_kamala", b.send_json, b.send_bytes)
        await cs.leave("grandparent", token=old.token)   # the old socket's finally-block
        assert cs.sides["grandparent"] is new
        await cs.leave("grandparent", token=new.token)
        assert "grandparent" not in cs.sides
    asyncio.run(run())


def test_unknown_call_id_is_rejected_at_connect(mock_llm):
    with TestClient(app) as c:
        with pytest.raises(WebSocketDisconnect) as ei:
            with c.websocket_connect("/ws/call/987654?role=grandparent&person=p_kamala") as ws:
                ws.receive_json()
        assert ei.value.code == 4404


def test_call_socket_refuses_world_and_space_calls(mock_llm):
    from tests.test_buddy import _space_calls
    with TestClient(app) as c:
        for cid in _space_calls():
            with pytest.raises(WebSocketDisconnect) as ei:
                with c.websocket_connect(f"/ws/call/{cid}?role=grandparent&person=p_kamala") as ws:
                    ws.receive_json()
            assert ei.value.code == 4404, cid
