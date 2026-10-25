from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import models as m
from ..db.session import get_session
from .calls import legacy_family

router = APIRouter(prefix="/api/glossary", tags=["glossary"])


@router.get("")
def glossary(family_id: int | None = None, limit: int = 100, s: Session = Depends(get_session)) -> list[dict]:
    fid = legacy_family(s, family_id).id
    rows = s.scalars(select(m.GlossaryEntry).where(m.GlossaryEntry.family_id == fid).order_by(m.GlossaryEntry.id.desc()).limit(limit)).all()
    people = {p.id: p.display_name for p in s.scalars(select(m.Person).where(m.Person.family_id == fid))}
    utts = {u.id: u for u in s.scalars(select(m.Utterance).where(m.Utterance.id.in_([r.utterance_id for r in rows if r.utterance_id])))} if rows else {}
    return [{"id": r.id, "card": r.card, "speaker": people.get(r.speaker_id), "created_at": r.created_at.isoformat() if r.created_at else None,
             "audio_url": r.audio_url, "utterance_id": r.utterance_id, "src_text": utts[r.utterance_id].src_text if r.utterance_id in utts else ""} for r in rows]
