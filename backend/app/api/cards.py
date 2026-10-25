"""Glance cards REST: lexicon status per language, and glance items for a typed line (tests, phone page)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from ..cards.glance import engine_for
from ..cards.images import get_pictures
from ..cards.lexicon import CATEGORIES, ensure_lexicon, load_lexicon, path_for
from ..config import get_settings
from ..graph.kin_tables import MUSE_LANGUAGES
from ..mt.translate import get_translator

log = logging.getLogger("kin.api.cards")
router = APIRouter(tags=["cards"])


def _generate(lang: str) -> None:
    try:
        ensure_lexicon(lang)
    except Exception as e:  # noqa: BLE001  (background job: log, never crash the server)
        log.error("lexicon generation for %s failed: %s", lang, e)


@router.get("/api/cards/lexicon/{lang}")
def lexicon_status(lang: str, background: BackgroundTasks, generate: bool = False) -> dict:
    if lang not in MUSE_LANGUAGES:
        raise HTTPException(404, f"unsupported language {lang!r}")
    present = path_for(lang).exists()
    if generate and not present:
        background.add_task(_generate, lang)
    lex = load_lexicon(lang)
    return {"lang": lang, "available": present, "generating": generate and not present, "verified": lex.verified, "source": lex.source,
            "generated_at": lex.generated_at, "count": len(lex.entries), "dropped": len(lex.dropped), "by_category": lex.counts(),
            "categories": list(CATEGORIES)}


class GlanceIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    family_id: int | None = None
    speaker: str | None = None
    listener: str | None = None


@router.post("/api/cards/glance")
def glance(body: GlanceIn, background: BackgroundTasks) -> dict:
    tr = get_translator(body.family_id or get_settings().demo_family_id)
    g = tr.g
    speaker = body.speaker or g.elder_slug()
    listener = body.listener or g.learner_slug()
    found = engine_for(tr).items(body.text, speaker, listener)
    pics = get_pictures()
    for it, wt in found:
        if wt and not it["image_url"] and pics.needs_fetch(wt):
            background.add_task(pics.fetch, wt)  # first sighting: no picture now, cached for the next one
    return {"items": [it for it, _ in found]}
