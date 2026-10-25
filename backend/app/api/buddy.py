"""Merged-call phone mode (Hey Buddy pattern): Twilio webhook + bidirectional Media Stream + captions page for the
grandchild's phone. See audio/buddy.py for the call flow."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from pathlib import Path
from xml.sax.saxutils import quoteattr

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse

from ..audio.asr import make_bilingual_asr
from ..audio.buddy import BuddyLine, default_people
from ..audio.pipeline import registry
from ..audio.telephony import from_twilio
from ..config import get_settings
from ..db import models as m
from ..db.session import session_scope
from ..security import key_ok, locked
from .twilio import _verify_twilio

log = logging.getLogger("kin.buddy")
router = APIRouter(tags=["phone"])
PHONE_PAGE = Path(__file__).resolve().parent.parent / "static" / "phone.html"
ASR_START_ATTEMPTS = 3
ASR_RETRY_DELAY_S = 1.0
MAX_PENDING_FRAMES = 500  # 10 s of 20 ms Twilio frames held while the ASR connects


@router.post("/twilio/buddy")
async def buddy_voice(request: Request) -> Response:
    """Voice webhook for KIN's number: someone merged KIN into their call. Nothing to install on either phone."""
    form = await request.form()
    _verify_twilio(request, {k: v for k, v in form.items()})
    host = get_settings().public_wss_host
    if not host:
        raise HTTPException(500, "PUBLIC_WSS_HOST is not set (cloudflared/ngrok hostname)")
    with session_scope() as s:
        if s.get(m.Family, get_settings().demo_family_id) is None:  # nothing pre-seeded: the family is set up in the app first
            return Response('<?xml version="1.0" encoding="UTF-8"?>\n<Response><Say>KIN is not set up yet. Open the KIN app, '
                            'add your family, then merge KIN into the call again.</Say></Response>\n', media_type="application/xml")
        c = m.Call(family_id=get_settings().demo_family_id, transport="phone-merge")
        s.add(c); s.flush()
        cid = c.id
    log.info("merged call %s from %s -> call %s", form.get("CallSid"), form.get("From"), cid)
    # the stream url may not carry a query string (Twilio), so the call id rides in the path
    url = quoteattr(f"wss://{host}/twilio/buddy/stream/{cid}")
    return Response(f'<?xml version="1.0" encoding="UTF-8"?>\n<Response><Connect><Stream url={url}/></Connect></Response>\n',
                    media_type="application/xml")


@router.websocket("/twilio/buddy/stream/{call_id}")
async def buddy_stream(ws: WebSocket, call_id: int) -> None:
    await ws.accept()
    with session_scope() as s:
        if s.get(m.Call, call_id) is None:
            await ws.close(code=4404, reason="unknown call id")
            return
    session = registry.get_or_create(call_id)
    g = session.translator.g
    sid: str | None = None

    async def send_audio(mulaw: bytes) -> None:
        if sid:
            await ws.send_text(json.dumps({"event": "media", "streamSid": sid, "media": {"payload": base64.b64encode(mulaw).decode()}}))

    elder, learner = default_people(g)
    line = BuddyLine(session, send_audio, grandparent=elder, learner=learner)
    asr = make_bilingual_asr(g.heritage_lang, session.translator.linker.keyterms())
    asr_ready = asyncio.Event()
    pending: list[bytes] = []
    tasks: list[asyncio.Task] = []
    try:
        while True:
            msg = json.loads(await ws.receive_text())
            event = msg.get("event")
            if event == "start" and sid is None:
                sid = msg.get("streamSid") or msg.get("start", {}).get("streamSid")
                await line.attach()
                tasks = [asyncio.create_task(_run_asr(asr, line, asr_ready)), asyncio.create_task(line.greet())]
            elif event == "media" and sid:
                pending = [*pending, from_twilio(base64.b64decode(msg["media"]["payload"]))][-MAX_PENDING_FRAMES:]
                if asr_ready.is_set():  # until then, keep the first words said while the provider handshake runs
                    for pcm in pending:
                        await asr.send_audio(pcm)
                    pending = []
            elif event == "stop":
                break
    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001  (a bad frame or provider error must not leave the session half-open)
        log.warning("buddy stream %s failed: %s", call_id, e)
    finally:
        for t in tasks:
            t.cancel()
        try:
            await asr.finish()
        except Exception as e:  # noqa: BLE001  (provider socket already gone at hang-up)
            log.debug("ASR finish after hang-up: %s", e)
        if sid:
            await line.detach()
        registry.drop_if_empty(call_id)


async def _run_asr(asr, line: BuddyLine, ready: asyncio.Event) -> None:
    """Start the provider stream off the receive loop, with retries: a slow handshake must not drop the phone call."""
    for attempt in range(1, ASR_START_ATTEMPTS + 1):
        try:
            await asr.start()
            break
        except Exception as e:  # noqa: BLE001  (timeouts, 4xx, DNS: all retried the same way)
            log.warning("ASR start attempt %s/%s failed: %s", attempt, ASR_START_ATTEMPTS, e)
            await asyncio.sleep(ASR_RETRY_DELAY_S)
    else:
        log.error("ASR never started; the call stays up but KIN cannot interpret")
        return
    ready.set()
    async for ev in asr.events():
        if not ev.final or not ev.text.strip():
            continue
        try:
            await line.on_final(ev.text)
        except Exception:  # noqa: BLE001  (one failed turn must not end the call)
            log.exception("buddy turn failed")


@router.get("/api/phone/live")
def live_call() -> dict:
    """The newest call that a merged phone line is feeding, for the captions page to follow."""
    ids = [cs.call_id for cs in registry.active() if cs.phone_line]
    return {"call_id": max(ids) if ids else None}


@router.websocket("/ws/watch/{call_id}")
async def watch(ws: WebSocket, call_id: int, key: str | None = Query(default=None)) -> None:
    """Read-only feed of a call's transcripts and cards (the grandchild's phone screen)."""
    if locked() and not key_ok(key or ws.headers.get("x-kin-key")):
        await ws.close(code=4401, reason="KIN API key required (?key=)")
        return
    await ws.accept()
    session = registry.get_or_create(call_id)

    async def send(msg: dict) -> None:
        await ws.send_text(json.dumps(msg, ensure_ascii=False))

    session.add_watcher(send)
    try:
        await send({"type": "watching", "call_id": call_id})
        while True:
            await ws.receive_text()  # pings; the feed is one-way
    except WebSocketDisconnect:
        pass
    finally:
        session.remove_watcher(send)
        registry.drop_if_empty(call_id)


@router.get("/phone")
def phone_page() -> FileResponse:
    return FileResponse(PHONE_PAGE, media_type="text/html")
