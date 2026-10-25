"""KIN backend: FastAPI app."""
from __future__ import annotations

import html
import logging
from contextlib import asynccontextmanager
from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from .config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("kin.main")
WORLD_CLOSE_TIMEOUT_S = 25  # LiveWorld.close runs the final extraction (an LLM call) per live call


async def _close_live_worlds() -> None:
    """Shutdown (or a --reload restart) mid-call: run each live world call's final extraction and knowledge flush,
    which otherwise only happen when the room empties."""
    import asyncio

    from .audio.pipeline import registry

    worlds = [cs for cs in registry.active() if cs.world is not None]
    results = await asyncio.gather(*(asyncio.wait_for(asyncio.to_thread(cs.world.close), WORLD_CLOSE_TIMEOUT_S)
                                     for cs in worlds), return_exceptions=True)
    for cs, res in zip(worlds, results):
        if isinstance(res, BaseException):
            log.error("closing live world call %s at shutdown failed: %r", cs.call_id, res)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from sqlalchemy import select

    from .db import models as m
    from .db.seed import seed_demo_family
    from .db.session import init_db, session_scope

    from .security import check_startup

    check_startup()
    init_db()
    from .db.seed import seed_languages

    with session_scope() as s:  # reference data (languages, kin tables) always; a demo family only when asked for
        if get_settings().seed_demo_family and s.scalar(select(m.Family)) is None:
            seed_demo_family(s)
        seed_languages(s)
    import asyncio

    from .api.calls import sweep_loop

    sweep_task = asyncio.create_task(sweep_loop())  # privacy sweep: third-party expiry at startup and hourly
    try:
        yield
    finally:
        sweep_task.cancel()
        await _close_live_worlds()


app = FastAPI(title="KIN", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def api_key_gate(request, call_next):
    from fastapi.responses import JSONResponse

    from .security import ALWAYS_LOCKED, PUBLIC_PREFIXES, key_ok, locked

    path = request.url.path
    needs = path in ALWAYS_LOCKED or (locked() and (path.startswith("/api/") or path.startswith("/ws/")) and not path.startswith(PUBLIC_PREFIXES))
    if needs:
        given = request.headers.get("x-kin-key") or request.query_params.get("key")
        auth = request.headers.get("authorization", "")
        if not given and auth.lower().startswith("bearer "):
            given = auth.split(" ", 1)[1]
        if not key_ok(given):
            return JSONResponse({"detail": "KIN API key required (X-KIN-Key header, Authorization: Bearer, or ?key=)"}, status_code=401)
    return await call_next(request)


from fastapi.staticfiles import StaticFiles  # noqa: E402

from .api import buddy, calls, events, rtc, cards, family_build, connector, fade, glossary, graph, languages, latency, translate, twilio, ws, users, world, dev, sms, explain  # noqa: E402
from .audio.glossary_audio import media_dir  # noqa: E402

app.include_router(calls.router)
app.include_router(graph.router)
app.include_router(glossary.router)
app.include_router(fade.router)
app.include_router(connector.router)
app.include_router(twilio.router)
app.include_router(buddy.router)
app.include_router(rtc.router)
app.include_router(family_build.router)
app.include_router(latency.router)
app.include_router(languages.router)
app.include_router(cards.router)
app.mount("/media", StaticFiles(directory=str(media_dir())), name="media")
app.include_router(translate.router)
app.include_router(ws.router)
app.include_router(users.router)
app.include_router(world.router)
app.include_router(dev.router)
app.include_router(sms.router)
app.include_router(explain.router)
app.include_router(events.router)


@app.get("/", include_in_schema=False)
def invite_page(request: Request) -> HTMLResponse:
    """Share sends `http(s)://<server>/?call=N[&key=K][&code=C]` (Messages makes that tappable); this page hands it to
    the app as kin://join. Outside /api, so the key gate does not apply; the page only echoes the link's own query."""
    query = {k: v for k, v in request.query_params.items() if k in ("call", "key", "code")}
    if "call" not in query:
        return HTMLResponse("<!doctype html><title>KIN</title><p>This is a KIN server.</p>")
    link = html.escape("kin://join?" + urlencode(query))
    return HTMLResponse(f'<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
                        f'<meta http-equiv="refresh" content="0;url={link}"><title>Join the KIN call</title>'
                        f'<p><a href="{link}">Open the call in KIN</a></p>')


@app.get("/health")
def health() -> dict:
    s = get_settings()
    return {"status": "ok", "llm_model": s.llm_model, "asr_provider": s.asr_provider, "tts_provider": s.tts_provider}
