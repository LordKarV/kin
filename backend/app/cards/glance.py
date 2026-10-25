"""Glance items for one transcript line: family-graph linker spans (who / what / ask) + cultural lexicon matches (term / saying).

Item contract (sent as {"type":"glance","role":"grandparent","items":[...]}):
  key, kind (who|what|term|saying|ask), title (as heard), native, body, category, image_url, image_credit, source_url
  ask items also carry term (the kin word) and guess (the word before it).
Pictures arrive later as {"type":"glance_image","key",...}; see live_glance().
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging
from typing import TYPE_CHECKING

from sqlalchemy import select

from ..db import models as m
from ..db.session import session_scope
from ..graph.ontology import normalize_term
from .images import get_pictures
from .lexicon import LexEntry, load_lexicon
from .matcher import Matcher, tokenize

if TYPE_CHECKING:
    from ..audio.pipeline import CallSession, Side
    from ..mt.translate import Translator

log = logging.getLogger("kin.cards.glance")
THING_CATEGORY = {"dish": "food", "place": "place", "event": "festival"}
GLOSS_CATEGORY = {"idiom": "saying", "proverb": "saying", "honorific": "address", "register": "address", "cultural": "other"}
EXTRA_SUFFIXES = ("s", "es")  # romanized/English plurals (-s, -es)


def glossary_entries(family_id: int) -> list[LexEntry]:
    """Past pragmatics cards for this family as lexicon entries: a term explained once is instant forever after."""
    out: list[LexEntry] = []
    seen: set[str] = set()
    with session_scope() as s:
        rows = s.scalars(select(m.GlossaryEntry).where(m.GlossaryEntry.family_id == family_id).order_by(m.GlossaryEntry.id)).all()
        for r in rows:
            c = r.card or {}
            src = (c.get("source") or "").strip()
            if not src or normalize_term(src) in seen:
                continue
            seen.add(normalize_term(src))
            out.append(LexEntry(f"gloss:{r.id}", (src,), (c.get("meaning") or c.get("literal") or "").strip(),
                                GLOSS_CATEGORY.get(c.get("kind", ""), "other"), (c.get("why_it_matters") or "").strip()))
    return out


class GlanceEngine:
    def __init__(self, translator: "Translator", extra: list[LexEntry] = ()):
        self.translator = translator
        self.graph = translator.g
        self.lang = self.graph.heritage_lang
        lex = load_lexicon(self.lang)
        entries = [dataclasses.replace(e, key=f"lex:{self.lang}:{e.key}") for e in lex.entries] + list(extra)
        table = translator.linker.table
        self.matcher = Matcher(entries, suffixes=(*table.suffixes, *table.roman_suffixes, *EXTRA_SUFFIXES), final_strip=tuple(table.final_strip))

    def items(self, text: str, speaker: str, listener: str) -> list[tuple[dict, str]]:
        """[(item, wiki_title)] in text order. Linker spans win over overlapping lexicon matches."""
        spans = self.translator.linker.link(text, speaker, listener)
        lex = self.matcher.match(text)
        pics = get_pictures()
        out: list[tuple[int, dict, str]] = []
        for sp in spans:
            it = self._from_span(sp, text, lex)
            if it:
                out.append((sp.start, *it))
        for mt in lex:
            if any(mt.start < sp.end and sp.start < mt.end for sp in spans if sp.method != "generic-address"):
                continue
            e = mt.entry
            body = ". ".join(x for x in (e.translate_as, e.note) if x)
            out.append((mt.start, _item(e.key, "saying" if e.category == "saying" else "term", mt.source, e.native, body, e.category), e.wiki_title))
        for _, it, wt in out:
            rec = pics.cached(wt) if wt else None
            if rec:
                it.update(image_url=rec["image_url"], image_credit=rec.get("image_credit", ""), source_url=rec.get("source_url", ""))
        out.sort(key=lambda x: x[0])
        return [(it, wt) for _, it, wt in out]

    def _from_span(self, sp, text: str, lex) -> tuple[dict, str] | None:
        g = self.graph
        if sp.type == "person" and sp.node:
            node = g.by_slug.get(sp.node)
            return _item(sp.node, "who", sp.source, node.lang_name if node else "", sp.display, "person"), ""
        if sp.type == "kin" and sp.method == "unknown-relative":
            before = [t for t in tokenize(text[: sp.start])]
            guess = text[before[-1].start:before[-1].end] if before else ""
            it = _item(f"ask:{normalize_term(sp.source)}", "ask", sp.source, sp.source, f"{sp.display}: a relative KIN has not met yet", "kin")
            return {**it, "term": sp.source, "guess": guess}, ""
        if sp.type in THING_CATEGORY and sp.node:
            t = g.thing_by_slug.get(sp.node)
            over = next((mt.entry for mt in lex if mt.start < sp.end and sp.start < mt.end), None)  # borrow the lexicon's picture/note
            body = ". ".join(x for x in (sp.display, t.note if t else "", over.note if over else "") if x)
            wiki = (over.wiki_title if over and over.wiki_title else (t.name if t else ""))
            return _item(f"thing:{sp.node}", "what", sp.source, t.lang_name if t else "", body, THING_CATEGORY[sp.type]), wiki
        return None


def _item(key: str, kind: str, title: str, native: str, body: str, category: str) -> dict:
    return {"key": key, "kind": kind, "title": title, "native": native, "body": body, "category": category,
            "image_url": "", "image_credit": "", "source_url": ""}


_engines: dict[int, tuple[object, GlanceEngine]] = {}


def engine_for(translator: "Translator", refresh: bool = False) -> GlanceEngine:
    """One engine per family, rebuilt when the graph object changes (translator cache reset) or on refresh (finals)."""
    fid = translator.g.family_id
    hit = _engines.get(fid)
    if hit and hit[0] is translator.g and not refresh:
        return hit[1]
    eng = GlanceEngine(translator, glossary_entries(fid))
    _engines[fid] = (translator.g, eng)
    return eng


def reset_engines() -> None:
    _engines.clear()


async def live_glance(cs: "CallSession", side: "Side", text: str, final: bool = False) -> None:
    """Grandparent partials/finals/typed text -> glance events; each key once per call; pictures follow in the background."""
    if side.role != "grandparent" or not text.strip():
        return
    try:
        peer = cs.peer(side.role)
        listener = peer.person if peer else cs._default_listener(side)
        # matcher ≈0.3 ms but the family linker ≈10-17 ms on a 27-word line: keep it off the event loop
        found = await asyncio.to_thread(lambda: engine_for(cs.translator, refresh=final).items(text, side.person, listener))
    except Exception as e:  # noqa: BLE001  (cards are decoration; the call must go on)
        log.warning("glance failed: %s", e)
        return
    new = [(it, wt) for it, wt in found if it["key"] not in cs.glance_sent]
    if not new:
        return
    cs.glance_sent = cs.glance_sent | {it["key"] for it, _ in new}
    await cs._broadcast({"type": "glance", "role": side.role, "items": [it for it, _ in new]})
    pics = get_pictures()
    for it, wt in new:
        if wt and not it["image_url"] and pics.needs_fetch(wt):
            task = asyncio.create_task(_image_followup(cs, it, wt))
            cs.glance_tasks.add(task)
            task.add_done_callback(cs.glance_tasks.discard)


async def _image_followup(cs: "CallSession", item: dict, title: str) -> None:
    try:
        rec = await asyncio.to_thread(get_pictures().fetch, title)
    except Exception as e:  # noqa: BLE001
        log.info("picture fetch failed for %r: %s", title, e)
        return
    if not rec:
        return
    msg = {"type": "glance_image", "key": item["key"], "image_url": rec["image_url"], "image_credit": rec.get("image_credit", ""),
           "source_url": rec.get("source_url", "")}
    if not item.get("body") and rec.get("extract"):
        msg["body"] = rec["extract"]
    await cs._broadcast(msg)
