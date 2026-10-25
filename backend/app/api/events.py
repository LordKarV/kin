"""Per-user event channel (ringing): WS /ws/events?token=<X-KIN-User token>[&key=<KIN key when locked>] (or the
X-KIN-User / X-KIN-Key headers).

Server -> client JSON only: call.incoming | call.answered | call.declined | call.cancelled | call.missed, plus
{"type":"ping"} every 25 s so idle mobile connections stay open. The client never sends anything that matters."""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Query, WebSocket

from ..db.session import session_scope
from ..security import key_ok, locked
from ..world.users import user_by_token

log = logging.getLogger("kin.events")
router = APIRouter()
PING_EVERY_S = 25

# ponytail: in-process registry, so one worker only (same ceiling as the call registry); a pub/sub bus if KIN scales out.
_sockets: dict[int, set[WebSocket]] = {}


async def send_to(person_id: int, msg: dict) -> bool:
    """Send to every open socket of this user. True when at least one took it."""
    delivered = False
    for ws in list(_sockets.get(person_id, ())):
        try:
            await ws.send_text(json.dumps(msg, ensure_ascii=False))
            delivered = True
        except Exception:  # noqa: BLE001  a dead socket: drop it, the client reconnects
            log.info("event socket for p%s is gone; dropping it", person_id)
            _sockets.get(person_id, set()).discard(ws)
    return delivered


async def drop(person_id: int) -> None:
    """Close every event socket of a deleted account (calls.drop_person)."""
    for ws in _sockets.pop(person_id, set()):
        try:
            await ws.close(code=4401, reason="account deleted")
        except Exception:  # noqa: BLE001  already closing
            log.info("event socket for p%s was already closing", person_id)


def _person_for(token: str | None) -> int | None:
    with session_scope() as s:
        user = user_by_token(s, token)
        return user.person_id if user else None


async def _ping(ws: WebSocket) -> None:
    while True:
        await asyncio.sleep(PING_EVERY_S)
        await ws.send_text('{"type":"ping"}')


@router.websocket("/ws/events")
async def events_ws(ws: WebSocket, token: str | None = Query(default=None), key: str | None = Query(default=None)):
    # Accept first so the client sees the 4401 close code (a close before accept is a bare 403 handshake failure).
    await ws.accept()
    if locked() and not key_ok(key or ws.headers.get("x-kin-key")):
        await ws.close(code=4401, reason="KIN API key required (?key=)")
        return
    # The header keeps the token out of access logs; ?token= is for clients that cannot set one.
    person_id = await asyncio.to_thread(_person_for, ws.headers.get("x-kin-user") or token)
    if person_id is None:
        await ws.close(code=4401, reason="X-KIN-User token required (?token=)")
        return
    _sockets.setdefault(person_id, set()).add(ws)
    pinger = asyncio.create_task(_ping(ws))
    try:
        from .calls import pending_rings
        for msg in pending_rings(person_id):  # rings and ring endings that happened while this socket was away
            await ws.send_text(json.dumps(msg, ensure_ascii=False))
        while (await ws.receive()).get("type") != "websocket.disconnect":
            pass
    except Exception:  # noqa: BLE001  a send on a closing socket; the finally cleans up
        log.info("event socket for p%s closed", person_id)
    finally:
        pinger.cancel()
        socks = _sockets.get(person_id)
        if socks is not None:
            socks.discard(ws)
            if not socks:
                _sockets.pop(person_id, None)
