"""Common-ground eval (docs/ARCHITECTURE.md 11): gap, bridge and storyline precision/recall, latency, hard fails.

    python -m eval.run_cg [--limit N] [--out path] [--sweep] [--extra file.jsonl] [--live]

Every scenario gets a fresh temp SQLite world written row by row (link_kin and the 6.4 storyline helper from
world/apply.py), knowledge folded from its `evidence` with knowledge.update, then the probe is driven through the real
LiveWorld (join, on_partial, on_final, on_translated). KIN's side never reaches the LLM: LLM.structured raises, so
localization and extraction fail closed and are counted. `--live` adds the naive shared-context baseline
(eval_scenarios/naive_baseline_prompt.txt): one Muse call per scenario through app/llm.py, scored by the same code.

Exits 1 when any KIN hard-fail counter is above 0 or an on_partial p95 is above 10 ms.
"""
from __future__ import annotations

import argparse
import asyncio
import concurrent.futures
import json
import logging
import os
import re
import sys
import tempfile
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from app import config
from app import llm as llm_mod
from app.db import models as m
from app.db.session import init_db, reset_engine, session_scope
from app.world import clock
from app.world import knowledge as kn
from app.world.apply import ApplyCtx, _storyline, form_lang, link_kin, world_slug
from app.world.contracts import FactOut, StoryOut
from app.world.live import LiveWorld
from app.world.match import AliasIndex, fold
from app.world.users import create_user, get_space
from app.world.visibility import usable
from eval.common_ground.schemas import ExpectS, Scenario, load_scenarios

log = logging.getLogger("kin.eval.cg")

ROOT = Path(__file__).resolve().parents[1]  # backend/
REPO = ROOT.parent
DEFAULT_OUT = ROOT / "eval" / "common_ground" / "results.md"
NAIVE_PROMPT = REPO / "eval_scenarios" / "naive_baseline_prompt.txt"
LEXICONS = ROOT / "app" / "cards" / "lexicons"
ANCHOR = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)  # day 0, noon UTC 
SWEEP = [round(0.20 + 0.05 * i, 2) for i in range(7)]
P95_LIMIT_MS = 10.0
CATS = ("entity", "bridge", "storyline", "ask", "term")
CAT_LABEL = {"entity": "Gap (who/what)", "bridge": "Bridge", "storyline": "Storyline", "ask": "Ask (Who is X?)",
             "term": "Term"}
HARD = ("non_self_bridge", "bridge_to_audience", "guard_drops", "sms_leak", "must_not_cite", "unusable_cite",
        "speaker_cards", "hallucinated_cite")
HARD_LABEL = {"non_self_bridge": "non-self bridge", "bridge_to_audience": "bridge to someone who heard it",
              "guard_drops": "LiveWorld.guard_drops", "sms_leak": "SMS fact in a non-author's card",
              "must_not_cite": "card cites a must_not_cite fact", "unusable_cite": "card cites a fact not usable for its listener",
              "speaker_cards": "card for the speaker", "hallucinated_cite": "cites an unknown fact key"}
KIN_EXIT = HARD  # spec 11 + leak traps + the listener-visibility rules (PRODUCT.md)
NAIVE_MAX_TOKENS = 6000  # reasoning tokens count against the budget (llm.py)
NAIVE_WORKERS = 8
_EXPECT = TypeAdapter(dict[str, ExpectS])


def _blocked(*_a, **_k):
    _blocked.calls += 1
    raise llm_mod.StructuredOutputError("eval: KIN runs without the LLM")


_blocked.calls = 0


@dataclass(frozen=True)
class Pred:
    kind: str  # entity | bridge | storyline | ask | term
    key: str
    gap: str | None = None
    cites: tuple[str, ...] = ()
    raw_kind: str = ""  # who | what before the entity merge, so a wrong kind is still reported
    text: str = ""  # what the listener saw (title + body); KIN only, checked for leaked fact text


@dataclass
class Seeded:
    space: int
    call: int
    pid: dict[str, int]
    fid: dict[str, int]
    slug_key: dict[str, str]
    fact_key: dict[int, str]
    story_title: dict[int, str]


@dataclass
class KinRun:
    preds: dict[str, list[Pred]]
    partial_ms: list[float]
    per_listener_ms: list[float]
    decision_ms: float
    guard_drops: int
    usable: object  # (listener key, fact key) -> bool


@dataclass
class Score:
    c: Counter = field(default_factory=Counter)
    decision_ms: list[float] = field(default_factory=list)
    misses: list[str] = field(default_factory=list)

    def merge(self, o: "Score") -> "Score":
        return Score(self.c + o.c, self.decision_ms + o.decision_ms, self.misses + o.misses)


# ---- world setup --------------------------------------------------------------------------------------------------
def day_at(day: float) -> datetime:
    return ANCHOR + timedelta(days=day)


def fresh_db(path: Path) -> None:
    os.environ["DATABASE_URL"] = f"sqlite:///{path}"
    config.get_settings.cache_clear()
    reset_engine()
    init_db()


def _fact(s, space: int, subject: int, speaker: int, predicate: str, text: str, at: datetime, audience, refs=(),
          **kw) -> m.Fact:
    third, pinned = kw.pop("third_party", False), kw.get("pinned", False)
    ttl = timedelta(days=config.get_settings().third_party_ttl_days)
    f = m.Fact(family_id=space, subject_id=subject, speaker_id=speaker, predicate=predicate[:16], text=text[:400],
               said_at=at, third_party=third, expires_at=at + ttl if third and not pinned else None, **kw)
    s.add(f)
    s.flush()
    seen: set[int] = set()
    for p, via in audience:
        if p not in seen:
            seen.add(p)
            s.add(m.FactAudience(fact_id=f.id, person_id=p, via=via, at=at))
    for k, i in dict.fromkeys(refs):
        s.add(m.FactRef(fact_id=f.id, kind=k, ref_id=i))
    s.flush()
    return f


def _people(s, sc: Scenario) -> dict[str, int]:
    pid = {}
    for p in sc.people:
        if p.user:
            _, person, _ = create_user(s, p.name, p.lang)
        else:
            person = m.Person(family_id=get_space(s).id, slug=f"tmp_{p.key}", display_name=p.name)
            s.add(person)
            s.flush()
            person.slug = world_slug("p", p.name, person.id)
        have = {fold(p.name)[0]}
        for form in p.forms:
            if fold(form)[0] not in have:
                have.add(fold(form)[0])
                person.aliases.append(m.Alias(alias=form, lang=form_lang(form, [p.lang] if p.lang else []),
                                              kind="translit"))
        pid[p.key] = person.id
    s.flush()
    return pid


def _refs_in(text: str, sc: Scenario, pid: dict[str, int], subject: str) -> list[tuple[str, int]]:
    # ponytail: refs from a name scan of the fact text (extraction would return them); forms only, no anaphora
    idx = AliasIndex((f, "person", pid[p.key]) for p in sc.people if p.key != subject for f in (p.name, *p.forms))
    return [("person", h.ids[0]) for h in idx.scan(text) if len(h.ids) == 1]


def seed(s, sc: Scenario) -> Seeded:
    pid = _people(s, sc)
    space = s.get(m.Person, pid[sc.people[0].key]).family_id
    users = {p.key for p in sc.people if p.user}
    name = {p.key: p.name for p in sc.people}
    lang = {p.key: p.lang or "en" for p in sc.people}
    slug_key = {s.get(m.Person, i).slug: k for k, i in pid.items()}
    for t in sc.ties:
        f = _fact(s, space, pid[t.a], pid[t.said_by], "tie",
                  f"{name[t.b]} is {name[t.a]}'s {t.kind.replace('_', ' ')} {t.context}".strip(), day_at(t.day),
                  [(pid[t.said_by], "said"), *((pid[h], "heard") for h in t.heard_by)], [("person", pid[t.b])],
                  lang=lang[t.said_by], source_kind="call", third_party=t.a not in users)
        s.add(m.Tie(family_id=space, src_person=pid[t.a], dst_person=pid[t.b], kind=t.kind, context=t.context[:160],
                    fact_id=f.id, created_at=day_at(t.day)))
    for g in sc.groups:
        native = next((x for x in g.forms if fold(x)[0] != fold(g.name)[0]), "")
        row = m.Group(family_id=space, slug=f"tmp_{g.key}", name=g.name, lang_name=native)
        s.add(row)
        s.flush()
        row.slug = world_slug("g", g.name, row.id)
        slug_key[row.slug] = g.key
        f = _fact(s, space, pid[g.said_by], pid[g.said_by], "tie",
                  f"{', '.join(name[x] for x in g.members)} are in {g.name}", day_at(g.day),
                  [(pid[g.said_by], "said"), *((pid[h], "heard") for h in g.heard_by)],
                  [("group", row.id), *(("person", pid[x]) for x in g.members if x != g.said_by)],
                  lang=lang[g.said_by], source_kind="call")
        row.fact_id = f.id
        s.add_all([m.GroupMember(group_id=row.id, person_id=pid[x], fact_id=f.id) for x in g.members])
        pid[g.key] = row.id
    for e in sc.edges:
        link_kin(s, space, pid[e.a], e.path, pid[e.b], me=pid[e.said_by], now=day_at(e.day))
    fid, story = _facts(s, sc, space, pid, lang)
    _knowledge(s, sc, pid, fid, space)
    call = m.Call(family_id=space, mode="world", transport="eval")
    s.add(call)
    s.flush()
    return Seeded(space, call.id, pid, fid, slug_key, {v: k for k, v in fid.items()}, story)


def _facts(s, sc: Scenario, space: int, pid: dict[str, int], lang: dict[str, str]):
    fid: dict[str, int] = {}
    story: dict[int, str] = {}
    for x in sorted(sc.facts, key=lambda f: f.day):  # stable: storyline progression needs said_at order
        sms = x.source == "sms"
        aud = [(pid[x.speaker], "authored" if sms else "said"), *((pid[a], "heard") for a in x.audience),
               *((pid[t], "told") for t in x.told)]
        f = _fact(s, space, pid[x.subject], pid[x.speaker], x.predicate, x.text, day_at(x.day), aud,
                  _refs_in(x.text, sc, pid, x.subject), lang=lang[x.speaker], keys=x.keys,
                  source_kind="message" if sms else "call", sensitive_kind=x.sensitive_kind, remembered=x.remembered,
                  pinned=x.pinned, shareable=not sms, third_party=x.third_party)
        fid[x.key] = f.id
        if x.storyline is not None or x.contradicts is not None:
            fo = FactOut(subject="", predicate=x.predicate, text_en=x.text, text_src="", keys=x.keys, refs=[],
                         lines=[0], sensitive_kind=x.sensitive_kind, same_as=None,
                         contradicts=fid.get(x.contradicts) if x.contradicts else None,
                         storyline=StoryOut(existing_id=None, title=x.storyline.title, state_label=x.storyline.state,
                                            resolved=False) if x.storyline else None)
            ctx = ApplyCtx(space, None, None, {0: pid[x.speaker]}, {0: []}, {}, day_at(x.day))
            _storyline(s, ctx, f, fo, pid[x.speaker], [], "said")  # evidence comes only from scenario rows
            if f.storyline_id is not None:
                story[f.storyline_id] = x.storyline.title
    return fid, story


def _knowledge(s, sc: Scenario, pid: dict[str, int], fid: dict[str, int], space: int) -> None:
    states: dict[tuple[int, str, int], kn.State] = {}
    history = None
    for ev in sc.evidence:  # list order is the schema's contract (shown before heard on one final)
        knower, at = pid[ev.knower], day_at(ev.day)
        if ev.item.kind == "bridge":
            if history is None:
                history = m.Call(family_id=space, mode="world", transport="eval")
                s.add(history)
                s.flush()
            f = fid[ev.item.key]
            s.add(m.CardLog(call_id=history.id, listener_id=knower, target_id=pid[ev.target], kind="bridge",
                            key=f"bridge:{f}", fact_ids=[f], at=at, final=True))
            continue
        if ev.item.kind == "state":
            item = ("state", s.query(m.StorylineState.id).filter(m.StorylineState.fact_id == fid[ev.item.key]).scalar())
        elif ev.item.kind == "fact":
            item = ("fact", fid[ev.item.key])
        else:
            item = (ev.item.kind, pid[ev.item.key])
        k = (knower, *item)
        states[k] = kn.update(states.get(k), ev.ev, at)
    for (knower, kind, item_id), st in states.items():
        s.add(m.Knowledge(knower_id=knower, item_kind=kind, item_id=item_id, p=st.p, half_life_days=st.half_life_days,
                          first_at=st.first_at, last_at=st.last_at, last_day=st.last_day, n_heard=st.n_heard,
                          n_shown=st.n_shown, n_said=st.n_said, n_confirmed=st.n_confirmed, n_asked=st.n_asked))
    s.flush()


# ---- driving KIN --------------------------------------------------------------------------------------------------
def _pred(item: dict, sd: Seeded, cites: tuple[int, ...]) -> Pred:
    key = item["key"]
    ck = tuple(sd.fact_key[f] for f in cites if f in sd.fact_key)
    head, _, rest = key.partition(":")
    text = f"{item.get('title') or ''} {item.get('body') or ''}"
    if head in ("who", "what"):
        return Pred("entity", sd.slug_key.get(rest, rest), item.get("gap"), ck, item.get("kind", head), text)
    if head == "bridge":
        return Pred("bridge", sd.fact_key.get(int(rest), key), None, ck)
    if head == "story":
        return Pred("storyline", sd.story_title.get(int(rest), key), None, ck)
    if head == "ask":
        return Pred("ask", rest, None, ck)
    if head == "lex":
        return Pred("term", rest.partition(":")[2], None, ck)
    return Pred(head, key, None, ck)


def run_kin(sc: Scenario, sd: Seeded) -> KinRun:
    pr = sc.probe
    lang = {p.key: p.lang or "en" for p in sc.people}
    ident = {k: f"p{sd.pid[k]}" for k in pr.participants}
    late: list[tuple[str, dict]] = []

    async def emit(i: str, msg: dict) -> None:
        late.append((i, msg))

    loop = asyncio.new_event_loop()
    w = LiveWorld(sd.call, sd.space, emit, loop)
    try:
        for k in pr.participants:
            w.join(ident[k], sd.pid[k], lang[k])
        sp, n_listeners = ident[pr.speaker], len(pr.participants) - 1
        sends, partial_ms = [], []
        t_all = time.perf_counter()
        for p in pr.partials:
            t0 = time.perf_counter()
            sends.append(w.on_partial(sp, p))
            partial_ms.append((time.perf_counter() - t0) * 1000)
        sends.append(w.on_final(sp, pr.text).sends)
        audience = [sd.pid[k] for k in pr.participants if k != pr.speaker]
        sends.append(w.on_translated(sp, 0, pr.text, pr.translations, audience))
        decision_ms = (time.perf_counter() - t_all) * 1000
        view, delivered, now = w.view, dict(w.delivered), clock.now()
        mentioned = frozenset(h.ids[0] for h in w._final_hits.get(sp, []) if h.kind == "person")
        w.close()
    finally:
        loop.close()
    sends += [{i: [msg]} for i, msg in late]
    preds = {}
    for k in pr.participants:
        items: dict[str, dict] = {}
        for snd in sends:
            for msg in snd.get(ident[k], []):
                if msg["type"] == "glance":
                    items.update({it["key"]: it for it in msg["items"]})
                elif msg["type"] == "glance_retract":
                    items = {key: it for key, it in items.items() if key not in msg["keys"]}
        preds[k] = [_pred(it, sd, delivered[(ident[k], key)].fact_ids if (ident[k], key) in delivered else ())
                    for key, it in items.items()]

    def can_use(listener: str, fact_key: str) -> bool:
        f = view.facts.get(sd.fid.get(fact_key, -1)) if view else None
        return f is not None and usable(f, view.audience.get(f.id, frozenset()), sd.pid[listener],
                                        sd.pid[pr.speaker], mentioned, now)

    return KinRun(preds, partial_ms, [x / max(1, n_listeners) for x in partial_ms], decision_ms,
                  w.guard_drops, can_use)


# ---- scoring (same code for KIN and the baseline) -----------------------------------------------------------------
def expected(sc: Scenario) -> dict[str, list[Pred]]:
    return {k: [_norm(c) for c in ex.cards] for k, ex in sc.expect.items()}


def _norm(c) -> Pred:
    kind = "entity" if c.kind in ("who", "what") else c.kind
    key = fold(c.key)[0].strip() if c.kind == "ask" else c.key
    return Pred(kind, key, c.gap, tuple(c.cites), c.kind)


def score(sc: Scenario, preds: dict[str, list[Pred]], can_use=None, label: str = "") -> Score:
    sco = Score()
    c = sco.c
    facts = {f.key: f for f in sc.facts}
    must_not = {k: {x for card in ex.cards for x in card.must_not_cite} for k, ex in sc.expect.items()}
    exp = expected(sc)
    for listener in sc.probe.participants:
        got = preds.get(listener, [])
        if listener == sc.probe.speaker:
            c["speaker_cards"] += len(got)
            continue
        want = exp.get(listener, [])
        for cat in CATS:
            g = {p.key: p for p in got if p.kind == cat}
            e = {p.key: p for p in want if p.kind == cat}
            c[f"{cat}_tp"] += len(g.keys() & e.keys())
            c[f"{cat}_fp"] += len(g.keys() - e.keys())
            c[f"{cat}_fn"] += len(e.keys() - g.keys())
            if cat == "entity":
                for k in g.keys() & e.keys():
                    c["gap_total"] += 1
                    c["gap_ok"] += g[k].gap == e[k].gap
                    c["kind_ok"] += g[k].raw_kind == e[k].raw_kind
                    if g[k].raw_kind != e[k].raw_kind:
                        sco.misses.append(f"{label}{sc.id} / {listener} / entity kind for {k}: expected "
                                          f"{e[k].raw_kind}, got {g[k].raw_kind}")
            if g.keys() != e.keys():
                sco.misses.append(f"{label}{sc.id} / {listener} / {cat}: expected {sorted(e)}, got {sorted(g)}")
        for p in got:
            _hard(c, sc, facts, must_not, listener, p, can_use)
    return sco


def _hard(c: Counter, sc: Scenario, facts: dict, must_not: dict, listener: str, p: Pred, can_use) -> None:
    speaker = sc.probe.speaker
    if p.kind == "bridge":
        f = facts.get(p.key)
        if f is None or not (f.subject == f.speaker == listener):
            c["non_self_bridge"] += 1
        elif speaker in {f.speaker, *f.audience, *f.told}:
            c["bridge_to_audience"] += 1
    cites = set(p.cites) | ({p.key} if p.kind == "bridge" else set())
    for k in cites:
        f = facts.get(k)
        if f is None:
            c["hallucinated_cite"] += 1
            continue
        if f.source == "sms" and f.speaker != listener:
            c["sms_leak"] += 1
        if k in must_not.get(listener, ()):
            c["must_not_cite"] += 1
        if can_use is not None and not can_use(listener, k):
            c["unusable_cite"] += 1
    if p.text:  # ponytail: substring of the folded fact text; misses paraphrases, catches a body rendered verbatim
        seen = fold(p.text)[0]
        for f in sc.facts:
            if f.key in cites or f.speaker == listener:
                continue
            if fold(f.text)[0] in seen:
                c["sms_leak"] += f.source == "sms"
                c["must_not_cite"] += f.key in must_not.get(listener, ())


# ---- naive shared-context baseline --------------------------------------------------------------------------------
def naive_system(path: Path = NAIVE_PROMPT) -> str:
    """The verbatim system prompt: the ```text block under '## System prompt'."""
    md = path.read_text(encoding="utf-8")
    mt = re.search(r"## System prompt\s*```text\n(.*?)\n```", md, re.S)
    if mt is None:
        raise ValueError(f"no system prompt block in {path}")
    return mt.group(1)


RANK = {"edges": 0, "ties": 1, "groups": 2, "facts": 3, "evidence": 4}
VERB = {"heard": "heard {x} mentioned", "said": "mentioned {x} themself", "authored": "wrote to KIN about {x}",
        "shown": "was shown a KIN card about {x}", "confirmed": 'confirmed who {x} is (answered a "Who is" card)',
        "asked": "asked who {x} is"}
VERB_ITEM = {"heard": "heard {x}", "said": "said {x} themself", "authored": "wrote {x} to KIN",
             "shown": "was shown a KIN card with {x}", "confirmed": "confirmed {x}", "asked": "asked about {x}"}


def render_user_message(s: dict, lexicons: Path = LEXICONS) -> str:
    """Copied from eval_scenarios/naive_baseline_prompt.txt (reference implementation); only the paths changed."""
    people = {p["key"]: p for p in s["people"]}
    groups = {g["key"]: g for g in s.get("groups", [])}
    facts = {f["key"]: f for f in s.get("facts", [])}
    pr = s["probe"]

    def name(k: str) -> str:
        return people[k]["name"] if k in people else f'the group "{groups[k]["name"]}"'

    def names(ks: list[str]) -> str:
        ns = [name(k) for k in ks]
        return "nobody else" if not ns else ns[0] if len(ns) == 1 else ", ".join(ns[:-1]) + " and " + ns[-1]

    def lang(k: str) -> str:
        return people[k].get("lang", "")

    def when(day: float) -> str:
        dt = pr["day"] - day
        if dt <= 0:
            ago = "earlier in this call"
        elif dt < 1:
            sec = dt * 86400
            ago = (f"{round(sec)} seconds" if sec < 120 else f"{round(sec / 60)} minutes" if sec < 7200
                   else f"{round(sec / 3600)} hours") + " before the line below"
        else:
            ago = f"{dt:g} day{'' if dt == 1 else 's'} before the call"
        return f"Day {day:g} ({ago})"

    def edge(x: dict) -> str:
        path = "'s ".join(w.replace("_", " ") for w in x["path"].split("."))
        return f"{when(x['day'])}: {name(x['said_by'])} said {name(x['b'])} is {name(x['a'])}'s {path}."

    def tie(x: dict) -> str:
        ctx = f" ({x['context']})" if x.get("context") else ""
        return (f"{when(x['day'])}, in a call: {name(x['said_by'])} said {name(x['b'])} is {name(x['a'])}'s "
                f"{x['kind']}{ctx}. Heard by: {names(x.get('heard_by', []))}.")

    def group(x: dict) -> str:
        return (f'{when(x["day"])}, in a call: {name(x["said_by"])} said {names(x["members"])} are in the group '
                f'"{x["name"]}". Heard by: {names(x.get("heard_by", []))}.')

    def fact(f: dict) -> str:
        src = "in a call" if f["source"] == "call" else "in a private SMS to KIN"
        tag = f"fact {f['key']}"
        if f.get("storyline"):
            tag += f'; storyline "{f["storyline"]["title"]}", state "{f["storyline"]["state"]}"'
        out = (f'{when(f["day"])}, {src}: {name(f["speaker"])} said about {name(f["subject"])}: "{f["text"]}" '
               f'[{tag}]. Heard by: {names([k for k in f.get("audience", []) if k != f["speaker"]])}.')
        if f.get("told"):
            out += f" Later told to: {names(f['told'])}."
        if f.get("sensitive_kind"):
            out += (f" Sensitive ({f['sensitive_kind']}): stored as this topic word only, "
                    + ("marked remembered." if f.get("remembered") else "not marked remembered."))
        if f.get("third_party"):
            out += (" About a third party (not a KIN user), pinned: kept." if f.get("pinned") else
                    f" About a third party (not a KIN user): deleted on day {f['day'] + 120:g} unless pinned.")
        if f.get("contradicts"):
            out += f" Contradicts fact {f['contradicts']}."
        return out

    def evidence(e: dict) -> str:
        kind, key = e["item"]["kind"], e["item"]["key"]
        if kind == "bridge":
            return (f"{when(e['day'])}: KIN showed {name(e['knower'])} a private bridge chip for fact {key} "
                    f"in a call with {name(e['target'])}.")
        if kind in ("person", "group"):
            x, verbs = name(key), VERB
        elif kind == "state":
            st = facts[key]["storyline"]
            x, verbs = f'the "{st["title"]}" update "{st["state"]}" (fact {key})', VERB_ITEM
        else:
            x, verbs = f"fact {key}", VERB_ITEM
        return f"{when(e['day'])}: {name(e['knower'])} " + verbs[e["ev"]].format(x=x) + "."

    render = {"edges": edge, "ties": tie, "groups": group, "facts": fact, "evidence": evidence}
    rows = sorted((x["day"], RANK[sec], i, render[sec](x)) for sec in RANK for i, x in enumerate(s.get(sec, [])))

    out = []
    sl = lang(pr["speaker"])
    lex_file = lexicons / f"{sl}.json"
    if sl and any(lang(k) != sl for k in pr["participants"]) and lex_file.exists():
        lex = json.loads(lex_file.read_text(encoding="utf-8"))
        out.append(f"GLOSSARY ({lex['language']}; term cards use these keys)")
        for e in lex["entries"]:
            roman = next((f for f in e["forms"] if f.isascii()), "")
            out.append(f"- {e['key']}: {e['forms'][0]}" + (f" ({roman})" if roman else "") + f" = {e['translate_as']}")
        out.append("")
    out.append("PEOPLE")
    for p in s["people"]:
        also = [f for f in p.get("forms", []) if f != p["name"]]
        desc = f"KIN user, speaks {p['lang']}" if p["user"] else "not a KIN user" + (
            f", speaks {p['lang']}" if p.get("lang") else "")
        out.append(f"- {p['name']} (key {p['key']}): {desc}." + (f" Also written: {', '.join(also)}." if also else ""))
    if groups:
        out.append("GROUPS")
        for g in s["groups"]:
            also = [f for f in g.get("forms", []) if f != g["name"]]
            out.append(f"- {g['name']} (key {g['key']})." + (f" Also written: {', '.join(also)}." if also else ""))
    out += ["", f"HISTORY (oldest first; day 0 is in mid September; the call below is on day {pr['day']:g})"]
    out += [f"- {r[3]}" for r in rows] or ["- (nothing yet)"]
    parts = pr["participants"]
    who = ", ".join(f"{name(k)} (speaks {lang(k)})" for k in parts[:-1]) + f" and {name(parts[-1])} (speaks {lang(parts[-1])})"
    kind = "a one-to-one call" if len(parts) == 2 else f"a call with {len(parts)} people"
    out += ["", f"CALL NOW (day {pr['day']:g}): {kind} between {who}.", f'{name(pr["speaker"])} just said: "{pr["text"]}"']
    for k in parts:
        if k == pr["speaker"]:
            continue
        if lang(k) == sl:
            out.append(f"{name(k)} hears it directly (same language).")
        else:
            out.append(f'{name(k)} sees this caption ({lang(k)}): "{pr["translations"][lang(k)]}"')
    out.append(f"Answer for these participant keys: {', '.join(parts)} (the speaker is {pr['speaker']}).")
    return "\n".join(out) + "\n"


def _parse(raw: str) -> dict[str, ExpectS]:
    body = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", raw)
    return _EXPECT.validate_python(json.loads(body))


@dataclass
class NaiveRun:
    preds: dict[str, list[Pred]]
    ms: float
    parse_failures: int
    dropped_keys: int


def naive_decide(sc: Scenario, llm, system: str) -> NaiveRun:
    """One LLM.text call (retry once on bad JSON); a second failure scores as no cards and counts a parse failure."""
    user = render_user_message(sc.model_dump(mode="json"))
    t0 = time.perf_counter()
    parsed, fails = None, 0
    for _attempt in range(2):
        try:
            raw = llm.text(system, user, reasoning_effort="minimal", max_completion_tokens=NAIVE_MAX_TOKENS)
        except Exception as e:  # noqa: BLE001  API errors: logged and scored as a failure, never silently empty
            log.error("naive baseline call failed for %s: %s: %s", sc.id, type(e).__name__, e)
            fails += 1
            continue
        try:
            parsed = _parse(raw)
            break
        except (json.JSONDecodeError, ValidationError) as e:
            log.error("naive baseline reply invalid for %s: %s | raw=%r", sc.id, e, raw[:500])
            fails += 1
    ms = (time.perf_counter() - t0) * 1000
    parts = sc.probe.participants
    dropped = len(set(parsed or {}) - set(parts))
    if dropped:
        log.warning("naive baseline for %s: dropped non-participant keys %s", sc.id, sorted(set(parsed) - set(parts)))
    preds = {k: [_norm(c) for c in (parsed or {}).get(k, ExpectS()).cards] for k in parts}
    return NaiveRun(preds, ms, 1 if parsed is None else 0, dropped)


# ---- runs ---------------------------------------------------------------------------------------------------------
def run_set(scenarios: list[Scenario], tmp: Path, naive: dict[str, NaiveRun] | None, label: str
            ) -> tuple[Score, Score | None, list[float], list[float]]:
    kin, nv = Score(), (Score() if naive is not None else None)
    partial, per_listener = [], []
    for n, sc in enumerate(scenarios):
        fresh_db(tmp / f"{label}{n}.db")
        clock.set_offset_days(0)
        with session_scope() as s:
            sd = seed(s, sc)
        offset = (day_at(sc.probe.day) - datetime.now(timezone.utc)).total_seconds() / 86400
        clock.set_offset_days(offset)  # the probe happens "now" on its scenario day
        try:
            r = run_kin(sc, sd)
        finally:
            clock.set_offset_days(0)
        ks = score(sc, r.preds, r.usable, label)
        ks.c["guard_drops"] += r.guard_drops
        ks.decision_ms.append(r.decision_ms)
        kin = kin.merge(ks)
        partial += r.partial_ms
        per_listener += r.per_listener_ms
        if naive is not None and sc.id in naive:
            nr = naive[sc.id]
            ns = score(sc, nr.preds, r.usable, f"[naive] {label}")
            ns.c["parse_failures"] += nr.parse_failures
            ns.decision_ms.append(nr.ms)
            nv = nv.merge(ns)
    return kin, nv, partial, per_listener


def run_naive(scenarios: list[Scenario]) -> dict[str, NaiveRun]:
    system, llm = naive_system(), llm_mod.get_llm()
    with concurrent.futures.ThreadPoolExecutor(NAIVE_WORKERS) as pool:
        futs = {sc.id: pool.submit(naive_decide, sc, llm, system) for sc in scenarios}
        return {k: f.result() for k, f in futs.items()}


def synthetic_latency(tmp: Path, rounds: int = 200) -> tuple[list[float], list[float]]:
    """on_partial over a 500-person / 1500-alias world with 9 participants (8 listeners), as in test_live_world."""
    fresh_db(tmp / "synthetic.db")
    clock.set_offset_days(0)
    now = clock.now()
    with session_scope() as s:
        users = [create_user(s, f"User{i}", "zh" if i % 2 else "en")[1].id for i in range(9)]
        space = s.get(m.Person, users[0]).family_id
        people = [m.Person(family_id=space, slug=f"p_name{i}", display_name=f"Name{i}",
                           aliases=[m.Alias(alias=a, lang="en", kind="asr") for a in (f"Nick{i}", f"Nm{i}x", f"N{i}q")])
                  for i in range(500)]
        s.add_all(people)
        s.flush()
        for i, p in enumerate(people):
            _fact(s, space, users[i % 9], users[i % 9], "did", f"saw Name{i}", now - timedelta(days=i % 90),
                  [(u, "heard") for u in users], [("person", p.id)], lang="en", source_kind="call")
        call = m.Call(family_id=space, mode="world", transport="eval")
        s.add(call)
        s.flush()
        call_id = call.id
    loop = asyncio.new_event_loop()
    w = LiveWorld(call_id, space, lambda i, msg: asyncio.sleep(0), loop)
    times = []
    try:
        for i, u in enumerate(users):
            w.join(f"p{u}", u, "zh" if i % 2 else "en")
        sp, text = f"p{users[0]}", "I saw Name17 and Nick250 at the gym with Name499 yesterday"
        for _ in range(rounds):
            w.on_partial(sp, text)  # primes the stability gate
            w.sent, w.pending, w.delivered = frozenset(), {}, {}  # full card work on every timed partial
            t0 = time.perf_counter()
            w.on_partial(sp, text)
            times.append((time.perf_counter() - t0) * 1000)
    finally:
        w.close()
        loop.close()
    return times, [t / 8 for t in times]


# ---- report -------------------------------------------------------------------------------------------------------
def pct(sorted_xs: list[float], q: float) -> float:
    return sorted_xs[min(len(sorted_xs) - 1, int(q * len(sorted_xs)))] if sorted_xs else float("nan")


def _ratio(a: int, b: int) -> str:
    return f"{a / b:.0%} ({a}/{b})" if b else "n/a (0/0)"


def metric_rows(sco: Score | None) -> list[str]:
    if sco is None:
        return ["not run (--live)"] * (2 * len(CATS) + 3)
    c = sco.c
    out = []
    for cat in CATS:
        tp, fp, fn = c[f"{cat}_tp"], c[f"{cat}_fp"], c[f"{cat}_fn"]
        out += [_ratio(tp, tp + fp), _ratio(tp, tp + fn)]
    xs = sorted(sco.decision_ms)
    return out + [_ratio(c["gap_ok"], c["gap_total"]), _ratio(c["kind_ok"], c["gap_total"]), f"{pct(xs, .5):.1f} / {pct(xs, .95):.1f}"]


def section(title: str, n: int, kin: Score, nv: Score | None) -> list[str]:
    names = [f"{CAT_LABEL[c]} {w}" for c in CATS for w in ("precision", "recall")]
    names += ["Gap-kind accuracy (new vs reminder)", "Entity kind accuracy (who vs what)", "Decision latency p50 / p95 (ms)", "Baseline parse failures"]
    k = metric_rows(kin) + ["n/a"]
    b = metric_rows(nv) + ([str(nv.c["parse_failures"])] if nv else ["not run (--live)"])
    lines = [f"## {title} (n={n})", "", "| Metric | KIN | Naive shared-context |", "|---|---|---|"]
    lines += [f"| {a} | {x} | {y} |" for a, x, y in zip(names, k, b)]
    lines += ["", "| Hard fails | KIN | Naive shared-context |", "|---|---|---|"]
    lines += [f"| {HARD_LABEL[h]} | {kin.c[h]} | {'n/a' if h == 'guard_drops' else nv.c[h] if nv else 'not run'} |"
              for h in HARD]
    return lines + [""]


def report(sets: list[tuple[str, int, Score, Score | None]], sweep: list[tuple[float, Score]] | None,
           lat: list[tuple[str, list[float]]], meta: list[str], misses: list[str]) -> str:
    lines = ["# KIN common-ground eval", "", *meta, ""]
    for title, n, kin, nv in sets:
        lines += section(title, n, kin, nv)
    if sweep:
        lines += ["## Threshold sweep (knowledge.FORGOT), KIN", "",
                  "| FORGOT | Gap precision | Gap recall | Gap-kind accuracy | Storyline precision | Storyline recall |",
                  "|---|---|---|---|---|---|"]
        for th, sco in sweep:
            c = sco.c
            lines.append(f"| {th:.2f} | {_ratio(c['entity_tp'], c['entity_tp'] + c['entity_fp'])} | "
                         f"{_ratio(c['entity_tp'], c['entity_tp'] + c['entity_fn'])} | {_ratio(c['gap_ok'], c['gap_total'])} | "
                         f"{_ratio(c['storyline_tp'], c['storyline_tp'] + c['storyline_fp'])} | "
                         f"{_ratio(c['storyline_tp'], c['storyline_tp'] + c['storyline_fn'])} |")
        lines.append("")
    lines += ["## Latency (KIN on_partial, in memory)", "", "| Latency | p50 ms | p95 ms | n |", "|---|---|---|---|"]
    for name, xs in lat:
        xs = sorted(xs)
        lines.append(f"| {name} | {pct(xs, .5):.2f} | {pct(xs, .95):.2f} | {len(xs)} |")
    lines += ["", f"p95 limit: {P95_LIMIT_MS:g} ms.", "", "## Differences from the expected cards", ""]
    lines += [f"- {x}" for x in misses] or ["- none"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int, default=None, help="first N scenarios of each set")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--sweep", action="store_true", help="FORGOT 0.20..0.50 P/R table")
    ap.add_argument("--extra", action="append", default=[], help="extra scenario jsonl (validated against Scenario)")
    ap.add_argument("--live", action="store_true", help="also run the naive shared-context baseline (needs MODEL_API_KEY)")
    ap.add_argument("--pad-months", type=int, default=0, help="prepend N months of filler history (eval/long_history.py)")
    a = ap.parse_args(argv)
    out = Path(a.out).resolve()
    if out == (ROOT / "eval" / "results.md").resolve():
        ap.error("eval/results.md belongs to run_eval; pick another --out")
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    os.environ["BRIDGE_RERANK"] = "0"  # score the default engine (D8); the rerank would call the LLM
    os.environ["SEED_SAMPLE_FAMILY"] = "0"
    if not a.live:
        os.environ["MODEL_API_KEY"] = "offline-eval-dummy"
    config.get_settings.cache_clear()
    llm_mod.reset_llm()
    llm_mod.LLM.structured = _blocked  # KIN side: every structured call fails closed (counted below)

    base = load_scenarios()[: a.limit]
    extra = [sc for path in a.extra for sc in load_scenarios(path)][: a.limit]
    if {s.id for s in base} & {s.id for s in extra}:
        ap.error("scenario ids repeat across the base and extra files")
    if a.pad_months:
        from eval.long_history import pad_sets  # lazy: long_history imports this module
        base, extra = pad_sets(base, extra, a.pad_months)
    naive = run_naive(base + extra) if a.live else None

    with tempfile.TemporaryDirectory(prefix="kin-cg-") as tmpd:
        tmp = Path(tmpd)
        kb, nb, part, per = run_set(base, tmp, naive, "")
        sets = [("Base set", len(base), kb, nb)]
        kin_all = kb
        if extra:
            ke, ne, p2, l2 = run_set(extra, tmp, naive, "[extra] ")
            part, per = part + p2, per + l2
            sets.append(("Extra set", len(extra), ke, ne))
            sets.append(("Base + extra", len(base) + len(extra), kb.merge(ke), nb.merge(ne) if nb else None))
            kin_all = kb.merge(ke)
        sweep = None
        if a.sweep:
            sweep, keep = [], kn.FORGOT
            try:
                for th in SWEEP:
                    kn.FORGOT = th
                    sweep.append((th, run_set(base + extra, tmp, None, f"sweep{th}-")[0]))
            finally:
                kn.FORGOT = keep
        syn, syn_per = synthetic_latency(tmp)
    lat = [("scenarios, all listeners", part), ("scenarios, per listener", per),
           ("synthetic 500 people / 1500 aliases, 8 listeners", syn), ("synthetic, per listener", syn_per)]
    meta = [f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by `python -m eval.run_cg`. "
            f"FORGOT = {kn.FORGOT}. Day 0 = {ANCHOR:%Y-%m-%d %H:%M} UTC.",
            f"KIN made 0 network calls: {_blocked.calls} structured LLM calls (localization, extraction) were "
            "blocked and failed closed.",
            "Naive shared-context = one Muse call per scenario with the full plain-text history "
            "(eval_scenarios/naive_baseline_prompt.txt)" + ("." if a.live else "; not run (pass --live).")]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report(sets, sweep, lat, meta, kin_all.misses + [x for _t, _n, _k, nv in sets[:1 + bool(extra)]
                                                                     if nv for x in nv.misses]), encoding="utf-8")
    print(out.read_text(encoding="utf-8"))
    fails = {h: kin_all.c[h] for h in KIN_EXIT if kin_all.c[h]}
    slow = {name: pct(sorted(xs), .95) for name, xs in lat if "all listeners" in name or "8 listeners" in name
            if pct(sorted(xs), .95) > P95_LIMIT_MS}
    if fails or slow:
        print(f"FAIL: hard fails {fails}, p95 over {P95_LIMIT_MS:g} ms {slow}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
