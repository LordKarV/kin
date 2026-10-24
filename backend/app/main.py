"""KIN backend: FastAPI app."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from sqlalchemy import select

    from .db import models as m
    from .db.seed import seed_demo_family
    from .db.session import init_db, session_scope

    from .security import check_startup

    check_startup()
    init_db()
    with session_scope() as s:  # demo family is always present (plan Phase 1); idempotent
        if s.scalar(select(m.Family)) is None:
            seed_demo_family(s)
    yield


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

from .api import calls, connector, fade, glossary, graph, latency, translate, twilio, ws  # noqa: E402
from .audio.glossary_audio import media_dir  # noqa: E402

app.include_router(calls.router)
app.include_router(graph.router)
app.include_router(glossary.router)
app.include_router(fade.router)
app.include_router(connector.router)
app.include_router(twilio.router)
app.include_router(latency.router)
app.mount("/media", StaticFiles(directory=str(media_dir())), name="media")
app.include_router(translate.router)
app.include_router(ws.router)


@app.get("/health")
def health() -> dict:
    s = get_settings()
    return {"status": "ok", "llm_model": s.llm_model, "asr_provider": s.asr_provider, "tts_provider": s.tts_provider}
