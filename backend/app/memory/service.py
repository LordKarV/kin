"""Memory across calls (Phase 6): post-call summary, structured extraction with the plan §9 privacy rule
(health/money/conflict stored as topic word only unless the grandchild taps "remember this"), approval → graph upserts,
and fuzzy memory search over utterances + summaries (no embeddings: Meta Model API has no embeddings endpoint)."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel
from rapidfuzz import fuzz
from sqlalchemy import select

from ..db import models as m
from ..db.session import session_scope
from ..llm import get_llm
from ..mt.translate import get_translator, reset_translator_cache

SENSITIVE_KINDS = {"health", "money", "conflict"}


class XPerson(BaseModel):
    name: str
    how_referred: str
    inferred_relation: str
    sensitive: bool


class XThing(BaseModel):
    name: str
    note: str
    sensitive: bool


class XEvent(BaseModel):
    name: str
    when: str
    sensitive: bool


class XTopic(BaseModel):
    topic: str
    kind: Literal["health", "money", "conflict", "other"]
    sensitive: bool
    detail: str
    lines: list[int]   # 1-based transcript line numbers where this topic was discussed


class ExtractionOut(BaseModel):
    people: list[XPerson]
    dishes: list[XThing]
    places: list[XThing]
    events: list[XEvent]
    topics: list[XTopic]


SUMMARY_SYS = ("Summarize this family call in 2-4 plain sentences for the grandchild's memory: what the grandparent said, plans, requests. "
               "Name people as the family does. No advice. Privacy rule: for health, money or conflict, mention only the topic word "
               "(e.g. 'talked about her knee'), never the details.")
EXTRACT_SYS = ("From this numbered transcript, extract new people (with how the speaker refers to them and inferred relation), dishes, places, events, "
               "and topics. Return JSON. Mark anything about health, money, or conflict as sensitive: true, do not include details beyond the topic word, "
               "and list the transcript line numbers (`lines`) where each topic was discussed.")


def _transcript_text(s, call_id: int) -> tuple[str, list[m.Utterance]]:
    utts = s.scalars(select(m.Utterance).where(m.Utterance.call_id == call_id).order_by(m.Utterance.id)).all()
    people = {p.id: p.display_name for p in s.scalars(select(m.Person))}
    lines = [f"{i}. {people.get(u.speaker_id, '?')}: {u.src_text}" + (f"  → {u.translation}" if u.translation else "") for i, u in enumerate(utts, 1)]
    return "\n".join(lines), utts


def _reduce_sensitive(x: ExtractionOut) -> dict:
    d = x.model_dump()
    for t in d["topics"]:
        if t["sensitive"] or t["kind"] in SENSITIVE_KINDS:
            t["sensitive"] = True
            t.pop("detail", None)  # topic word only (plan §9)
        else:
            t.pop("lines", None)
    for key in ("people", "dishes", "places"):
        d[key] = [i for i in d[key] if not i["sensitive"]]
    d["events"] = [i for i in d["events"] if not i["sensitive"]]
    return d


def end_call(call_id: int) -> dict:
    with session_scope() as s:
        call = s.get(m.Call, call_id)
        if call is None:
            raise ValueError("call not found")
        text, utts = _transcript_text(s, call_id)
        call.ended_at = datetime.now(timezone.utc)
        summary, extracted, err = "", {}, None
        if text.strip():
            llm = get_llm()
            try:
                summary = llm.text(SUMMARY_SYS, text, reasoning_effort="medium").strip()
            except Exception as e:  # noqa: BLE001
                err = f"summary: {e}"
            try:
                extracted = _reduce_sensitive(llm.structured(ExtractionOut, EXTRACT_SYS, text, reasoning_effort="medium", max_completion_tokens=4000))
                # tag the utterances that carried a sensitive topic: their text is withheld from memory until remembered
                for t in extracted.get("topics", []):
                    if t.get("sensitive"):
                        for ln in t.get("lines", []):
                            if 1 <= ln <= len(utts) and not utts[ln - 1].sensitive_topic:
                                utts[ln - 1].sensitive_topic = t["topic"]
            except Exception as e:  # noqa: BLE001
                err = (err + "; " if err else "") + f"extraction: {e}"
        cs = s.scalar(select(m.CallSummary).where(m.CallSummary.call_id == call_id))
        if cs is None:
            cs = m.CallSummary(call_id=call_id, summary=summary, extracted=extracted, approved=False)
            s.add(cs)
        else:
            cs.summary, cs.extracted, cs.approved = summary, extracted, False
        s.flush()
        return {"call_id": call_id, "summary": summary, "extracted": extracted, "approved": False, "n_utterances": len(utts), "error": err}


def _slug(prefix: str, name: str) -> str:
    base = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    base = re.sub(r"[^a-z0-9]+", "_", base).strip("_") or "x"
    return f"{prefix}_{base}"


def approve_call(call_id: int, remember_topics: list[str]) -> dict:
    added_things: list[str] = []
    added_people: list[str] = []
    with session_scope() as s:
        cs = s.scalar(select(m.CallSummary).where(m.CallSummary.call_id == call_id))
        call = s.get(m.Call, call_id)
        if cs is None or call is None:
            raise ValueError("call has no summary yet; call /end first")
        fid = call.family_id
        g = get_translator(fid)
        x = cs.extracted or {}
        existing = {t.slug for t in s.scalars(select(m.Thing).where(m.Thing.family_id == fid))}
        for kind, prefix, key in (("dish", "d", "dishes"), ("place", "pl", "places"), ("event", "ev", "events")):
            for item in x.get(key, []):
                name = item["name"].strip()
                if not name or g.linker.link(name, "p_kamala", "p_arjun"):  # already known to the family graph
                    continue
                slug = _slug(prefix, name)
                if slug in existing:
                    continue
                s.add(m.Thing(family_id=fid, slug=slug, kind=kind, name=name, lang_name="", aliases=[name], note=item.get("note") or item.get("when", "")))
                existing.add(slug); added_things.append(slug)
        for person in x.get("people", []):
            name = person["name"].strip()
            if not name or g.linker.link(name, "p_kamala", "p_arjun"):
                continue
            slug = _slug("p", name)
            if s.scalar(select(m.Person).where(m.Person.family_id == fid, m.Person.slug == slug)):
                continue
            p = m.Person(family_id=fid, slug=slug, display_name=name, notes=f"Mentioned as '{person['how_referred']}'; {person['inferred_relation']} (unverified, from call {call_id})")
            p.aliases = [m.Alias(alias=name, lang="en", kind="name"), m.Alias(alias=person["how_referred"], lang="ta", kind="address")]
            s.add(p); added_people.append(slug)
        remembered = [t for t in remember_topics if any(tp["topic"] == t for tp in x.get("topics", []))]
        cs.extracted = {**x, "remembered": remembered}
        cs.approved = True
        s.flush()
    if added_things or added_people:
        reset_translator_cache()
    return {"call_id": call_id, "approved": True, "added_things": added_things, "added_people": added_people, "remembered_topics": remembered}


def remembered_by_call(s, call_ids: list[int]) -> dict[int, set[str]]:
    out: dict[int, set[str]] = {}
    for cs in s.scalars(select(m.CallSummary).where(m.CallSummary.call_id.in_(call_ids))) if call_ids else []:
        out[cs.call_id] = set((cs.extracted or {}).get("remembered", []))
    return out


def withheld(u: m.Utterance, remembered: dict[int, set[str]]) -> bool:
    return bool(u.sensitive_topic) and u.sensitive_topic not in remembered.get(u.call_id, set())


def search(q: str, family_id: int, limit: int = 8) -> list[dict]:
    ql = q.lower().strip()
    if not ql:
        return []
    out: list[dict] = []
    with session_scope() as s:
        people = {p.id: p.display_name for p in s.scalars(select(m.Person).where(m.Person.family_id == family_id))}
        calls = {c.id: c for c in s.scalars(select(m.Call).where(m.Call.family_id == family_id))}
        rem = remembered_by_call(s, list(calls))
        for u in s.scalars(select(m.Utterance).where(m.Utterance.call_id.in_(list(calls)))) if calls else []:
            if withheld(u, rem):
                continue  # plan §9: sensitive detail stays out of memory unless the grandchild chose to remember it
            text = f"{u.src_text} {u.translation}".strip()
            sc = max(fuzz.partial_ratio(ql, text.lower()), 100 if ql in text.lower() else 0)
            if sc >= 70:
                out.append({"kind": "utterance", "text": text, "translation": u.translation, "speaker": people.get(u.speaker_id), "call_id": u.call_id,
                            "when": u.created_at.isoformat() if u.created_at else None, "score": sc})
        for cs in s.scalars(select(m.CallSummary).where(m.CallSummary.call_id.in_(list(calls)))) if calls else []:
            blob = cs.summary + " " + " ".join(t.get("topic", "") for t in (cs.extracted or {}).get("topics", []))
            sc = max(fuzz.partial_ratio(ql, blob.lower()), 100 if ql in blob.lower() else 0)
            if sc >= 70:
                c = calls.get(cs.call_id)
                out.append({"kind": "summary", "text": cs.summary, "translation": "", "speaker": None, "call_id": cs.call_id,
                            "when": (c.ended_at or c.started_at).isoformat() if c and (c.ended_at or c.started_at) else None, "score": sc,
                            "remembered_topics": (cs.extracted or {}).get("remembered", [])})
    out.sort(key=lambda h: (-h["score"], h["when"] or ""))
    return out[:limit]
