"""Grow a family graph from what the grandchild tells KIN, in any of the 25 heritage languages. Nothing is pre-seeded.

A family starts as the learner plus the person they call (setup). Every confirmed "Who's X?" card adds one relative by
its path from the learner ("mother.younger_brother"), reusing people already on that path and creating unnamed
placeholders ("Mom") for missing links; naming a placeholder later fills it in instead of duplicating it.
"""
from __future__ import annotations

import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import models as m
from .kin_tables import load_table
from .kinship import WORD, FamilyGraph
from .ontology import normalize_term

PLACEHOLDER_NOTE = "Not named yet"
LEARNER_BIRTH_YEAR = 2005  # ponytail: assumed; only orders generations (who is the "elder"), never shown
GENERATION_YEARS = 28

# step -> (gender, how the new person attaches to the current one)
STEPS = {
    "mother": ("f", "parent"), "father": ("m", "parent"),
    "son": ("m", "child"), "daughter": ("f", "child"),
    "husband": ("m", "spouse"), "wife": ("f", "spouse"),
    "elder_brother": ("m", "elder"), "younger_brother": ("m", "younger"), "brother": ("m", "sibling"),
    "elder_sister": ("f", "elder"), "younger_sister": ("f", "younger"), "sister": ("f", "sibling"),
}
GENERATION = {"parent": -1, "child": 1}
EXTRA_WORDS = {"parent": "parent", "child": "child", "spouse": "spouse", "sibling": "sibling"}

# the relations offered in pickers (setup + cards); any path in the STEPS grammar works through the API
COMMON_PATHS = [
    "mother.mother", "mother.father", "father.mother", "father.father",
    "mother", "father",
    "mother.elder_brother", "mother.younger_brother", "mother.elder_sister", "mother.younger_sister",
    "father.elder_brother", "father.younger_brother", "father.elder_sister", "father.younger_sister",
    "mother.younger_brother.wife", "father.elder_brother.wife",
    "elder_brother", "younger_brother", "elder_sister", "younger_sister",
    "mother.brother.son", "mother.brother.daughter", "father.brother.son", "father.brother.daughter",
]


def path_label(path: str) -> str:
    """'mother.younger_brother' -> "Mom's younger brother"."""
    words = [WORD.get(s) or EXTRA_WORDS.get(s, s.replace("_", " ")) for s in path.split(".")]
    words = [words[0]] + [w.lower() for w in words[1:]]
    out = "'s ".join(words)
    return out[0].upper() + out[1:]


def relations() -> list[dict]:
    return [{"path": p, "label": path_label(p)} for p in COMMON_PATHS]


def suggest(term: str, lang: str) -> list[dict]:
    """Relations a kin word can mean in the family's language, from the language's kin table (all 25 languages)."""
    try:
        d = load_table(lang).surface_forms().get(normalize_term(term))
    except Exception:  # noqa: BLE001  (no table for this language: the picker falls back to COMMON_PATHS)
        return []
    if d is None or not d.patterns:
        return []
    return [{"path": p, "label": path_label(p), "gloss": d.gloss} for p in d.patterns if _valid(p)]


def _valid(path: str) -> bool:
    return all(step in STEPS for step in path.split("."))


def _slug(s: Session, family_id: int, name: str) -> str:
    base = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    base = "p_" + (re.sub(r"[^a-z0-9]+", "_", base).strip("_") or "person")
    taken = set(s.scalars(select(m.Person.slug).where(m.Person.family_id == family_id)))
    slug, n = base, 2
    while slug in taken:
        slug, n = f"{base}_{n}", n + 1
    return slug


def _is_native(name: str) -> bool:
    return any(c.isalpha() and not unicodedata.name(c, "").startswith("LATIN") for c in name)


def _aliases(name: str, call_them: str, lang: str) -> list[m.Alias]:
    native = _is_native(name)
    out = [m.Alias(alias=name, lang=lang if native else "en", kind="script" if native else "name")]
    if call_them:
        out += [m.Alias(alias=call_them, lang=lang, kind="address"), m.Alias(alias=f"{name} {call_them}", lang=lang, kind="address")]
    return out


def _person(s: Session, fam: m.Family, name: str, gender: str, birth: int | None, call_them: str = "",
            learner: bool = False, placeholder: bool = False) -> m.Person:
    p = m.Person(family_id=fam.id, slug=_slug(s, fam.id, name), display_name=name, lang_name=name if _is_native(name) else "",
                 gender=gender, birth_year_approx=birth, is_learner=learner,
                 notes=PLACEHOLDER_NOTE if placeholder else "Added by the family during a call.")
    p.aliases = [] if placeholder else _aliases(name, call_them, fam.heritage_lang)
    s.add(p)
    s.flush()
    return p


def _existing(s: Session, family_id: int, cur: int, step: str) -> int | None:
    g = FamilyGraph.from_session(s, family_id)
    near = g.parents[cur] | g.children[cur] | g.spouses[cur] | g.siblings[cur]
    for other in near:
        path = g.shortest_path(cur, other)
        if path and len(path) == 1 and FamilyGraph.matches(path, step):
            return other
    return None


def _attach(s: Session, fam: m.Family, cur: m.Person, new: m.Person, step: str, call_them: str) -> None:
    how = STEPS[step][1]
    term = call_them if cur.is_learner else ""
    if how == "parent":
        s.add(m.Edge(family_id=fam.id, src_person=new.id, dst_person=cur.id, relation="parent", lang_term=term))
    elif how == "child":
        s.add(m.Edge(family_id=fam.id, src_person=cur.id, dst_person=new.id, relation="parent"))
    elif how == "spouse":
        s.add(m.Edge(family_id=fam.id, src_person=cur.id, dst_person=new.id, relation="spouse"))
    elif how == "elder":
        s.add(m.Edge(family_id=fam.id, src_person=new.id, dst_person=cur.id, relation="sibling", lang_term=term, meta={"src_is_elder": True}))
    elif how == "younger":
        s.add(m.Edge(family_id=fam.id, src_person=cur.id, dst_person=new.id, relation="sibling", meta={"src_is_elder": True}))
    else:
        s.add(m.Edge(family_id=fam.id, src_person=cur.id, dst_person=new.id, relation="sibling", meta={}))
    s.flush()


def add_relative(s: Session, family_id: int, path: str, name: str, call_them: str = "", anchor: str | None = None) -> m.Person:
    """Add (or name) the person at `path` from the learner (or `anchor`). Returns that person."""
    if not path or not _valid(path):
        raise ValueError(f"unsupported relation path: {path!r}")
    fam = s.get(m.Family, family_id)
    if fam is None:
        raise ValueError(f"unknown family {family_id}")
    people = {p.slug: p for p in s.scalars(select(m.Person).where(m.Person.family_id == family_id))}
    cur = people[anchor] if anchor else next(p for p in people.values() if p.is_learner)
    steps = path.split(".")
    for i, step in enumerate(steps):
        last = i == len(steps) - 1
        gender, how = STEPS[step]
        birth = cur.birth_year_approx and cur.birth_year_approx - GENERATION.get(how, 0) * GENERATION_YEARS
        found = _existing(s, family_id, cur.id, step)
        if found is not None:
            person = s.get(m.Person, found)
            if last and person.notes == PLACEHOLDER_NOTE:  # name the "Mom" we created earlier
                person.display_name, person.notes = name, "Added by the family during a call."
                person.aliases = _aliases(name, call_them, fam.heritage_lang)
                s.flush()
                return person
            if not last or person.display_name == name:
                cur = person
                continue
        new = _person(s, fam, name if last else WORD.get(step, step), gender, birth, call_them if last else "", placeholder=not last)
        _attach(s, fam, cur, new, step, call_them if last else "")
        cur = new
    return cur


def create_family(s: Session, lang: str, learner_name: str, elder_name: str, elder_call: str, elder_path: str) -> tuple[m.Family, m.Person, m.Person]:
    """The two-minute setup: you, plus the person you are calling and how they are related to you."""
    fam = m.Family(name=f"{learner_name}'s family", heritage_lang=lang)
    s.add(fam)
    s.flush()
    learner = _person(s, fam, learner_name, "?", LEARNER_BIRTH_YEAR, learner=True)
    elder = add_relative(s, fam.id, elder_path, elder_name, elder_call)
    return fam, learner, elder
