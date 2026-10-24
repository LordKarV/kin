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
    asyncio.run(run())


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
