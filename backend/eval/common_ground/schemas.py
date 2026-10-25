"""Planted common-ground scenarios: who knows what, when, and which cards each listener should get.

Days are offsets from the scenario's day 0 (fractions allowed, e.g. 41.9995 for "a minute before the probe").
Evidence rows are applied in list order (the runner relies on this: `shown` before `heard` on the same final).
`heard_by` on ties and groups is only the FactAudience of that tie/group fact. It never writes knowledge rows:
all knowledge (kcache) comes from `evidence`, so the runner must not turn heard_by into `heard` evidence.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_PATH = Path(__file__).resolve().parent / "scenarios.jsonl"
KIN_PATH = re.compile(r"^[a-z_]+(\.[a-z_]+)*$")   # builder.STEPS grammar, e.g. "mother.mother"


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")   # a typo in the data is an error, not a silently ignored field


class PersonS(_M):
    key: str
    name: str
    lang: str = ""
    user: bool
    forms: list[str] = Field(default_factory=list)


class GroupS(_M):        # "Westwood crew"; membership is stated in a call like a tie
    key: str
    name: str
    forms: list[str] = Field(default_factory=list)
    members: list[str]
    day: float
    said_by: str
    heard_by: list[str] = Field(default_factory=list)   # FactAudience of the group fact only; never knowledge


class TieS(_M):          # "b is a's <kind>"; a fact with subject a, speaker said_by
    a: str
    b: str
    kind: str
    context: str = ""
    day: float
    said_by: str
    heard_by: list[str] = Field(default_factory=list)   # FactAudience of the tie fact only; never knowledge


class EdgeS(_M):         # kin placement: b is a's <path>
    a: str
    b: str
    path: str
    day: float
    said_by: str


class StorylineRef(_M):
    title: str
    state: str


class FactS(_M):
    key: str
    subject: str
    speaker: str
    predicate: str
    text: str
    keys: list[list[str]] = Field(default_factory=list)
    day: float
    source: Literal["call", "sms"]
    audience: list[str] = Field(default_factory=list)
    told: list[str] = Field(default_factory=list)
    sensitive_kind: Literal["", "health", "money", "conflict"] = ""
    remembered: bool = False
    pinned: bool = False
    third_party: bool = False
    contradicts: str | None = None      # key of an earlier fact this one contradicts
    storyline: StorylineRef | None = None


class ItemRef(_M):
    # person/group: a people or groups key; fact/state: a fact key (state = that fact's storyline state);
    # bridge: a fact key, meaning a bridge card for it was already logged (card_log) toward `target`
    kind: Literal["person", "group", "fact", "state", "bridge"]
    key: str


class EvidenceS(_M):
    knower: str
    item: ItemRef
    ev: Literal["heard", "shown", "said", "authored", "confirmed", "asked"]
    day: float
    target: str | None = None           # bridge items only: the person who had not heard it


class ProbeS(_M):
    day: float
    participants: list[str]
    speaker: str
    text: str
    partials: list[str] = Field(default_factory=list)
    translations: dict[str, str] = Field(default_factory=dict)


class CardE(_M):
    # who/what: key = people/groups key, gap required. bridge: fact key about the listener. storyline: storyline title.
    # ask: the ambiguous or unknown surface term as it appears in probe.text. term: lexicon key.
    kind: Literal["who", "what", "ask", "bridge", "storyline", "term"]
    key: str
    gap: Literal["new", "reminder"] | None = None
    cites: list[str] = Field(default_factory=list)          # fact keys the card body must cite
    must_not_cite: list[str] = Field(default_factory=list)  # fact keys it must never cite (leak traps)


class ExpectS(_M):
    cards: list[CardE] = Field(default_factory=list)


class Scenario(_M):
    id: str
    tags: list[str]
    people: list[PersonS]
    groups: list[GroupS] = Field(default_factory=list)
    ties: list[TieS] = Field(default_factory=list)
    edges: list[EdgeS] = Field(default_factory=list)
    facts: list[FactS] = Field(default_factory=list)
    evidence: list[EvidenceS] = Field(default_factory=list)
    probe: ProbeS
    expect: dict[str, ExpectS]

    @model_validator(mode="after")
    def _refs(self) -> "Scenario":
        people = {p.key: p for p in self.people}
        groups = {g.key for g in self.groups}
        facts = {f.key: f for f in self.facts}
        _unique("people/group", [p.key for p in self.people] + [g.key for g in self.groups])
        _unique("fact", [f.key for f in self.facts])
        story_titles = {f.storyline.title for f in self.facts if f.storyline}

        def person(k: str, where: str) -> None:
            if k not in people:
                raise ValueError(f"{where}: unknown person {k!r}")

        for g in self.groups:
            for k in [g.said_by, *g.members, *g.heard_by]:
                person(k, f"group {g.key}")
        for t in self.ties:
            for k in [t.a, t.b, t.said_by, *t.heard_by]:
                person(k, f"tie {t.a}-{t.b}")
        for e in self.edges:
            for k in (e.a, e.b, e.said_by):
                person(k, f"edge {e.a}-{e.b}")
            if not KIN_PATH.match(e.path):
                raise ValueError(f"edge {e.a}-{e.b}: bad kin path {e.path!r}")
        for f in self.facts:
            for k in [f.subject, f.speaker, *f.audience, *f.told]:
                person(k, f"fact {f.key}")
            if f.contradicts is not None and f.contradicts not in facts:
                raise ValueError(f"fact {f.key}: contradicts unknown fact {f.contradicts!r}")
        for ev in self.evidence:
            person(ev.knower, "evidence")
            _item_exists(ev.item, people, groups, facts)
            if ev.item.kind == "bridge":
                # Only the fact's own subject and speaker can have been shown its bridge, and only toward someone
                # who had not heard it (told may grow later, when the listener passes it on).
                f = facts[ev.item.key]
                if not (f.subject == f.speaker == ev.knower) or ev.target in f.audience:
                    raise ValueError(f"evidence bridge {ev.item.key}: impossible card_log row")
            if (ev.item.kind == "bridge") != (ev.target is not None):
                raise ValueError(f"evidence {ev.item.key}: target is required for bridge items and only for them")
            if ev.target is not None:
                person(ev.target, "evidence target")
            if ev.day > self.probe.day:
                raise ValueError(f"evidence {ev.item.key} on day {ev.day} is after the probe")
        for x in [*self.ties, *self.edges, *self.facts, *self.groups]:
            if x.day > self.probe.day:
                raise ValueError(f"{type(x).__name__} on day {x.day} is after the probe")

        pr = self.probe
        for k in pr.participants:
            person(k, "probe")
            if not people[k].user:
                raise ValueError(f"probe participant {k!r} is not a user")
        if not all(pr.text.startswith(x) for x in pr.partials):
            raise ValueError("every partial must be a prefix of probe.text")
        if pr.speaker not in pr.participants:
            raise ValueError(f"probe speaker {pr.speaker!r} is not a participant")
        if set(self.expect) != set(pr.participants):
            raise ValueError(f"expect must name exactly the participants: {sorted(self.expect)} vs {sorted(pr.participants)}")
        if self.expect[pr.speaker].cards:
            raise ValueError("the speaker never gets cards about their own words")
        for listener, ex in self.expect.items():
            for c in ex.cards:
                _card_ok(c, listener, people, groups, facts, story_titles, pr.text)
                if c.kind in ("who", "what") and c.key in pr.participants:
                    raise ValueError(f"expect[{listener}] {c.kind}:{c.key}: participants are structural, never a gap")
        return self


def _unique(what: str, keys: list[str]) -> None:
    dup = {k for k in keys if keys.count(k) > 1}
    if dup:
        raise ValueError(f"duplicate {what} keys: {sorted(dup)}")


def _item_exists(item: ItemRef, people, groups, facts) -> None:
    ok = {"person": item.key in people, "group": item.key in groups, "fact": item.key in facts,
          "bridge": item.key in facts,
          "state": item.key in facts and facts[item.key].storyline is not None}[item.kind]
    if not ok:
        raise ValueError(f"evidence item {item.kind}:{item.key} does not exist")


def _card_ok(c: CardE, listener: str, people, groups, facts, story_titles, text: str) -> None:
    where = f"expect[{listener}] {c.kind}:{c.key}"
    if c.kind in ("who", "what"):
        if c.key not in people and c.key not in groups:
            raise ValueError(f"{where}: unknown entity")
        if c.gap is None:
            raise ValueError(f"{where}: who/what cards need a gap")
    elif c.gap is not None:
        raise ValueError(f"{where}: only who/what cards carry a gap")
    if c.kind == "bridge":
        f = facts.get(c.key)
        if f is None or f.subject != listener or f.speaker != listener:
            raise ValueError(f"{where}: a bridge must name a fact about the listener, said by the listener")
    if c.kind == "storyline" and c.key not in story_titles:
        raise ValueError(f"{where}: unknown storyline")
    if c.kind == "ask" and c.key.casefold() not in text.casefold():
        raise ValueError(f"{where}: ask term is not in the probe text")
    for k in [*c.cites, *c.must_not_cite]:
        if k not in facts:
            raise ValueError(f"{where}: cites unknown fact {k!r}")


def load_scenarios(path: str | Path | None = None) -> list[Scenario]:
    """Load and validate every scenario. Raises ValueError (pydantic.ValidationError) on the first bad line."""
    p = Path(path) if path else DEFAULT_PATH
    rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    out = [Scenario.model_validate(r) for r in rows]
    _unique("scenario", [s.id for s in out])
    return out
