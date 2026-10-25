"""WebSocket transport (primary): browser ⇄ FastAPI. Binary frames = 16 kHz mono PCM16 mic audio in, TTS audio out.
JSON frames: client → {"type":"text","text":...} | {"type":"verify",...}; server → joined/peer/partial/transcript/audio_start/audio_end/status/error."""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from ..audio.pipeline import registry
from ..db import models as m
from ..db.session import session_scope
from ..security import key_ok, locked

log = logging.getLogger("kin.ws")
router = APIRouter()


@router.websocket("/ws/call/{call_id}")
async def call_ws(ws: WebSocket, call_id: int, role: str = Query(...), person: str = Query(...), key: str | None = Query(default=None)):
    if locked() and not key_ok(key or ws.headers.get("x-kin-key")):
        await ws.close(code=4401, reason="KIN API key required (?key=)")
        return
    with session_scope() as s:
        exists = s.get(m.Call, call_id) is not None
    if not exists:
        await ws.close(code=4404, reason="unknown call id; create one with POST /api/calls")
        return
    await ws.accept()
    session = registry.get_or_create(call_id)

    async def send_json(msg: dict) -> None:
        await ws.send_text(json.dumps(msg, ensure_ascii=False))

    async def send_bytes(b: bytes) -> None:
        await ws.send_bytes(b)

    try:
        side = await session.join(role, person, send_json, send_bytes)
    except PermissionError as e:  # a world call needs a verified person; the legacy socket cannot provide one
        await ws.close(code=4403, reason=str(e)[:120] or "not allowed on this call")
        registry.drop_if_empty(call_id)
        return
    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if msg.get("bytes") is not None:
                await session.on_audio(role, msg["bytes"])
            elif msg.get("text"):
                try:
                    data = json.loads(msg["text"])
                except json.JSONDecodeError:
                    continue
                t = data.get("type")
                if t == "text":
                    await session.on_text(role, data.get("text", ""))
                elif t == "verify":
                    from ..fade.service import record_verification  # Phase 4
                    await send_json(record_verification(data))
                elif t == "ping":
                    await send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001
        log.warning("ws error (%s/%s): %s", call_id, role, e)
    finally:
        await session.leave(role, token=side.token)
        registry.drop_if_empty(call_id)
