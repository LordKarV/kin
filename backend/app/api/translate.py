"""Demo endpoint: generic vs grounded side by side on one utterance (plan §10 step 3)."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel

from ..config import get_settings
from ..mt.translate import get_translator

router = APIRouter(prefix="/api/translate", tags=["translate"])


class CompareIn(BaseModel):
    text: str
    speaker: str = "p_kamala"
    listener: str = "p_arjun"
    family_id: int | None = None
    target_lang: str = "en"


@router.post("/compare")
async def compare(body: CompareIn) -> dict:
    tr = get_translator(body.family_id or get_settings().demo_family_id)
    generic, grounded = await asyncio.gather(
        asyncio.to_thread(tr.translate_generic, body.text),
        asyncio.to_thread(tr.translate, body.text, body.speaker, body.listener, (), (), None, body.target_lang),
    )
    return {"generic": generic.as_dict(), "grounded": grounded.as_dict()}


@router.post("/grounded")
async def grounded(body: CompareIn) -> dict:
    tr = get_translator(body.family_id or get_settings().demo_family_id)
    res = await asyncio.to_thread(tr.translate, body.text, body.speaker, body.listener, (), (), None, body.target_lang)
    return res.as_dict()
