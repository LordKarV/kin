"""WorldView: an immutable per-call snapshot of the world graph (docs/ARCHITECTURE.md section 2).

Built in a worker thread at join/leave/refresh; every read here is pure Python over the snapshot. All rendering is
listener-relative and walks only hops the listener may see (or the current speaker may disclose, section 1.3).
"""
from __future__ import annotations

import heapq
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Callable, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import models as m
from ..graph.kinship import FamilyGraph
from .visibility import IDENTITY, FactV, disclosable, expired, fact_visible, usable


@dataclass(frozen=True)
class PersonV:
    id: int
    slug: str
    name: str
    lang_name: str
    is_user: bool
    lang: str
    aliases: tuple[tuple[str, str], ...]  # (form, lang)


@dataclass(frozen=True)
class ThingV:
    id: int
    slug: str
    kind: str
    name: str
    owner_id: int | None
    keys: tuple[tuple[str, ...], ...]
    aliases: tuple[str, ...]  # includes lang_name


@dataclass(frozen=True)
class GroupV:
    id: int
    slug: str
    name: str
    members: frozenset[int]


@dataclass(frozen=True)
class Hop:
    to: int
    kind: str  # kin|tie|group
    label: str
    context: str
    fact_id: int | None


@dataclass(frozen=True)
class StoryV:
    id: int
    slug: str
    owner_id: int
    title: str
    keys: tuple
    status: str
    unresolved: bool
    states: tuple[tuple[int, str, datetime, int, str], ...]  # (state_id, label, at, fact_id, status) by seq


TIE_LABEL = {"close_friend": "close friend", "knows": "acquaintance"}
HOP_COST = {"kin": 1.0, "tie": 1.0, "group": 1.5}
MAX_KIN_DEPTH = 4      # rule 2, in FamilyGraph steps
MAX_BFS_HOPS = 3       # rule 5
ROSTER_CAP = 40
CARD_FACTS = 2

HopOk = Callable[[int, Hop], bool]
Key = tuple[str, int]


def _day(d: datetime) -> str:
    return f"{d:%b} {d.day}"


def _ctx(h: Hop) -> str:
    return f" ({h.context})" if h.context else ""


def _two_hops(adj: dict[int, list | tuple], start: Iterable[int]) -> set[int]:
    ring1 = {h.to if isinstance(h, Hop) else h for x in start for h in adj.get(x, ())}
    return ring1 | {h.to if isinstance(h, Hop) else h for x in ring1 for h in adj.get(x, ())}


@dataclass(frozen=True)
class WorldView:
    space_id: int
    members: frozenset[int]
    kin: FamilyGraph
    people: dict[int, PersonV]
    things: dict[int, ThingV]
    groups: dict[int, GroupV]
    adj: dict[int, tuple[Hop, ...]]
    facts: dict[int, FactV]
    audience: dict[int, frozenset[int]]
    storylines: dict[int, StoryV]
    first_mention: dict[int, datetime]
    # Indexes beyond 2.1, defaulted so a fake built from the 2.1 fields alone still constructs.
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))  # clock for visible()/render()
    # entity -> (link fact, endpoints)
    links: dict[Key, tuple[tuple[int | None, frozenset[int]], ...]] = field(default_factory=dict)
    about: dict[Key, tuple[int, ...]] = field(default_factory=dict)  # entity -> facts with it as subject or ref
    # group hop -> both memberships
    gpair: dict[tuple[int, int, str], tuple[tuple[int | None, int], ...]] = field(default_factory=dict)
    first_known: dict[tuple[int, str, int], datetime] = field(default_factory=dict)  # (knower, kind, id) -> first_at
    group_forms: dict[int, tuple[str, ...]] = field(default_factory=dict)

    # ---- build ------------------------------------------------------------------------------------------------------
    @classmethod
    def build(cls, s: Session, space_id: int, members: Iterable[int], now: datetime) -> "WorldView":
        members = frozenset(members)
        users = dict(s.execute(select(m.User.person_id, m.User.lang).join(m.Person, m.Person.id == m.User.person_id)
                               .where(m.Person.family_id == space_id)).all())
        ties = s.scalars(select(m.Tie).where(m.Tie.family_id == space_id, m.Tie.status == "active")).all()
        edges = s.scalars(select(m.Edge).where(m.Edge.family_id == space_id)).all()
        gms = s.execute(select(m.GroupMember.group_id, m.GroupMember.person_id, m.GroupMember.fact_id)
                        .join(m.Group, m.Group.id == m.GroupMember.group_id).where(m.Group.family_id == space_id)).all()
        by_group: dict[int, dict[int, int | None]] = defaultdict(dict)
        for gid, pid, fid in gms:
            by_group[gid][pid] = fid
        nb: dict[int, set[int]] = defaultdict(set)
        for a, b in [(t.src_person, t.dst_person) for t in ties] + [(e.src_person, e.dst_person) for e in edges]:
            nb[a].add(b)
            nb[b].add(a)
        for mem in by_group.values():
            for p in mem:  # ponytail: O(members^2) per group; fine for friend groups, index by group if they get big
                nb[p] |= mem.keys() - {p}

        # Facts a member heard or said: every fact any listener here could see or the speaker could disclose.
        fids = set(s.scalars(select(m.FactAudience.fact_id).join(m.Fact, m.Fact.id == m.FactAudience.fact_id)
                             .where(m.Fact.family_id == space_id, m.FactAudience.person_id.in_(members))))
        fids |= set(s.scalars(select(m.Fact.id).where(m.Fact.family_id == space_id, m.Fact.speaker_id.in_(members))))
        aud: dict[int, set[int]] = defaultdict(set)
        refs: dict[int, set[tuple[str, int]]] = defaultdict(set)
        for fid, pid in s.execute(select(m.FactAudience.fact_id, m.FactAudience.person_id)
                                  .where(m.FactAudience.fact_id.in_(fids))):
            aud[fid].add(pid)
        for fid, kind, rid in s.execute(select(m.FactRef.fact_id, m.FactRef.kind, m.FactRef.ref_id)
                                        .where(m.FactRef.fact_id.in_(fids))):
            refs[fid].add((kind, rid))
        facts = {f.id: FactV(f.id, f.subject_id, f.speaker_id, f.predicate, f.text,
                             tuple(tuple(g) for g in (f.keys or [])), f.status, f.sensitive_kind, f.remembered,
                             f.shareable, f.third_party, f.expires_at, f.pinned, f.storyline_id, f.said_at,
                             frozenset(refs[f.id]))
                 for f in s.scalars(select(m.Fact).where(m.Fact.id.in_(fids)))}
        ref_ids = lambda kind: {i for f in facts.values() for k, i in f.refs if k == kind}  # noqa: E731

        scope = set(members) | _two_hops(nb, members) | set(users) | ref_ids("person")
        scope |= {f.subject_id for f in facts.values()} | {f.speaker_id for f in facts.values() if f.speaker_id}
        # Load people (and aliases) first: FamilyGraph then reuses the identity map instead of lazy-loading aliases.
        rows = s.scalars(select(m.Person).options(selectinload(m.Person.aliases))
                         .where(m.Person.family_id == space_id, m.Person.id.in_(scope))).all()
        scope = {p.id for p in rows}
        people = {p.id: PersonV(p.id, p.slug, p.display_name, p.lang_name, p.id in users, users.get(p.id, ""),
                                tuple((a.alias, a.lang) for a in p.aliases)) for p in rows}
        kin = FamilyGraph.from_session(s, space_id, person_ids=scope)

        near = set(members) | {x for p in members for x in nb.get(p, ())}
        gids = {g for g, mem in by_group.items() if mem.keys() & near} | ref_ids("group")
        grows = s.scalars(select(m.Group).where(m.Group.family_id == space_id, m.Group.id.in_(gids))).all()
        groups = {g.id: GroupV(g.id, g.slug, g.name, frozenset(by_group[g.id].keys() & scope)) for g in grows}
        trows = s.scalars(select(m.Thing).where(m.Thing.family_id == space_id, m.Thing.id.in_(ref_ids("thing")) |
                                                m.Thing.owner_id.in_(members))).all()
        things = {t.id: ThingV(t.id, t.slug, t.kind, t.name, t.owner_id, tuple(tuple(g) for g in (t.keys or [])),
                               tuple(x for x in [t.lang_name, *(t.aliases or [])] if x)) for t in trows}
        storylines = cls._storylines(s, space_id, scope)

        adj: dict[int, list[Hop]] = defaultdict(list)
        links: dict[Key, list] = defaultdict(list)
        gpair: dict[tuple[int, int, str], tuple] = {}
        gender = lambda p, ml, fl, nl: {"m": ml, "f": fl}.get(kin.people[p].gender, nl)  # noqa: E731
        for t in ties:
            if t.src_person in scope and t.dst_person in scope:
                label = TIE_LABEL.get(t.kind, t.kind.replace("_", " "))  # every tie kind is symmetric
                adj[t.src_person].append(Hop(t.dst_person, "tie", label, t.context, t.fact_id))
                adj[t.dst_person].append(Hop(t.src_person, "tie", label, t.context, t.fact_id))
        for e in edges:
            a, b = e.src_person, e.dst_person
            if a not in scope or b not in scope:
                continue
            if e.relation == "parent":
                ab, ba = gender(b, "son", "daughter", "child"), gender(a, "father", "mother", "parent")
            elif e.relation == "spouse":
                ab, ba = gender(b, "husband", "wife", "spouse"), gender(a, "husband", "wife", "spouse")
            else:
                ab, ba = gender(b, "brother", "sister", "sibling"), gender(a, "brother", "sister", "sibling")
            adj[a].append(Hop(b, "kin", ab, "", e.fact_id))
            adj[b].append(Hop(a, "kin", ba, "", e.fact_id))
        for a, b, fid in [(t.src_person, t.dst_person, t.fact_id) for t in ties] + \
                [(e.src_person, e.dst_person, e.fact_id) for e in edges]:
            if a in scope and b in scope:
                links[("person", a)].append((fid, frozenset({a, b})))
                links[("person", b)].append((fid, frozenset({a, b})))
        for g in grows:
            label = f"fellow {g.name} member"
            mem = {p: f for p, f in by_group[g.id].items() if p in scope}
            links[("group", g.id)].append((g.fact_id, frozenset()))
            for p, f in mem.items():
                links[("person", p)].append((f, frozenset({p})))
                links[("group", g.id)].append((f, frozenset({p})))
                for q, fq in mem.items():
                    if q != p:
                        adj[p].append(Hop(q, "group", label, "", fq))
                        gpair[(p, q, label)] = ((f, p), (fq, q))
        for t in things.values():
            row_fact = next(r.fact_id for r in trows if r.id == t.id)
            links[("thing", t.id)].append((row_fact, frozenset({t.owner_id}) if t.owner_id else frozenset()))

        about: dict[Key, list[int]] = defaultdict(list)
        first_mention: dict[int, datetime] = {}
        for f in facts.values():
            for k in {("person", f.subject_id), *f.refs}:
                about[k].append(f.id)
            for k, i in f.refs:
                if k == "person" and (i not in first_mention or f.said_at < first_mention[i]):
                    first_mention[i] = f.said_at
        for st in storylines.values():
            about[("storyline", st.id)].extend(fid for _sid, _l, _at, fid, _st in st.states if fid in facts)

        first_known = {(k, kind, i): at for k, kind, i, at in s.execute(
            select(m.Knowledge.knower_id, m.Knowledge.item_kind, m.Knowledge.item_id, m.Knowledge.first_at)
            .where(m.Knowledge.knower_id.in_(members)))}
        return cls(space_id, members, kin, people, things, groups, {k: tuple(v) for k, v in adj.items()}, facts,
                   {k: frozenset(v) for k, v in aud.items()}, storylines, first_mention, now,
                   {k: tuple(v) for k, v in links.items()}, {k: tuple(v) for k, v in about.items()}, gpair,
                   first_known, {g.id: tuple(x for x in (g.name, g.lang_name) if x) for g in grows})

    @staticmethod
    def _storylines(s: Session, space_id: int, scope: set[int]) -> dict[int, StoryV]:
        rows = s.scalars(select(m.Storyline).where(m.Storyline.family_id == space_id,
                                                   m.Storyline.owner_id.in_(scope))).all()
        states: dict[int, list] = defaultdict(list)
        for st in s.scalars(select(m.StorylineState).where(m.StorylineState.storyline_id.in_([r.id for r in rows]))
                            .order_by(m.StorylineState.seq)):
            states[st.storyline_id].append((st.id, st.label, st.at, st.fact_id, st.status))
        return {r.id: StoryV(r.id, r.slug, r.owner_id, r.title, tuple(tuple(g) for g in (r.keys or [])), r.status,
                             r.unresolved, tuple(states[r.id])) for r in rows}

    # ---- visibility -------------------------------------------------------------------------------------------------
    def _fact_ok(self, fid: int | None, viewer: int, speaker: int | None, mentioned: frozenset[int]) -> bool:
        if fid is None:
            return True  # setup/legacy link: visible to everyone in the space
        f = self.facts.get(fid)
        if f is None:
            return False  # not heard or said by anyone in this call
        return (fact_visible(f, self.audience.get(fid, frozenset()), viewer, self.now)
                or (speaker is not None and disclosable(f, speaker, mentioned, self.now)))

    def visible(self, viewer: int, kind: str, id: int, speaker: int | None = None) -> bool:
        if kind == "person" and (id == viewer or id in self.members):
            return True
        if kind == "storyline" and id in self.storylines and self.storylines[id].owner_id == viewer:
            return True
        # Only the entity being resolved counts as "just mentioned" (D9), never the link's other endpoint.
        mentioned = frozenset({id}) if kind == "person" else frozenset()
        for fid, ends in self.links.get((kind, id), ()):
            if viewer in ends or self._fact_ok(fid, viewer, speaker, mentioned):
                return True
        return any(self._fact_ok(fid, viewer, speaker, mentioned) for fid in self.about.get((kind, id), ()))

    def _hop_ok(self, listener: int, speaker: int | None, a: int, h: Hop, mentioned: frozenset[int]) -> bool:
        """mentioned: the entity being rendered (D9); a hop's endpoints do not count as mentioned by themselves."""
        if h.kind == "group":  # two memberships behind one hop: both must be visible
            return all(p == listener or self._fact_ok(f, listener, speaker, mentioned)
                       for f, p in self.gpair[(a, h.to, h.label)])
        return listener in (a, h.to) or self._fact_ok(h.fact_id, listener, speaker, mentioned)

    def structural_known(self, knower: int, kind: str, id: int) -> bool:
        if kind == "person":
            if id == knower or (knower in self.members and id in self.members):
                return True
            if any(h.to == id and h.kind in ("tie", "group") for h in self.adj.get(knower, ())):
                return True
            if knower in self.kin.people and id in self.kin.people and self.kin.distance(knower, id) <= 1:
                return True
        elif kind == "group" and id in self.groups and knower in self.groups[id].members:
            return True
        elif kind == "thing" and id in self.things and self.things[id].owner_id == knower:
            return True
        elif kind == "storyline" and id in self.storylines and self.storylines[id].owner_id == knower:
            return True
        return any(self.facts[f].subject_id == knower and self.facts[f].speaker_id == knower
                   for f in self.about.get((kind, id), ()))

    # ---- render (2.3) -----------------------------------------------------------------------------------------------
    def render(self, listener: int, person_id: int, speaker: int | None = None) -> str:
        mentioned = frozenset({person_id})
        return self._render(listener, person_id, speaker, lambda a, h: self._hop_ok(listener, speaker, a, h, mentioned))

    def _kin_ok(self, ego: int, e: int, ok: HopOk) -> bool:
        """True only when every step of the path FamilyGraph.render describes is walkable, so its
        parenthetical ("Mom's younger brother") never names a relation the listener has not seen."""
        if ego not in self.kin.people or e not in self.kin.people:
            return False
        steps = self.kin.shortest_steps(ego, e)
        if steps is None or len(steps) > MAX_KIN_DEPTH:
            return False
        prev = ego
        for _step, n in steps:
            if not (self._hop(prev, n, ("kin",), ok) or self._sibling_ok(prev, n, ok)):
                return False
            prev = n
        return True

    def _sibling_ok(self, a: int, b: int, ok: HopOk) -> bool:
        """A sibling step FamilyGraph derives from a shared parent: both parent edges must be walkable."""
        return any(self._hop(a, p, ("kin",), ok) and self._hop(p, b, ("kin",), ok)
                   for p in self.kin.parents.get(a, set()) & self.kin.parents.get(b, set()))

    def _hop(self, a: int, b: int, kinds: tuple[str, ...], ok: HopOk) -> Hop | None:
        return next((h for h in self.adj.get(a, ()) if h.to == b and h.kind in kinds and ok(a, h)), None)

    def _render(self, ego: int, e: int, speaker: int | None, ok: HopOk) -> str:
        name = self.people[e].name
        if e == ego:
            return "you"
        if self._kin_ok(ego, e, ok):
            return self.kin.render(ego, e)
        h = self._hop(ego, e, ("tie",), ok)
        if h:
            return f"your {h.label} {name}{_ctx(h)}"
        if speaker is not None and speaker not in (ego, e) and speaker in self.people:
            s_name = self.people[speaker].name
            # Deviation from 2.3 prefix: a tied speaker is just their name ("Mei's friend Lin", the spec example).
            prefix = f"your {self.kin.role(ego, speaker)} {s_name}" if self._kin_ok(ego, speaker, ok) else s_name
            if self._kin_ok(speaker, e, ok):
                return f"{prefix}'s {self.kin.role(speaker, e)} {name}"
            h = self._hop(speaker, e, ("tie", "group"), ok)
            if h:
                return f"{prefix}'s {h.label} {name}{_ctx(h)}"
        path = self._bfs(ego, e, ok)
        if path:
            nodes = [ego] + [h.to for _a, h in path]
            i = next(j for j in range(len(nodes) - 2, -1, -1)
                     if nodes[j] == ego or self.structural_known(ego, "person", nodes[j]))
            labels = "'s ".join(h.label for _a, h in path[i:])
            lead = "your" if nodes[i] == ego else f"{self.people[nodes[i]].name}'s"
            return f"{lead} {labels} {name}{_ctx(path[-1][1])}"
        if speaker is not None and speaker in self.people and speaker != e:
            return f"{name}, mentioned by {self.people[speaker].name}"
        return name

    def _bfs(self, ego: int, e: int, ok: HopOk) -> tuple[tuple[int, Hop], ...] | None:
        """Cheapest visible path ego -> e within MAX_BFS_HOPS (kin 1, tie 1, group 1.5)."""
        best = {ego: 0.0}
        heap: list = [(0.0, 0, ego, ())]
        n = 0
        while heap:
            cost, _n, node, path = heapq.heappop(heap)
            if node == e:
                return path
            if len(path) == MAX_BFS_HOPS:
                continue
            for h in self.adj.get(node, ()):
                c = cost + HOP_COST[h.kind]
                if c < best.get(h.to, float("inf")) and ok(node, h):
                    best[h.to] = c
                    n += 1
                    heapq.heappush(heap, (c, n, h.to, path + ((node, h),)))
        return None

    # ---- cards ------------------------------------------------------------------------------------------------------
    def card_body(self, listener: int, kind: str, id: int, speaker: int | None,
                  now: datetime) -> tuple[str, tuple[int, ...]]:
        if now != self.now:  # one clock per card: judge the render and the cited facts against the same now
            return replace(self, now=now).card_body(listener, kind, id, speaker, now)
        mentioned = frozenset({id}) if kind == "person" else frozenset()
        about = [self.facts[i] for i in self.about.get((kind, id), ())]
        ok = [f for f in about if f.status == "active"
              and usable(f, self.audience.get(f.id, frozenset()), listener, speaker, mentioned, now)]
        ok.sort(key=lambda f: f.said_at, reverse=True)
        if kind == "person":
            head = self.render(listener, id, speaker)
            cited = [f for f in ok if f.subject_id == id and f.predicate in IDENTITY - {"tie"}][:CARD_FACTS]
        elif kind == "storyline":
            st = self.storylines[id]
            usable_ids = {f.id for f in ok}
            steps = [f"{label} ({_day(at)})" for _sid, label, at, fid, status in st.states
                     if fid in usable_ids and status == "active"]
            owner = self.people[st.owner_id].name if st.owner_id in self.people else ""
            return f"{owner}'s {st.title}: " + " -> ".join(steps), tuple(f.id for f in ok)
        else:
            head = self.things[id].name if kind == "thing" else self.groups[id].name
            owner = self.things[id].owner_id if kind == "thing" else None
            if owner is not None and owner in self.people and self.visible(listener, "person", owner, speaker):
                head += f" ({self.render(listener, owner, speaker)}'s {self.things[id].kind})"
            cited = ok[:CARD_FACTS]
        parts = [head] + [f.text for f in cited]
        first = min(ok, key=lambda f: f.said_at, default=None)
        if first is not None:
            parts.append(f"first mentioned {_day(first.said_at)}")
            cited = cited + [first]
        elif (listener, kind, id) in self.first_known:
            parts.append(f"first mentioned {_day(self.first_known[(listener, kind, id)])}")
        return ", ".join(parts), tuple(dict.fromkeys(f.id for f in cited))

    # ---- prompts (2.4) ----------------------------------------------------------------------------------------------
    def roster(self, listeners: frozenset[int], speaker: int, recent_ids: Iterable[int] = ()) -> str:
        """PEOPLE section of a world call's MT prompt. recent_ids: person ids linked in the last 6 utterances."""
        listeners = frozenset(listeners)
        if not listeners:  # all() over no listeners is True: an empty set would show everything
            raise ValueError("roster needs at least one listener")
        recent = [i for i in recent_ids if i in self.people]
        cand = (_two_hops(self.adj, self.members) | set(recent)) - self.members
        shown = [e for e in cand if e in self.people
                 and all(self.visible(L, "person", e, speaker) for L in listeners)]
        latest = lambda e: max((self.facts[f].said_at.timestamp() for f in self.about.get(("person", e), ())),  # noqa: E731
                               default=0.0)
        ranked = sorted(self.members & self.people.keys(), key=lambda e: e != speaker) + sorted(
            shown, key=lambda e: (e not in recent, -latest(e), e))
        lines = []
        for e in ranked[:ROSTER_CAP]:
            p = self.people[e]
            text = self.render(next(iter(listeners)), e, speaker) if len(listeners) == 1 \
                else self._third(listeners, speaker, e)
            forms = ", ".join(dict.fromkeys(a for a, _l in p.aliases if a not in (p.name, p.lang_name)))
            lines.append(f"{p.slug} | {p.name} | {p.lang_name} | {text} | {forms}")
        return "\n".join(lines)

    def _third(self, listeners: frozenset[int], speaker: int, e: int) -> str:
        """Third person relative to the speaker over hops every listener may walk ("Arjun's uncle Ravi").
        ponytail: string swap of the leading "your"; the kin parenthetical stays speaker-relative ("Mom's ...")."""
        mentioned = frozenset({e})
        text = self._render(speaker, e, None,
                            lambda a, h: all(self._hop_ok(L, speaker, a, h, mentioned) for L in listeners))
        s_name = self.people[speaker].name
        if text == "you":
            return s_name
        return f"{s_name}'s {text[5:]}" if text.startswith("your ") else text

    # ---- match indexes ----------------------------------------------------------------------------------------------
    def index_forms(self) -> list[tuple[str, str, int]]:
        out: dict[tuple[str, str, int], None] = {}
        for p in self.people.values():
            for form in (p.name, p.lang_name, *(a for a, _l in p.aliases)):
                if form:
                    out[(form, "person", p.id)] = None
        for t in self.things.values():
            for form in (t.name, *t.aliases):
                if form:
                    out[(form, "thing", t.id)] = None
        for gid, forms in self.group_forms.items():
            for form in forms:
                out[(form, "group", gid)] = None
        return list(out)

    def fact_forms(self) -> list[tuple[str, str, int]]:
        out: dict[tuple[str, str, int], None] = {}
        for f in self.facts.values():
            if not expired(f, self.now):
                for group in f.keys:
                    for form in group:
                        out[(form, "fact", f.id)] = None
        for st in self.storylines.values():
            for group in st.keys:
                for form in group:
                    out[(form, "storyline", st.id)] = None
        return list(out)
