#!/usr/bin/env python3
"""Standalone checker for the planted common-ground scenarios (standard library only, no pydantic).

Checks every line of the build's set (../backend/eval/common_ground/scenarios.jsonl) and of scenarios_extra.jsonl:

1. Format: JSON parses; required fields, allowed keys and literal values per the Pydantic `Scenario` model in
   backend/eval/common_ground/schemas.py (extra keys are errors there too). Deliberately stricter than Pydantic's lax
   mode on types: a bool must be a JSON true/false and a day a JSON number ("yes" or "42" pass Pydantic, not this).
2. References: every rule of `Scenario._refs` and `_card_ok`, re-implemented here.
3. Test-set rules: ids unique across both files; the `same_language` tag is true; every listener whose language differs
   from the speaker's has `probe.translations[lang]`. Extra file only: exactly 2 participants and the `one_to_one` tag.
4. Knowledge math (WARN only): for every expected who/what card with gap "new"/"reminder", and every expectation of NO
   who/what card where the listener has evidence rows on that entity, p is recomputed with the formulas and constants
   of backend/app/world/knowledge.py (evidence applied in list order). Decision: "new" with no rows, "reminder" when
   p < FORGOT, else none. Structural, visibility and matcher gates are not modelled, so a WARN is a prompt to check,
   not a failure; a hint names the gate that probably explains it.
5. Bridge sanity (WARN only): an expected bridge's fact must be unheard by the speaker (audience and told), not
   sensitive, said within 180 days, not logged toward the speaker in the last 7 days, and at most one per listener.

Exit status: 1 on any format/reference/test-set failure, else 0 (warnings do not fail).
Usage: python3 validate.py [-v] [file ...]   (-v also prints every knowledge check that agrees)
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE_FILE = HERE.parent / "backend" / "eval" / "common_ground" / "scenarios.jsonl"
EXTRA_FILE = HERE / "scenarios_extra.jsonl"

KIN_PATH = re.compile(r"^[a-z_]+(\.[a-z_]+)*$")   # schemas.KIN_PATH (builder.STEPS grammar)

# ---------------------------------------------------------------------------------------------------------------------
# 1. Format: the Pydantic models as data. (type, required). Types: str, bool, float, list:T, dict:T (str keys),
#    opt:T (T or null), lit:a|b (one of the strings; an empty alternative is ""), or a model name.
# ---------------------------------------------------------------------------------------------------------------------
MODELS: dict[str, dict[str, tuple[str, bool]]] = {
    "Scenario": {"id": ("str", True), "tags": ("list:str", True), "people": ("list:PersonS", True),
                 "groups": ("list:GroupS", False), "ties": ("list:TieS", False), "edges": ("list:EdgeS", False),
                 "facts": ("list:FactS", False), "evidence": ("list:EvidenceS", False), "probe": ("ProbeS", True),
                 "expect": ("dict:ExpectS", True)},
    "PersonS": {"key": ("str", True), "name": ("str", True), "lang": ("str", False), "user": ("bool", True),
                "forms": ("list:str", False)},
    "GroupS": {"key": ("str", True), "name": ("str", True), "forms": ("list:str", False),
               "members": ("list:str", True), "day": ("float", True), "said_by": ("str", True),
               "heard_by": ("list:str", False)},
    "TieS": {"a": ("str", True), "b": ("str", True), "kind": ("str", True), "context": ("str", False),
             "day": ("float", True), "said_by": ("str", True), "heard_by": ("list:str", False)},
    "EdgeS": {"a": ("str", True), "b": ("str", True), "path": ("str", True), "day": ("float", True),
              "said_by": ("str", True)},
    "StorylineRef": {"title": ("str", True), "state": ("str", True)},
    "FactS": {"key": ("str", True), "subject": ("str", True), "speaker": ("str", True), "predicate": ("str", True),
              "text": ("str", True), "keys": ("list:list:str", False), "day": ("float", True),
              "source": ("lit:call|sms", True), "audience": ("list:str", False), "told": ("list:str", False),
              "sensitive_kind": ("lit:|health|money|conflict", False), "remembered": ("bool", False),
              "pinned": ("bool", False), "third_party": ("bool", False), "contradicts": ("opt:str", False),
              "storyline": ("opt:StorylineRef", False)},
    "ItemRef": {"kind": ("lit:person|group|fact|state|bridge", True), "key": ("str", True)},
    "EvidenceS": {"knower": ("str", True), "item": ("ItemRef", True),
                  "ev": ("lit:heard|shown|said|authored|confirmed|asked", True), "day": ("float", True),
                  "target": ("opt:str", False)},
    "ProbeS": {"day": ("float", True), "participants": ("list:str", True), "speaker": ("str", True),
               "text": ("str", True), "partials": ("list:str", False), "translations": ("dict:str", False)},
    "CardE": {"kind": ("lit:who|what|ask|bridge|storyline|term", True), "key": ("str", True),
              "gap": ("opt:lit:new|reminder", False), "cites": ("list:str", False),
              "must_not_cite": ("list:str", False)},
    "ExpectS": {"cards": ("list:CardE", False)},
}
DEFAULTS = {"lang": "", "forms": [], "groups": [], "ties": [], "edges": [], "facts": [], "evidence": [],
            "heard_by": [], "context": "", "keys": [], "audience": [], "told": [], "sensitive_kind": "",
            "remembered": False, "pinned": False, "third_party": False, "contradicts": None, "storyline": None,
            "target": None, "partials": [], "translations": {}, "gap": None, "cites": [], "must_not_cite": [],
            "cards": []}


def check_model(obj, model: str, path: str, errs: list[str]) -> None:
    if not isinstance(obj, dict):
        errs.append(f"{path}: expected an object ({model})")
        return
    fields = MODELS[model]
    for k in obj:
        if k not in fields:
            errs.append(f"{path}: unknown field {k!r}")
    for k, (typ, required) in fields.items():
        if k in obj:
            check_type(obj[k], typ, f"{path}.{k}", errs)
        elif required:
            errs.append(f"{path}: missing required field {k!r}")


def check_type(v, typ: str, path: str, errs: list[str]) -> None:
    if typ == "str":
        ok = isinstance(v, str)
    elif typ == "bool":
        ok = isinstance(v, bool)
    elif typ == "float":
        ok = isinstance(v, (int, float)) and not isinstance(v, bool)
    elif typ.startswith("opt:"):
        if v is not None:
            check_type(v, typ[4:], path, errs)
        return
    elif typ.startswith("lit:"):
        ok = isinstance(v, str) and v in typ[4:].split("|")
        if not ok:
            errs.append(f"{path}: {v!r} is not one of {typ[4:].split('|')}")
        return
    elif typ.startswith("list:"):
        if not isinstance(v, list):
            errs.append(f"{path}: expected a list")
            return
        for i, x in enumerate(v):
            check_type(x, typ[5:], f"{path}[{i}]", errs)
        return
    elif typ.startswith("dict:"):
        if not isinstance(v, dict):
            errs.append(f"{path}: expected an object")
            return
        for k, x in v.items():
            check_type(x, typ[5:], f"{path}[{k!r}]", errs)
        return
    else:
        check_model(v, typ, path, errs)
        return
    if not ok:
        errs.append(f"{path}: expected {typ}, got {type(v).__name__}")


def d(obj: dict, k: str):
    """Field value with the model default when the key is absent."""
    return obj[k] if k in obj else DEFAULTS.get(k)


# ---------------------------------------------------------------------------------------------------------------------
# 2. References: Scenario._refs, _item_exists, _card_ok
# ---------------------------------------------------------------------------------------------------------------------
def check_refs(s: dict) -> list[str]:
    errs: list[str] = []
    people = {p["key"]: p for p in s["people"]}
    groups = {g["key"] for g in d(s, "groups")}
    facts = {f["key"]: f for f in d(s, "facts")}
    pg = [p["key"] for p in s["people"]] + [g["key"] for g in d(s, "groups")]
    for what, keys in (("people/group", pg), ("fact", [f["key"] for f in d(s, "facts")])):
        dup = sorted({k for k in keys if keys.count(k) > 1})
        if dup:
            errs.append(f"duplicate {what} keys: {dup}")
    story_titles = {d(f, "storyline")["title"] for f in d(s, "facts") if d(f, "storyline")}
    pr = s["probe"]

    def person(k, where):
        if k not in people:
            errs.append(f"{where}: unknown person {k!r}")
            return False
        return True

    for g in d(s, "groups"):
        for k in [g["said_by"], *g["members"], *d(g, "heard_by")]:
            person(k, f"group {g['key']}")
    for t in d(s, "ties"):
        for k in [t["a"], t["b"], t["said_by"], *d(t, "heard_by")]:
            person(k, f"tie {t['a']}-{t['b']}")
    for e in d(s, "edges"):
        for k in (e["a"], e["b"], e["said_by"]):
            person(k, f"edge {e['a']}-{e['b']}")
        if not KIN_PATH.match(e["path"]):
            errs.append(f"edge {e['a']}-{e['b']}: bad kin path {e['path']!r}")
    for f in d(s, "facts"):
        for k in [f["subject"], f["speaker"], *d(f, "audience"), *d(f, "told")]:
            person(k, f"fact {f['key']}")
        if d(f, "contradicts") is not None and d(f, "contradicts") not in facts:
            errs.append(f"fact {f['key']}: contradicts unknown fact {d(f, 'contradicts')!r}")
    for ev in d(s, "evidence"):
        item, target = ev["item"], d(ev, "target")
        person(ev["knower"], "evidence")
        exists = {"person": item["key"] in people, "group": item["key"] in groups, "fact": item["key"] in facts,
                  "bridge": item["key"] in facts,
                  "state": item["key"] in facts and d(facts[item["key"]], "storyline") is not None}[item["kind"]]
        if not exists:
            errs.append(f"evidence item {item['kind']}:{item['key']} does not exist")
            continue
        if item["kind"] == "bridge":
            f = facts[item["key"]]
            if not (f["subject"] == f["speaker"] == ev["knower"]) or target in d(f, "audience"):
                errs.append(f"evidence bridge {item['key']}: impossible card_log row")
        if (item["kind"] == "bridge") != (target is not None):
            errs.append(f"evidence {item['key']}: target is required for bridge items and only for them")
        if target is not None:
            person(target, "evidence target")
        if ev["day"] > pr["day"]:
            errs.append(f"evidence {item['key']} on day {ev['day']} is after the probe")
    for kind, rows in (("TieS", d(s, "ties")), ("EdgeS", d(s, "edges")), ("FactS", d(s, "facts")),
                       ("GroupS", d(s, "groups"))):
        for x in rows:
            if x["day"] > pr["day"]:
                errs.append(f"{kind} on day {x['day']} is after the probe")

    for k in pr["participants"]:
        if person(k, "probe") and not people[k]["user"]:
            errs.append(f"probe participant {k!r} is not a user")
    if not all(pr["text"].startswith(x) for x in d(pr, "partials")):
        errs.append("every partial must be a prefix of probe.text")
    if pr["speaker"] not in pr["participants"]:
        errs.append(f"probe speaker {pr['speaker']!r} is not a participant")
    expect = s["expect"]
    if set(expect) != set(pr["participants"]):
        errs.append(f"expect must name exactly the participants: {sorted(expect)} vs {sorted(pr['participants'])}")
    if pr["speaker"] in expect and d(expect[pr["speaker"]], "cards"):
        errs.append("the speaker never gets cards about their own words")
    for listener, ex in expect.items():
        for c in d(ex, "cards"):
            where = f"expect[{listener}] {c['kind']}:{c['key']}"
            if c["kind"] in ("who", "what"):
                if c["key"] not in people and c["key"] not in groups:
                    errs.append(f"{where}: unknown entity")
                if d(c, "gap") is None:
                    errs.append(f"{where}: who/what cards need a gap")
            elif d(c, "gap") is not None:
                errs.append(f"{where}: only who/what cards carry a gap")
            if c["kind"] == "bridge":
                f = facts.get(c["key"])
                if f is None or f["subject"] != listener or f["speaker"] != listener:
                    errs.append(f"{where}: a bridge must name a fact about the listener, said by the listener")
            if c["kind"] == "storyline" and c["key"] not in story_titles:
                errs.append(f"{where}: unknown storyline")
            if c["kind"] == "ask" and c["key"].casefold() not in pr["text"].casefold():
                errs.append(f"{where}: ask term is not in the probe text")
            for k in [*d(c, "cites"), *d(c, "must_not_cite")]:
                if k not in facts:
                    errs.append(f"{where}: cites unknown fact {k!r}")
            if c["kind"] in ("who", "what") and c["key"] in pr["participants"]:
                errs.append(f"{where}: participants are structural, never a gap")
    return errs


# ---------------------------------------------------------------------------------------------------------------------
# 3. Test-set rules (tests/test_cg_testset.py) plus the one-to-one rules for the extra file
# ---------------------------------------------------------------------------------------------------------------------
def check_testset(s: dict, extra: bool) -> list[str]:
    errs: list[str] = []
    langs = {p["key"]: d(p, "lang") for p in s["people"]}
    pr = s["probe"]
    if any(k not in langs for k in [pr["speaker"], *pr["participants"]]):
        return errs   # already reported as a reference failure
    sl = langs[pr["speaker"]]
    if "same_language" in s["tags"] and not all(langs[k] == sl for k in pr["participants"]):
        errs.append("tag same_language but participants do not all share the speaker's language")
    need = {langs[k] for k in pr["participants"]} - {sl}
    missing = sorted(need - set(d(pr, "translations")))
    if missing:
        errs.append(f"probe.translations missing for listener language(s) {missing}")
    if extra:
        if len(pr["participants"]) != 2:
            errs.append(f"extra scenarios are one-to-one: {len(pr['participants'])} participants")
        if "one_to_one" not in s["tags"]:
            errs.append("extra scenarios carry the one_to_one tag")
    return errs


# ---------------------------------------------------------------------------------------------------------------------
# 4. Knowledge math, copied from backend/app/world/knowledge.py
# ---------------------------------------------------------------------------------------------------------------------
P_FLOOR = 0.02
PRIOR = 0.02
LEARN = {"heard": .70, "shown": .50, "said": .95, "authored": .95, "confirmed": .98}
H0_DAYS = {"heard": 30, "shown": 21, "said": 60, "authored": 60, "confirmed": 90, "asked": 30}
GROWTH, H_MAX = 1.5, 365
FORGOT = 0.35
SLIP, GUESS = 0.05, 0.02
THIRD_PARTY_TTL_DAYS = 120          # ARCHITECTURE D11
# Day 0 is mid September. Noon UTC, so a fractional day within half a day of an integer (41.9995) stays on that UTC
# date for the once-per-day half-life growth rule (D5).
DAY0 = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class State:
    p: float
    half_life_days: float
    last_at: datetime
    last_day: str


def at(day: float) -> datetime:
    return DAY0 + timedelta(days=day)


def p_now(st: State | None, t: datetime) -> float:
    if st is None:
        return PRIOR
    dt = max(0.0, (t - st.last_at).total_seconds() / 86400)
    return P_FLOOR + (st.p - P_FLOOR) * 2 ** (-dt / st.half_life_days)


def update(st: State | None, ev: str, t: datetime) -> State:
    if st is not None and t < st.last_at:
        t = st.last_at
    p0 = p_now(st, t)
    day = t.date().isoformat()
    if ev == "asked":
        p = p0 * SLIP / (p0 * SLIP + (1 - p0) * (1 - GUESS))
        h = float(H0_DAYS["asked"])
    else:
        p = p0 + (1 - p0) * LEARN[ev]
        if st is None:
            h = float(H0_DAYS[ev])
        elif day != st.last_day:
            h = min(H_MAX, max(st.half_life_days, H0_DAYS[ev]) * (1 + GROWTH * p0))
        else:
            h = max(st.half_life_days, H0_DAYS[ev])
    if st is None:
        return State(p, h, t, day)
    return replace(st, p=p, half_life_days=h, last_at=t, last_day=day)


def fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).casefold()


def is_han(ch: str) -> bool:
    return unicodedata.name(ch, "").startswith("CJK UNIFIED IDEOGRAPH")


def hints(s: dict, listener: str, ent: str, math: str | None, expected: str | None) -> list[str]:
    """Gates knowledge.py does not see, named so a WARN is quick to triage."""
    out = []
    people = {p["key"]: p for p in s["people"]}
    groups = {g["key"]: g for g in d(s, "groups")}
    pr = s["probe"]
    if math is not None and expected is None:
        g = groups.get(ent)
        if g and listener in g["members"]:
            out.append(f"structural: {listener} is a member of {ent}")
        for t in d(s, "ties"):
            if {t["a"], t["b"]} == {listener, ent}:
                out.append(f"structural: direct tie {t['a']}-{t['b']} ({t['kind']})")
        for e in d(s, "edges"):
            if {e["a"], e["b"]} == {listener, ent} and "." not in e["path"]:
                out.append(f"structural: kin distance 1 ({e['a']}->{e['b']} {e['path']})")
        about = [f for f in d(s, "facts") if f["subject"] == ent]
        if about and all(d(f, "third_party") and not d(f, "pinned") for f in about):
            ends = [f["day"] + THIRD_PARTY_TTL_DAYS for f in about]
            if max(ends) <= pr["day"]:
                out.append(f"visibility: third-party facts about {ent} expired by day {max(ends):g} (TTL 120, unpinned)")
        if ent in people:
            text = pr["text"]
            forms = {people[ent]["name"], *d(people[ent], "forms")}
            present = [f for f in forms if f and fold(f) in fold(text)]
            if present and all(len(f) == 1 and is_han(f) for f in present):
                out.append("matcher: only a single-character Han form occurs in the probe (cue rule, ARCHITECTURE 3.2)")
            if not present:
                out.append("no form of the entity occurs in the probe text")
    return out


def knowledge_checks(s: dict) -> list[tuple[bool, str]]:
    """(agrees, line) per checked (listener, entity)."""
    out = []
    people = {p["key"] for p in s["people"]}
    groups = {g["key"] for g in d(s, "groups")}
    pr = s["probe"]
    t_probe = at(pr["day"])
    for listener in pr["participants"]:
        if listener == pr["speaker"]:
            continue
        cards = d(s["expect"].get(listener, {}), "cards")
        expected = {c["key"]: d(c, "gap") for c in cards if c["kind"] in ("who", "what")}
        with_rows = {e["item"]["key"] for e in d(s, "evidence")
                     if e["knower"] == listener and e["item"]["kind"] in ("person", "group")}
        for ent in sorted(set(expected) | with_rows):
            kind = "group" if ent in groups and ent not in people else "person"
            rows = [e for e in d(s, "evidence")
                    if e["knower"] == listener and e["item"]["kind"] == kind and e["item"]["key"] == ent]
            exp = expected.get(ent)
            if exp is None and not rows:
                continue
            st = None
            for e in rows:
                st = update(st, e["ev"], at(e["day"]))
            p = p_now(st, t_probe)
            math = "new" if st is None else ("reminder" if p < FORGOT else None)
            ok = math == exp
            line = (f"{s['id']}: {listener} {kind}:{ent} p={p:.3f} ({len(rows)} rows) "
                    f"math={math or 'none'} expected={exp or 'none'}")
            if not ok:
                h = hints(s, listener, ent, math, exp)
                if h:
                    line += "  [" + "; ".join(h) + "]"
            out.append((ok, line))
    return out


# ---------------------------------------------------------------------------------------------------------------------
# 5. Bridge sanity (ARCHITECTURE 5)
# ---------------------------------------------------------------------------------------------------------------------
def bridge_checks(s: dict) -> list[tuple[bool, str]]:
    out = []
    facts = {f["key"]: f for f in d(s, "facts")}
    pr = s["probe"]
    S = pr["speaker"]
    for listener, ex in s["expect"].items():
        bridges = [c for c in d(ex, "cards") if c["kind"] == "bridge"]
        if len(bridges) > 1:
            out.append((False, f"{s['id']}: {listener} expects {len(bridges)} bridges; the limit is 1 per 90 s"))
        for c in bridges:
            f = facts.get(c["key"])
            if f is None:
                continue
            problems = []
            if S in d(f, "audience") or S in d(f, "told"):
                problems.append(f"{S} already heard it")
            if d(f, "sensitive_kind") and not d(f, "remembered"):
                problems.append("sensitive and not remembered")
            if pr["day"] - f["day"] > 180:
                problems.append("said more than 180 days before the probe")
            for e in d(s, "evidence"):
                if (e["item"]["kind"] == "bridge" and e["item"]["key"] == f["key"] and e["knower"] == listener
                        and d(e, "target") == S and pr["day"] - e["day"] < 7):
                    problems.append(f"bridge logged toward {S} on day {e['day']:g} (7-day rule)")
            line = f"{s['id']}: {listener} bridge:{f['key']} toward {S}"
            out.append((not problems, line + ("  [" + "; ".join(problems) + "]" if problems else " ok")))
    return out


# ---------------------------------------------------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------------------------------------------------
def load(path: Path, extra: bool, fails: list[str]) -> list[dict]:
    rows = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        fails.append(f"{path.name}: cannot read: {e}")
        return rows
    for n, line in enumerate(lines, 1):
        if not line.strip():
            continue
        where = f"{path.name}:{n}"
        try:
            s = json.loads(line)
        except json.JSONDecodeError as e:
            fails.append(f"{where}: JSON: {e}")
            continue
        errs: list[str] = []
        check_model(s, "Scenario", "scenario", errs)
        sid = s.get("id", "?") if isinstance(s, dict) else "?"
        if not errs:
            errs = check_refs(s) + check_testset(s, extra)
        fails.extend(f"{where} {sid}: {e}" for e in errs)
        if not errs:
            rows.append(s)
    return rows


def main(argv: list[str]) -> int:
    verbose = "-v" in argv or "--verbose" in argv
    paths = [Path(a) for a in argv if not a.startswith("-")]
    files = [(p, p.resolve() != BASE_FILE.resolve()) for p in paths] if paths else [(BASE_FILE, False),
                                                                                       (EXTRA_FILE, True)]
    fails: list[str] = []
    loaded = [(p, extra, load(p, extra, fails)) for p, extra in files]

    seen: dict[str, str] = {}
    for p, _, rows in loaded:
        for s in rows:
            if s["id"] in seen:
                fails.append(f"{p.name} {s['id']}: duplicate scenario id (also in {seen[s['id']]})")
            seen.setdefault(s["id"], p.name)

    tag_n: dict[str, Counter] = {}
    kind_n: dict[str, Counter] = {}
    k_checks: list[tuple[bool, str]] = []
    b_checks: list[tuple[bool, str]] = []
    print("Common-ground scenario check (standard library; schema mirrors backend/eval/common_ground/schemas.py)")
    print("files")
    for p, extra, rows in loaded:
        parts = Counter(len(s["probe"]["participants"]) for s in rows)
        empty = sum(1 for s in rows for ex in s["expect"].values() if not d(ex, "cards"))
        listeners = sum(len(s["expect"]) for s in rows)
        shape = ", ".join(f"{k}-person {v}" for k, v in sorted(parts.items()))
        print(f"  {p.name:<24} {len(rows):>3} valid   calls: {shape}   listener slots: {listeners} "
              f"({empty} expect no card)")
        tag_n[p.name] = Counter(t for s in rows for t in s["tags"])
        kind_n[p.name] = Counter(c["kind"] for s in rows for ex in s["expect"].values() for c in d(ex, "cards"))
        for s in rows:
            k_checks += knowledge_checks(s)
            b_checks += bridge_checks(s)

    names = [p.name for p, _, _ in loaded]
    print("expected cards by kind (" + " / ".join(names) + ")")
    kinds = ["who", "what", "ask", "bridge", "storyline", "term"]
    print("  " + "   ".join(f"{k} " + "/".join(str(kind_n[n][k]) for n in names) for k in kinds))
    print("tags (" + " / ".join(names) + ")")
    all_tags = sorted({t for n in names for t in tag_n[n]})
    cells = [f"{t} " + "/".join(str(tag_n[n][t]) for n in names) for t in all_tags]
    line = " "
    for c in cells:
        if len(line) + len(c) + 3 > 118:
            print(line)
            line = " "
        line += "  " + c
    print(line)

    k_bad = [l for ok, l in k_checks if not ok]
    b_bad = [l for ok, l in b_checks if not ok]
    print(f"knowledge checks: {len(k_checks)} run, {len(k_checks) - len(k_bad)} agree, {len(k_bad)} WARN")
    if verbose:
        for ok, l in k_checks:
            if ok:
                print(f"  ok   {l}")
    print(f"bridge checks: {len(b_checks)} run, {len(b_checks) - len(b_bad)} ok, {len(b_bad)} WARN")
    if verbose:
        for ok, l in b_checks:
            if ok:
                print(f"  ok   {l}")
    for l in k_bad + b_bad:
        print(f"WARN {l}")
    for f in fails:
        print(f"FAIL {f}")
    total = sum(len(r) for _, _, r in loaded)
    status = "FAILED" if fails else "OK"
    print(f"result: {status}: {total} scenarios, {len(fails)} failures, {len(k_bad) + len(b_bad)} warnings")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
