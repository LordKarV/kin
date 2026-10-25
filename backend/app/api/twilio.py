"""Twilio webhooks + ConversationRelay WebSocket (Phase 5)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Form, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from ..audio.pipeline import registry
from ..audio.twilio_bridge import PhoneLeg, relay_twiml
from ..config import get_settings
from ..db import models as m
from ..db.session import session_scope
from ..security import locked
from .calls import legacy_call, legacy_family

log = logging.getLogger("kin.twilio")
router = APIRouter(tags=["phone"])


def _ws_url(call_id: int, role: str) -> str:
    host = get_settings().public_wss_host
    if not host:
        raise HTTPException(500, "PUBLIC_WSS_HOST is not set (ngrok/cloudflared hostname)")
    return f"wss://{host}/twilio/relay?call_id={call_id}&role={role}"


def _heritage_locale() -> str:
    s = get_settings()
    if s.twilio_heritage_lang:
        return s.twilio_heritage_lang
    from ..graph.kin_tables import load_table
    from ..mt.translate import get_translator
    try:
        return load_table(get_translator(s.demo_family_id).g.heritage_lang).locale
    except Exception:  # noqa: BLE001
        return "ta-IN"


def _new_call() -> int:
    with session_scope() as s:
        c = m.Call(family_id=legacy_family(s, None).id, transport="twilio")  # the phone bridge is legacy: never the space
        s.add(c); s.flush()
        return c.id


def _verify_twilio(request: Request, form: dict) -> None:
    """Reject webhooks not signed by our Twilio account. Without an auth token only an unlocked dev server accepts them:
    /twilio/ skips the KIN key gate, so a locked (exposed) server must fail closed."""
    token = get_settings().twilio_auth_token
    if not token:
        if locked():
            raise HTTPException(403, "TWILIO_AUTH_TOKEN is not set")
        return
    from twilio.request_validator import RequestValidator

    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc))
    url = f"{proto}://{host}{request.url.path}" + (f"?{request.url.query}" if request.url.query else "")
    if not RequestValidator(token).validate(url, form, request.headers.get("x-twilio-signature", "")):
        raise HTTPException(403, "invalid Twilio signature")


@router.post("/twilio/voice")
async def voice(request: Request, role: str = "grandparent", call_id: int | None = None):
    """Inbound call webhook: the grandparent dials the Twilio number; nothing to install."""
    form = await request.form()
    _verify_twilio(request, {k: v for k, v in form.items()})
    cid = call_id or _new_call()
    s = get_settings()
    log.info("inbound call %s from %s → call %s", form.get("CallSid"), form.get("From"), cid)
    welcome = "வணக்கம். KIN இணைக்கிறது." if role == "grandparent" else "Connecting you to KIN."
    loc = _heritage_locale()
    xml = relay_twiml(_ws_url(cid, role), role, language=loc if role == "grandparent" else "en-US",
                      other_language="en-US" if role == "grandparent" else loc, welcome=welcome)
    return Response(content=xml, media_type="application/xml")


class Dial(BaseModel):
    to: str
    role: str = "grandparent"
    call_id: int | None = None


@router.post("/api/phone/dial")
def dial(body: Dial) -> dict:
    """Outbound: KIN calls a phone and bridges it into an existing (or new) call."""
    s = get_settings()
    if not (s.twilio_account_sid and s.twilio_auth_token and s.twilio_number):
        raise HTTPException(400, "Twilio is not configured (TWILIO_ACCOUNT_SID/AUTH_TOKEN/NUMBER)")
    from twilio.rest import Client

    cid = body.call_id or _new_call()
    loc = _heritage_locale()
    xml = relay_twiml(_ws_url(cid, body.role), body.role, language=loc if body.role == "grandparent" else "en-US",
                      other_language="en-US" if body.role == "grandparent" else loc)
    call = Client(s.twilio_account_sid, s.twilio_auth_token).calls.create(to=body.to, from_=s.twilio_number, twiml=xml)
    return {"call_id": cid, "sid": call.sid}


@router.websocket("/twilio/relay")
async def relay(ws: WebSocket, call_id: int = Query(...), role: str = Query("grandparent")):
    try:
        with session_scope() as s:
            legacy_call(s, call_id)  # a world call, or one in the space, is never bridged to an unauthenticated phone leg
    except HTTPException:
        await ws.close(code=4404, reason="unknown call")
        return
    await ws.accept()
    session = registry.get_or_create(call_id)
    g = session.translator.g
    person = (next((p.slug for p in g.people.values() if p.slug == "p_kamala"), None) or next(p.slug for p in g.people.values() if not p.is_learner)) \
        if role == "grandparent" else next(p.slug for p in g.people.values() if p.is_learner)
    leg = PhoneLeg(ws, role, person, _heritage_locale())
    joined = False
    try:
        while True:
            msg = await ws.receive_json()
            t = msg.get("type")
            if t == "setup":
                if msg.get("customParameters", {}).get("role"):
                    leg.role = msg["customParameters"]["role"]
                await leg.attach(session); joined = True
                log.info("relay setup call=%s sid=%s from=%s", call_id, msg.get("callSid"), msg.get("from"))
            elif t == "prompt":
                if not joined:
                    await leg.attach(session); joined = True
                if msg.get("last", True) and msg.get("voicePrompt", "").strip():
                    await session.on_text(leg.role, msg["voicePrompt"])
            elif t == "dtmf" and msg.get("digit") == "#":
                await ws.send_json({"type": "end"})
            elif t == "error":
                log.warning("relay error: %s", msg.get("description"))
            # interrupt: Relay already stopped speaking; nothing to do for a human-to-human bridge
    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001
        log.warning("relay ws error: %s", e)
    finally:
        if joined:
            await session.leave(leg.role)
        registry.drop_if_empty(call_id)
