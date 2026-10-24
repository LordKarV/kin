"""Latency panel data: p50/p95 per stage over recent utterances, against the plan §4 budget."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import models as m
from ..db.session import get_session

router = APIRouter(prefix="/api/latency", tags=["latency"])
STAGES = ["asr_ms", "link_ms", "mt_ms", "tts_first_byte_ms", "total_ms"]
BUDGET = {"asr_ms": 400, "mt_ms": 700, "tts_first_byte_ms": 400, "total_p50_ms": 2000, "total_p95_ms": 3000}


def _pct(vals: list[float], q: float) -> float:
    if not vals:
        return 0.0
    vals = sorted(vals)
    return float(vals[min(len(vals) - 1, int(round(q * (len(vals) - 1))))])


@router.get("/summary")
def summary(limit: int = 200, call_id: int | None = None, s: Session = Depends(get_session)) -> dict:
    stmt = select(m.Utterance).order_by(m.Utterance.id.desc()).limit(limit)
    if call_id:
        stmt = stmt.where(m.Utterance.call_id == call_id)
    rows = s.scalars(stmt).all()
    stages = {}
    for k in STAGES:
        vals = [float(u.latencies.get(k, 0.0)) for u in rows if u.latencies and k in u.latencies]
        stages[k] = {"p50": round(_pct(vals, 0.5), 1), "p95": round(_pct(vals, 0.95), 1), "n": len(vals)}
    return {"n": len(rows), "stages": stages, "budget": BUDGET}
