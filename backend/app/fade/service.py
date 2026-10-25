"""Mastery bookkeeping: exposures (weak), verifications (strong), the passthrough policy, and the demo simulation."""
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


def _lang_of(s, learner: str) -> str:
    p = s.scalar(select(m.Person).where(m.Person.slug == learner))
    fam = s.get(m.Family, p.family_id) if p else None
    return fam.heritage_lang if fam else "ta"


def record_exposures(learner: str, text: str, lang: str | None = None) -> list[str]:
    with session_scope() as s:
        lang = lang or _lang_of(s, learner)
    lms = heritage_lemmas(text, lang)
    with session_scope() as s:
        lid = _learner_id(s, learner)
        for lm in lms:
            r = _row(s, lid, lm)
            r.p_known = bkt.expose(r.p_known); r.n_exposures += 1
    return lms


def record_verification(data: dict) -> dict:
    """{"learner","understood", "text" | "utterance_id"} → updates every heritage lemma in the text as one observation."""
    learner = data.get("learner") or "p_arjun"
    understood = bool(data.get("understood", True))
    text = data.get("text", "")
    with session_scope() as s:
        lid = lang = None
        if not text and data.get("utterance_id"):
            u = s.get(m.Utterance, int(data["utterance_id"]))
            text = u.src_text if u else ""
            if u and u.listener_id:  # use the listener row itself: slugs are only unique per family
                p = s.get(m.Person, u.listener_id)
                learner, lid = p.slug, p.id
                fam = s.get(m.Family, p.family_id)
                lang = fam.heritage_lang if fam else None
        lms = heritage_lemmas(text, lang or _lang_of(s, learner))
        lid = lid or _learner_id(s, learner)
        for lm in lms:
            r = _row(s, lid, lm)
            r.p_known = bkt.update(r.p_known, correct=understood); r.n_verified += 1
    return {"type": "verified", "learner": learner, "understood": understood, "lemmas": lms}


def mastery(learner: str) -> list[dict]:
    with session_scope() as s:
        lid = _learner_id(s, learner)
        rows = s.scalars(select(m.Mastery).where(m.Mastery.learner_id == lid).order_by(m.Mastery.p_known.desc())).all()
        return [{"lemma": r.lemma, "p_known": round(r.p_known, 4), "n_exposures": r.n_exposures, "n_verified": r.n_verified,
                 "mastered": r.p_known >= MASTERY_THRESHOLD, "updated_at": r.updated_at.isoformat() if r.updated_at else None} for r in rows]


def reset(learner: str) -> int:
    with session_scope() as s:
        lid = _learner_id(s, learner)
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


# ---- demo simulation ----------------------------------------------------------
# A fixed, documented history: words Paatti uses on every call. Week w exposes each word `per_week` times and
# verifies it once per week from week 2 (the grandchild starts answering without asking for a repeat).
DEMO_VOCAB = ["நேத்து", "இன்னைக்கு", "நல்லா", "ரொம்ப", "சாப்பிட்டியா", "எப்போ", "போன்", "பண்ணான்", "வர்ற", "வெயில்", "மழை", "தூங்கு", "படி", "சந்தோஷம்", "கவனமா"]
DEMO_SENTENCE = "இன்னைக்கு ரொம்ப வெயில், நீ நல்லா சாப்பிட்டியா? உன் மாமா நேத்து போன் பண்ணான், எப்போ வர்ற?"


def simulate(learner: str, weeks: int, per_week: int = 3, family_id: int | None = None) -> dict:
    """Replay `weeks` of recorded-style exposures/verifications through the REAL BKT, in memory, from a clean slate.
    Never writes the learner's real mastery rows. Returns per-word trajectories (week 0..weeks), the resulting
    mastery table, and what the fixed demo sentence would pass through."""
    weeks = max(0, min(12, int(weeks)))
    vocab = [(w, lemma(w)) for w in DEMO_VOCAB]
    state = {lm: {"p": DEFAULT.p_init, "exp": 0, "ver": 0} for _w, lm in vocab}
    traj: dict[str, list[float]] = {lm: [DEFAULT.p_init] for _w, lm in vocab}
    pace = {lm: 1.0 - 0.06 * i for i, (_w, lm) in enumerate(vocab)}  # greetings first, so curves are staggered
    for wk in range(1, weeks + 1):
        for _w, lm in vocab:
            st = state[lm]
            for _ in range(max(1, round(per_week * pace[lm]))):
                st["p"] = bkt.expose(st["p"]); st["exp"] += 1
            if wk >= 2 and (wk * pace[lm]) >= 1.5:
                st["p"] = bkt.update(st["p"], correct=True); st["ver"] += 1
            traj[lm].append(round(st["p"], 4))
    known = {lm for lm, st in state.items() if st["p"] >= MASTERY_THRESHOLD}
    pt = passthrough_tokens(learner, DEMO_SENTENCE, family_id, known=known)
    return {"learner": learner, "weeks": weeks, "simulated": True, "sentence": DEMO_SENTENCE, "passthrough": pt,
            "trajectories": [{"lemma": lm, "lemma_surface": w, "curve": traj[lm], "mastered": lm in known} for w, lm in vocab],
            "mastery": [{"lemma": lm, "surface": w, "p_known": round(state[lm]["p"], 4), "n_exposures": state[lm]["exp"], "n_verified": state[lm]["ver"], "mastered": lm in known} for w, lm in vocab],
            "note": "Simulation of accumulated history: a documented exposure pattern replayed through the real BKT in memory. Your real mastery is untouched.",
            "at": datetime.now(timezone.utc).isoformat()}
