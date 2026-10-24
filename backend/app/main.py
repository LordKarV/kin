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
    from .db.session import init_db

    init_db()
    yield


app = FastAPI(title="KIN", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health() -> dict:
    s = get_settings()
    return {"status": "ok", "llm_model": s.llm_model, "asr_provider": s.asr_provider, "tts_provider": s.tts_provider}
