"""Supported languages (the 25 Muse Voice Transcribe languages) and which have a kin table."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import models as m
from ..db.session import get_session
from ..graph.kin_tables import MUSE_LANGUAGES, available_codes, load_table

router = APIRouter(tags=["languages"])


@router.get("/api/languages")
def languages(s: Session = Depends(get_session)) -> list[dict]:
    rows = {r.code: r for r in s.scalars(select(m.Language))}
    out = []
    for code in sorted(MUSE_LANGUAGES):
        avail = code in available_codes()
        t = load_table(code) if avail else None
        r = rows.get(code)
        out.append({"code": code, "name": MUSE_LANGUAGES[code], "native_name": t.native_name if t else "", "available": avail,
                    "verified": bool(t.verified) if t else False, "source": t.source if t else "", "locale": t.locale if t else "",
                    "kin_terms": len([d for d in t.terms if d.kind == "kin"]) if t else 0, "dropped": len(t.dropped) if t else 0, "in_db": r is not None})
    return out
