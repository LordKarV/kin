"""Family graph with kinship reasoning: paths, relation labels, kin-term resolution, address terms.

Everything is computed relative to an ego (normally the listener), so the same person is rendered
"your uncle Ravi mama (Mom's younger brother)" whether the speaker said "en magan", "un mama" or "Ravi".
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import models as m
from .ontology import KIN_TERMS, KinTermDef, normalize_term

GENERIC = {
    "parent": {"mother", "father"}, "child": {"son", "daughter"}, "spouse": {"husband", "wife"},
    "sibling": {"elder_brother", "younger_brother", "elder_sister", "younger_sister", "brother", "sister"},
    "brother": {"elder_brother", "younger_brother", "brother"}, "sister": {"elder_sister", "younger_sister", "sister"},
}
CAT = {"mother": "P", "father": "P", "son": "C", "daughter": "C", "husband": "S", "wife": "S",
       "elder_brother": "B", "younger_brother": "B", "elder_sister": "B", "younger_sister": "B", "brother": "B", "sister": "B"}
WORD = {"mother": "Mom", "father": "Dad", "son": "son", "daughter": "daughter", "husband": "husband", "wife": "wife",
        "elder_brother": "elder brother", "younger_brother": "younger brother", "elder_sister": "elder sister",
        "younger_sister": "younger sister", "brother": "brother", "sister": "sister"}
# sibling-type kin terms applied to cousins carry a relative-age constraint
AGE_RULE = {"anna": "older", "akka": "older", "thambi": "younger", "thangai": "younger"}


@dataclass
class Node:
    id: int
    slug: str
    name: str
    lang_name: str
    gender: str
    birth_year: int | None
    is_learner: bool
    is_deceased: bool
    notes: str
    aliases: list[tuple[str, str, str]]  # (alias, lang, kind)
    cues: list[str] = field(default_factory=list)


@dataclass
class ThingNode:
    id: int
    slug: str
    kind: str
    name: str
    lang_name: str
    aliases: list[str]
    note: str


class FamilyGraph:
    def __init__(self, family_id: int, heritage_lang: str, people: list[Node], edges: list[tuple], things: list[ThingNode]):
        self.family_id = family_id
        self.heritage_lang = heritage_lang
        self.people: dict[int, Node] = {p.id: p for p in people}
        self.by_slug: dict[str, Node] = {p.slug: p for p in people}
        self.things: list[ThingNode] = things
        self.thing_by_slug = {t.slug: t for t in things}
        self.parents: dict[int, set[int]] = {p.id: set() for p in people}
        self.children: dict[int, set[int]] = {p.id: set() for p in people}
        self.spouses: dict[int, set[int]] = {p.id: set() for p in people}
        self.siblings: dict[int, set[int]] = {p.id: set() for p in people}
        self._elder: dict[tuple[int, int], bool] = {}  # (a, b) -> a is elder than b
        self.address: dict[tuple[int, int], str] = {}  # (ego, target) -> how ego addresses target (family usage)
        for src, dst, rel, term, meta in edges:
            if rel == "parent":
                self.parents[dst].add(src); self.children[src].add(dst)
            elif rel == "spouse":
                self.spouses[src].add(dst); self.spouses[dst].add(src)
            elif rel == "sibling":
                self.siblings[src].add(dst); self.siblings[dst].add(src)
                if meta and "src_is_elder" in meta:
                    self._elder[(src, dst)] = bool(meta["src_is_elder"]); self._elder[(dst, src)] = not meta["src_is_elder"]
            if term:
                self.address[(dst, src)] = term
        # siblings via shared parents
        for a in self.people:
            for b in self.people:
                if a != b and self.parents[a] and self.parents[a] & self.parents[b]:
                    self.siblings[a].add(b)

    # ---- construction -------------------------------------------------------
    @classmethod
    def from_session(cls, session: Session, family_id: int) -> "FamilyGraph":
        fam = session.get(m.Family, family_id)
        people = []
        for p in session.scalars(select(m.Person).where(m.Person.family_id == family_id)):
            people.append(Node(p.id, p.slug, p.display_name, p.lang_name, p.gender, p.birth_year_approx, p.is_learner, p.is_deceased,
                               p.notes, [(a.alias, a.lang, a.kind) for a in p.aliases], list(p.cues or [])))
        edges = [(e.src_person, e.dst_person, e.relation, e.lang_term, e.meta or {})
                 for e in session.scalars(select(m.Edge).where(m.Edge.family_id == family_id))]
        things = [ThingNode(t.id, t.slug, t.kind, t.name, t.lang_name, list(t.aliases or []), t.note)
                  for t in session.scalars(select(m.Thing).where(m.Thing.family_id == family_id))]
        return cls(family_id, fam.heritage_lang if fam else "ta", people, edges, things)

    # ---- who's who (any family, any language) --------------------------------
    def learner_slug(self) -> str:
        return next((p.slug for p in self.people.values() if p.is_learner), next(iter(self.by_slug), ""))

    def elder_slug(self) -> str:
        """Oldest living non-learner: the default far-end speaker on a call."""
        elders = sorted((p for p in self.people.values() if not p.is_learner and not p.is_deceased and p.notes != "Not named yet"),
                        key=lambda p: p.birth_year or 9999)
        return elders[0].slug if elders else self.learner_slug()

    # ---- primitives ---------------------------------------------------------
    def is_elder(self, a: int, b: int) -> bool | None:
        if (a, b) in self._elder:
            return self._elder[(a, b)]
        ya, yb = self.people[a].birth_year, self.people[b].birth_year
        if ya is not None and yb is not None and ya != yb:
            return ya < yb
        return None

    def _g(self, pid: int, male: str, female: str, neutral: str | None = None) -> str:
        g = self.people[pid].gender
        return male if g == "m" else female if g == "f" else (neutral or male)

    def neighbors(self, n: int) -> list[tuple[str, int]]:
        out = []
        for p in self.parents[n]:
            out.append((self._g(p, "father", "mother"), p))
        for c in self.children[n]:
            out.append((self._g(c, "son", "daughter"), c))
        for s in self.spouses[n]:
            out.append((self._g(s, "husband", "wife"), s))
        for s in self.siblings[n]:
            e = self.is_elder(s, n)
            base = self._g(s, "brother", "sister")
            out.append((base if e is None else ("elder_" if e else "younger_") + base, s))
        return out

    def all_paths(self, ego: int, target: int, max_depth: int = 4) -> list[list[str]]:
        paths: list[list[str]] = []

        def dfs(n: int, seen: set[int], path: list[str]):
            if len(path) > max_depth:
                return
            if n == target and path:
                paths.append(list(path)); return
            for step, other in self.neighbors(n):
                if other not in seen:
                    dfs(other, seen | {other}, path + [step])

        dfs(ego, {ego}, [])
        return paths

    def shortest_path(self, ego: int, target: int) -> list[str] | None:
        if ego == target:
            return []
        q = deque([(ego, [])]); seen = {ego}
        while q:
            n, path = q.popleft()
            # deterministic order: parents, children, spouses, siblings (blood before marriage at equal depth)
            for step, other in self.neighbors(n):
                if other in seen:
                    continue
                if other == target:
                    return path + [step]
                seen.add(other); q.append((other, path + [step]))
        return None

    def distance(self, a: int, b: int) -> int:
        p = self.shortest_path(a, b)
        return len(p) if p is not None else 99

    @staticmethod
    def matches(path: list[str], pattern: str) -> bool:
        steps = pattern.split(".")
        if len(steps) != len(path):
            return False
        return all(ps == s or s in GENERIC.get(ps, set()) for ps, s in zip(steps, path))

    # ---- kin terms ------------------------------------------------------------
    def resolve_kin_term(self, term: KinTermDef, ego: int) -> set[int]:
        if not term.patterns:
            return set()
        maxd = max(len(p.split(".")) for p in term.patterns)
        out: set[int] = set()
        for t in self.people:
            if t == ego:
                continue
            paths = self.all_paths(ego, t, maxd)
            if any(self.matches(p, pat) for p in paths for pat in term.patterns):
                rule = AGE_RULE.get(term.term)
                if rule and min(len(p) for p in paths) > 1:  # cousin use: respect relative age
                    e = self.is_elder(t, ego)
                    if e is not None and ((rule == "older") != e):
                        continue
                out.add(t)
        for (e, t), word in self.address.items():
            if e == ego and normalize_term(word) in {normalize_term(x) for x in (term.term, term.script, *term.variants)}:
                out.add(t)
        return out

    def address_term(self, ego: int, target: int) -> str | None:
        """How ego's family addresses target: edge usage > '<Name> term' alias > ontology default."""
        if (ego, target) in self.address:
            return self.address[(ego, target)].lower()
        tgt = self.people[target]
        path = self.shortest_path(ego, target)
        name_l = tgt.name.lower()
        for alias, _lang, kind in tgt.aliases:
            if kind != "address" or any("஀" <= ch <= "௿" for ch in alias):
                continue
            a = alias.lower()
            if a.startswith(name_l + " "):
                return a[len(name_l) + 1:]
            from .ontology import lookup
            d = lookup(a)
            if d and path and any(self.matches(path, pat) for pat in d.patterns):
                return a
        if path:
            from .kin_tables import load_table
            try:
                terms = load_table(self.heritage_lang).terms
            except (KeyError, FileNotFoundError):
                terms = KIN_TERMS
            for d in terms:
                if d.kind == "kin" and any(self.matches(path, pat) for pat in d.patterns):
                    return d.term
        return None

    # ---- rendering --------------------------------------------------------
    def how(self, ego: int, target: int) -> str:
        path = self.shortest_path(ego, target)
        if not path:
            return "you" if ego == target else "relative"
        words = [WORD[s] for s in path]
        words = [words[0]] + [w.lower() for w in words[1:]]  # "Mom's mom", not "Mom's Mom"
        if CAT[path[0]] != "P":
            words[0] = "your " + words[0]
        return "'s ".join(words)

    def role(self, ego: int, target: int) -> str:
        path = self.shortest_path(ego, target)
        if path is None:
            return "relative"
        if not path:
            return "you"
        shape = "".join(CAT[s] for s in path)
        g = lambda male, female: self._g(target, male, female)  # noqa: E731
        if len(path) == 1:
            return {"mother": "mom", "father": "dad"}.get(path[0], WORD[path[0]])
        table = {
            "PP": g("grandfather", "grandmother"), "PB": g("uncle", "aunt"), "PBS": g("uncle", "aunt"), "PBC": "cousin",
            "BC": g("nephew", "niece"), "CC": g("grandson", "granddaughter"), "SP": g("father-in-law", "mother-in-law"),
            "CS": g("son-in-law", "daughter-in-law"), "SB": g("brother-in-law", "sister-in-law"), "BS": g("brother-in-law", "sister-in-law"),
            "PPB": g("grand-uncle", "grand-aunt"), "PPBS": g("grand-uncle", "grand-aunt"), "PPP": g("great-grandfather", "great-grandmother"),
            "CCC": g("great-grandson", "great-granddaughter"), "PPBC": "cousin", "BCC": g("great-nephew", "great-niece"),
        }
        return table.get(shape, "relative")

    def render(self, ego: int, target: int) -> str:
        t = self.people[target]
        if ego == target:
            return f"you ({t.name})"
        r = self.role(ego, target)
        if r in ("mom", "dad"):
            return f"your {r} ({t.name})"
        addr = self.address_term(ego, target)
        name = f"{t.name} {addr}" if addr else t.name
        return f"your {r} {name} ({self.how(ego, target)})"

    def roster(self, ego: int) -> list[dict]:
        """Compact family roster relative to ego, for the LLM prompt (cached prefix)."""
        rows = []
        for pid, p in self.people.items():
            rows.append({"id": p.slug, "name": p.name, "lang_name": p.lang_name, "render": self.render(ego, pid),
                         "aliases": [a for a, _l, k in p.aliases if k in ("nickname", "address")],
                         "notes": p.notes, "deceased": p.is_deceased})
        return rows
