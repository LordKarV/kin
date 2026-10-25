"""Demo endpoint: generic vs grounded side by side on one utterance (plan §10 step 3)."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db.session import get_session
from ..mt.translate import get_translator
from .calls import legacy_family

router = APIRouter(prefix="/api/translate", tags=["translate"])


class CompareIn(BaseModel):
    text: str
    speaker: str | None = None   # default: the family's eldest living member
    listener: str | None = None  # default: the family's learner
    family_id: int | None = None
    target_lang: str = "en"


@router.post("/compare")
async def compare(body: CompareIn, s: Session = Depends(get_session)) -> dict:
    tr = get_translator(legacy_family(s, body.family_id).id)
    speaker, listener = body.speaker or tr.g.elder_slug(), body.listener or tr.g.learner_slug()
    generic, grounded = await asyncio.gather(
        asyncio.to_thread(tr.translate_generic, body.text),
        asyncio.to_thread(tr.translate, body.text, speaker, listener, (), (), None, body.target_lang),
    )
    return {"generic": generic.as_dict(), "grounded": grounded.as_dict()}


@router.post("/grounded")
async def grounded(body: CompareIn, s: Session = Depends(get_session)) -> dict:
    tr = get_translator(legacy_family(s, body.family_id).id)
    speaker, listener = body.speaker or tr.g.elder_slug(), body.listener or tr.g.learner_slug()
    res = await asyncio.to_thread(tr.translate, body.text, speaker, listener, (), (), None, body.target_lang)
    return res.as_dict()
