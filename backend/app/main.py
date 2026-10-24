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

    init_db()
    with session_scope() as s:  # demo family is always present (plan Phase 1); idempotent
        if s.scalar(select(m.Family)) is None:
            seed_demo_family(s)
    yield


app = FastAPI(title="KIN", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


from .api import calls, fade, glossary, graph, translate, ws  # noqa: E402

app.include_router(calls.router)
app.include_router(graph.router)
app.include_router(glossary.router)
app.include_router(fade.router)
app.include_router(translate.router)
app.include_router(ws.router)


@app.get("/health")
def health() -> dict:
    s = get_settings()
    return {"status": "ok", "llm_model": s.llm_model, "asr_provider": s.asr_provider, "tts_provider": s.tts_provider}
