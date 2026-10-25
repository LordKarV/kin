"""Mastery bookkeeping: exposures (weak), verifications (strong), the passthrough policy."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import select

from ..db import models as m
from ..db.session import session_scope
from ..mt.translate import get_translator
from .bkt import BKT, DEFAULT, MASTERY_THRESHOLD
from .lemmas import heritage_lemmas, lemma

bkt = BKT()


def _learner_id(s, slug: str, family_id: int | None = None) -> int:
    q = select(m.Person).where(m.Person.slug == slug)
    if family_id is not None:  # slugs are only unique per family
        q = q.where(m.Person.family_id == family_id)
    p = s.scalars(q).first()
    if p is None:
        raise ValueError(f"unknown learner {slug}")
    return p.id


def _row(s, learner_id: int, lm: str) -> m.Mastery:
    r = s.scalar(select(m.Mastery).where(m.Mastery.learner_id == learner_id, m.Mastery.lemma == lm))
    if r is None:
        r = m.Mastery(learner_id=learner_id, lemma=lm, p_known=DEFAULT.p_init)
        s.add(r); s.flush()
    return r


def _lang_of(s, learner: str, family_id: int | None = None) -> str:
    fam = s.get(m.Family, family_id) if family_id is not None else None
    if fam is None:
        p = s.scalar(select(m.Person).where(m.Person.slug == learner))
        fam = s.get(m.Family, p.family_id) if p else None
    return fam.heritage_lang if fam else "ta"


def record_exposures(learner: str, text: str, lang: str | None = None, family_id: int | None = None) -> list[str]:
    with session_scope() as s:
        lang = lang or _lang_of(s, learner, family_id)
    lms = heritage_lemmas(text, lang)
    with session_scope() as s:
        lid = _learner_id(s, learner, family_id)
        for lm in lms:
            r = _row(s, lid, lm)
            r.p_known = bkt.expose(r.p_known); r.n_exposures += 1
    return lms


def _utterance(s, utterance_id: int, family_id: int | None) -> m.Utterance | None:
    """With a family, only an utterance of a legacy call in that family: a world transcript never reaches Fade."""
    u = s.get(m.Utterance, utterance_id)
    if u is None or family_id is None:
        return u
    call = s.get(m.Call, u.call_id)
    return u if call is not None and call.family_id == family_id and call.mode != "world" else None


def record_verification(data: dict, family_id: int | None = None) -> dict:
    """{"learner","understood", "text" | "utterance_id"} → updates every heritage lemma in the text as one observation.
    `family_id` scopes the learner slug and the utterance to one legacy family (the REST and /ws/call callers)."""
    learner = data.get("learner") or "p_arjun"
    understood = bool(data.get("understood", True))
    text = data.get("text", "")
    with session_scope() as s:
        lid = lang = None
        if not text and data.get("utterance_id"):
            u = _utterance(s, int(data["utterance_id"]), family_id)
            text = u.src_text if u else ""
            if u and u.listener_id:  # use the listener row itself: slugs are only unique per family
                p = s.get(m.Person, u.listener_id)
                learner, lid = p.slug, p.id
                fam = s.get(m.Family, p.family_id)
                lang = fam.heritage_lang if fam else None
        lms = heritage_lemmas(text, lang or _lang_of(s, learner, family_id))
        lid = lid or _learner_id(s, learner, family_id)
        for lm in lms:
            r = _row(s, lid, lm)
            r.p_known = bkt.update(r.p_known, correct=understood); r.n_verified += 1
    return {"type": "verified", "learner": learner, "understood": understood, "lemmas": lms}


def mastery(learner: str, family_id: int | None = None) -> list[dict]:
    with session_scope() as s:
        lid = _learner_id(s, learner, family_id)
        rows = s.scalars(select(m.Mastery).where(m.Mastery.learner_id == lid).order_by(m.Mastery.p_known.desc())).all()
        return [{"lemma": r.lemma, "p_known": round(r.p_known, 4), "n_exposures": r.n_exposures, "n_verified": r.n_verified,
                 "mastered": r.p_known >= MASTERY_THRESHOLD, "updated_at": r.updated_at.isoformat() if r.updated_at else None} for r in rows]


def reset(learner: str, family_id: int | None = None) -> int:
    with session_scope() as s:
        lid = _learner_id(s, learner, family_id)
        rows = s.scalars(select(m.Mastery).where(m.Mastery.learner_id == lid)).all()
        for r in rows:
            s.delete(r)
        return len(rows)


def passthrough_tokens(learner: str, text: str, family_id: int | None = None, known: set[str] | None = None) -> list[str]:
    """Tokens of `text` whose lemma is mastered, excluding anything inside a grounded entity span (hard guardrail).
    `known` overrides the DB (used by the simulation so it never touches the learner's real rows)."""
    if known is None:
        with session_scope() as s:
            lid = _learner_id(s, learner, family_id)
            known = {r.lemma for r in s.scalars(select(m.Mastery).where(m.Mastery.learner_id == lid, m.Mastery.p_known >= MASTERY_THRESHOLD))}
    if not known:
        return []
    tr = get_translator(family_id) if family_id else None
    lang = tr.g.heritage_lang if tr is not None else "ta"
    protected: list[tuple[int, int]] = []
    if tr is not None:
        g = tr.g
        speaker = next((p.slug for p in g.people.values() if not p.is_learner), learner)
        protected = [(sp.start, sp.end) for sp in tr.linker.link(text, speaker, learner) if sp.node or sp.type == "kin"]
    out: list[str] = []
    for mt in re.finditer(r"\S+", text):
        tok = mt.group(0).strip("\"'“”‘’()[]{},;:!?।.")
        if not tok or lemma(tok, lang) not in known:
            continue
        if any(a <= mt.start() < b or a < mt.end() <= b for a, b in protected):
            continue
        if tok not in out:
            out.append(tok)
    return out
