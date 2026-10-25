"""Fact visibility and disclosure, one definition (ARCHITECTURE 1.3). Pure, no DB."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

IDENTITY = frozenset({"tie", "lives_in", "from", "works_at", "studies_at"})


@dataclass(frozen=True)
class FactV:
    id: int
    subject_id: int
    speaker_id: int | None
    predicate: str
    text: str
    keys: tuple[tuple[str, ...], ...]
    status: str
    sensitive_kind: str
    remembered: bool
    shareable: bool
    third_party: bool
    expires_at: datetime | None
    pinned: bool
    storyline_id: int | None
    said_at: datetime
    refs: frozenset[tuple[str, int]]  # {("person", 17), ("thing", 4)}


def expired(f: FactV, now: datetime) -> bool:
    return f.expires_at is not None and not f.pinned and f.expires_at <= now


def content_ok(f: FactV) -> bool:
    return f.sensitive_kind == "" or f.remembered


def fact_visible(f: FactV, audience: frozenset[int], viewer: int, now: datetime) -> bool:
    return viewer in audience and not expired(f, now)


def disclosable(f: FactV, speaker: int, mentioned: frozenset[int], now: datetime) -> bool:
    if f.speaker_id != speaker or not f.shareable or not content_ok(f) or expired(f, now) or f.status != "active":
        return False
    if f.storyline_id is not None and f.subject_id == speaker:  # owner raising their own storyline
        return True
    return f.predicate in IDENTITY and (f.subject_id == speaker or f.subject_id in mentioned)


def usable(f: FactV, audience: frozenset[int], viewer: int, speaker: int | None,
           mentioned: frozenset[int], now: datetime) -> bool:
    """What a card body may cite."""
    return content_ok(f) and (
        fact_visible(f, audience, viewer, now) or (speaker is not None and disclosable(f, speaker, mentioned, now))
    )


def bridge_candidate(f: FactV, audience: frozenset[int], listener: int, other: int, now: datetime) -> bool:
    return (f.subject_id == listener and f.speaker_id == listener and f.status == "active" and content_ok(f)
            and not expired(f, now) and other not in audience)
