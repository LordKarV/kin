"""Long-history stress mode for the common-ground eval: pad(scenario, months) prepends months of everyday filler.

Deterministic (random.Random seeded with seed and scenario id), no LLM, no network. Filler goes BEFORE the scenario's
own history (days before min(0, earliest scenario day)) and only through the existing Scenario fields:
- per pair of users, CALLS_PER_MONTH calls of 20 to 30 lines (one FactS per line, said by the line's speaker, heard by
  the other), plus TEXTS_PER_MONTH private SMS facts per user; each line in its speaker's language (en/zh/ta, else en);
- "heard" evidence for the filler people each call discusses, so listeners do know some filler entities.
Distractors (keys start with DX): a near-name person per scenario person ("Lina" next to "Lin"), the pair's privately
discussed person (never mentioned to anyone else), and a stale storyline whose later states the listener never heard.

Collision rules keep the scenario's expected cards right: every filler name and line is checked with the engine's
own AliasIndex against the scenario's people/group forms (both directions, probe texts included), and filler concept
keys or storyline titles that would hit the probe are dropped (they would make a filler fact a real bridge).
"""
from __future__ import annotations

import random

from app.world.match import AliasIndex
from eval.common_ground.schemas import Scenario

PAD = "pad_"
DX = "pad_dx_"
CALLS_PER_MONTH = 4
LINES = (20, 30)
TEXTS_PER_MONTH = 10
CAST_PER_PAIR = 4
NEAR_SUFFIXES = ("a", "n", "na", "nka", "ne", "wen", "dsey", "ette")
LINE_GAP = 0.0007  # about a minute between lines of one call
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

# lang -> names (latin, native), places, self lines (topic_en, topic_native, text), third-party lines with {p},
# storyline (title, [(state label, text with {p})]); {pl} = place, {d} = day
V = {
    "en": {
        "names": [("Marcus", "Marcus"), ("Delia", "Delia"), ("Tobias", "Tobias"), ("Renee", "Renee"),
                  ("Hollis", "Hollis"), ("Grace Okafor", "Grace Okafor"), ("Wendell", "Wendell"), ("Bianca", "Bianca"),
                  ("Theo Marsh", "Theo Marsh"), ("Odette", "Odette")],
        "places": ["the Eastside library", "Kessler Hall", "the Maple Street market", "the night bus depot",
                   "Rosa's bakery", "the campus gym"],
        "self": [("class", "class", "my statistics class moved to {d} mornings"),
                 ("exam", "midterm", "the chemistry midterm got pushed back a week"),
                 ("food", "soup", "made a big pot of lentil soup for the week"),
                 ("food", "noodles", "found a decent noodle place near {pl}"),
                 ("weather", "rain", "it rained the whole way to {pl}"),
                 ("weather", "heating", "the heating in the flat is broken again"),
                 ("work", "shift", "picked up an extra shift at {pl} on {d}"),
                 ("work", "report", "my manager wants the quarterly report by {d}"),
                 ("family", "groceries", "I'm doing the grocery run on {d}"),
                 ("family", "bill", "paid the electricity bill, we split it later"),
                 ("class", "lab", "lab ran late again, got home after nine"),
                 ("food", "dinner", "cooked dinner for the flat on {d}")],
        "third": ["{p} is driving everyone to the airport on {d}", "{p} started a new job at {pl}",
                  "{p} lent me a rice cooker", "{p} is visiting family over the long weekend",
                  "{p} can't make dinner on {d}", "{p} keeps losing their keys at {pl}"],
        "story": ("flat move", [("looking at flats", "{p} is looking at flats near {pl}"),
                                ("signed a lease", "{p} signed a lease, finally"),
                                ("settled in", "{p} has moved in and is unpacking")]),
    },
    "zh": {
        "names": [("Wang Hao", "王浩"), ("Chen Jing", "陈静"), ("Zhao Lei", "赵磊"), ("Liu Fang", "刘芳"),
                  ("Zhou Ting", "周婷"), ("Sun Yu", "孙宇"), ("Guo Qiang", "郭强"), ("He Yan", "何燕")],
        "places": ["图书馆", "食堂", "超市", "地铁站", "宿舍楼"],
        "self": [("class", "课", "我的统计课改到{d}早上了"), ("exam", "考试", "化学期中考试推迟了一周"),
                 ("food", "饺子", "周末包了很多饺子"), ("food", "面条", "{pl}旁边有一家不错的面馆"),
                 ("weather", "下雨", "去{pl}的路上一直在下雨"), ("weather", "暖气", "宿舍的暖气又坏了"),
                 ("work", "加班", "这周{d}又要加班"), ("work", "报告", "老板要我{d}之前交报告"),
                 ("family", "买菜", "{d}我去买菜"), ("family", "电费", "电费我先交了，回头再分"),
                 ("class", "实验", "实验又做到很晚")],
        "third": ["{p}{d}开车送大家去机场", "{p}在{pl}找到了新工作", "{p}借给我一个电饭锅",
                  "{p}放假回老家了", "{p}{d}来不了吃饭"],
        "story": ("找房子", [("在看房子", "{p}在{pl}附近看房子"), ("签了租约", "{p}终于签了租约"),
                             ("住进去了", "{p}已经住进去了，在收拾东西")]),
        "days": ("周一", "周二", "周三", "周四", "周五", "周六", "周日"),
    },
    "ta": {
        "names": [("Selvi", "செல்வி"), ("Murugan", "முருகன்"), ("Revathi", "ரேவதி"), ("Kannan", "கண்ணன்"),
                  ("Valli", "வள்ளி"), ("Senthil", "செந்தில்"), ("Bhavani", "பவானி")],
        "places": ["கோவில்", "சந்தை", "பேருந்து நிலையம்", "பள்ளி"],
        "self": [("food", "சாம்பார்", "இன்னைக்கு சாம்பார் வச்சேன்"), ("food", "இட்லி", "காலையில இட்லி செஞ்சேன்"),
                 ("weather", "மழை", "{pl} போற வழியில மழை பெஞ்சுது"), ("weather", "வெயில்", "இன்னைக்கு ரொம்ப வெயில்"),
                 ("family", "காய்கறி", "{d} காய்கறி வாங்கப் போறேன்"), ("family", "கரண்ட் பில்", "கரண்ட் பில் கட்டிட்டேன்"),
                 ("work", "தோட்டம்", "தோட்டத்துல வேலை பார்த்தேன்"), ("class", "பாட்டு", "{d} பாட்டு வகுப்பு இருக்கு")],
        "third": ["{p} {d} ஊருக்கு வர்றாங்க", "{p} {pl}ல புது வேலைக்கு சேர்ந்தாங்க", "{p} எனக்கு ஊறுகாய் கொடுத்தாங்க",
                  "{p} {d} சாப்பிட வர முடியாது"],
        "story": ("வீடு மாற்றம்", [("வீடு பார்க்கிறார்", "{p} {pl} பக்கத்துல வீடு பார்க்கிறாங்க"),
                                   ("ஒப்பந்தம் போட்டார்", "{p} வீட்டுக்கு ஒப்பந்தம் போட்டாங்க"),
                                   ("குடியேறினார்", "{p} புது வீட்டுக்கு குடியேறிட்டாங்க")]),
        "days": ("திங்கள்", "செவ்வாய்", "புதன்", "வியாழன்", "வெள்ளி", "சனி", "ஞாயிறு"),
    },
}


def _v(lang: str) -> dict:
    return V.get(lang, V["en"])


def _lang(lang: str) -> str:
    return lang if lang in V else "en"


class _Guard:
    """The engine's own matcher, both directions: filler must not hit scenario forms or the probe, and vice versa."""

    def __init__(self, sc: Scenario):
        forms = [f for p in sc.people for f in (p.name, *p.forms)] + [f for g in sc.groups for f in (g.name, *g.forms)]
        self.scenario = AliasIndex((f, "x", 0) for f in forms)
        self.langs = sorted({p.lang for p in sc.people} | {""})
        pr = sc.probe
        self.probe = [pr.text, *pr.partials, *pr.translations.values()]
        self.scenario_texts = self.probe + [f.text for f in sc.facts]

    def _hit(self, idx: AliasIndex, texts) -> bool:
        return any(idx.scan(t, lg) for t in texts for lg in self.langs)

    def text_ok(self, text: str) -> bool:
        return not self._hit(self.scenario, [text])

    def name_ok(self, forms: list[str]) -> bool:
        return self.text_ok(" ".join(forms)) and all(self.text_ok(f) for f in forms) and not self._hit(
            AliasIndex((f, "x", 0) for f in forms), self.scenario_texts)

    def key_ok(self, forms: list[str]) -> bool:  # a filler concept that hit the probe would be a real bridge
        return not self._hit(AliasIndex((f, "x", 0) for f in forms), self.probe)


class _Builder:
    def __init__(self, sc: Scenario, rng: random.Random, guard: _Guard):
        self.sc, self.rng, self.g = sc, rng, guard
        self.people: list[dict] = []
        self.facts: list[dict] = []
        self.evidence: list[dict] = []
        self.ties: list[dict] = []
        self.native: dict[str, str] = {}  # filler person key -> native-script form
        self.used: set[str] = set()
        self.n = 0
        self.lang = {p.key: _lang(p.lang) for p in sc.people}

    def person(self, key: str, latin: str, native: str, lang: str) -> str:
        self.people.append({"key": key, "name": latin, "lang": lang, "user": False,
                            "forms": [native] if native != latin else []})
        self.native[key] = native
        self.used.add(latin)
        return key

    def fill(self, tmpl: str, lang: str, p: str | None = None) -> str:
        v, r = _v(lang), self.rng
        name = (self.native[p] if lang != "en" else next(x["name"] for x in self.people if x["key"] == p)) if p else ""
        return tmpl.format(p=name, pl=r.choice(v["places"]), d=r.choice(v.get("days", DAYS)))

    def fact(self, prefix: str, subject: str, speaker: str, text: str, day: float, audience: list[str],
             topic: list[str] | None = None, sms: bool = False, **kw) -> str | None:
        if not self.g.text_ok(text):
            return None  # ponytail: drop a colliding line rather than rewrite it; the guard test pins zero collisions
        self.n += 1
        key = f"{prefix}{self.n}"
        keys = [topic] if topic and self.g.key_ok(topic) else []
        self.facts.append({"key": key, "subject": subject, "speaker": speaker, "predicate": "said", "text": text,
                           "keys": keys, "day": round(day, 4), "source": "sms" if sms else "call",
                           "audience": [speaker] if sms else audience, **kw})
        return key

    def heard(self, knower: str, kind: str, key: str, day: float) -> None:
        self.evidence.append({"knower": knower, "item": {"kind": kind, "key": key}, "ev": "heard", "day": round(day, 4)})


def _cast(b: _Builder, langs: list[str], n: int, tag: str) -> list[str]:
    pool = [(lg, x) for lg in dict.fromkeys(langs) for x in _v(lg)["names"]]
    b.rng.shuffle(pool)
    out = []
    for lg, (latin, native) in pool:
        if len(out) == n:
            break
        if latin not in b.used and b.g.name_ok([latin, native]):
            out.append(b.person(f"{PAD}{tag}_{len(b.people)}", latin, native, lg))
    return out


def _near_names(b: _Builder, users: list[str], start: float) -> None:
    """A different person whose name is close to each scenario person's, well known to every user."""
    for p in b.sc.people:
        base = p.name.split()[0]
        cand = next((base + s for s in NEAR_SUFFIXES if base + s not in b.used and b.g.name_ok([base + s])), None)
        if cand is None:
            continue
        k = b.person(f"{DX}near_{p.key}", cand, cand, "en")
        owner = b.rng.choice(users)
        b.ties.append({"a": owner, "b": k, "kind": "friend", "context": "from the pottery class", "day": start,
                       "said_by": owner, "heard_by": [u for u in users if u != owner]})
        for i in range(3):
            day = start + 5 + i * 9 + b.rng.random()
            sp = b.rng.choice(users)
            others = [u for u in users if u != sp]
            line = b.fill(b.rng.choice(_v(b.lang[sp])["third"]), b.lang[sp], k)
            if b.fact(f"{DX}near_f", k, sp, line, day, others, third_party=True):
                for u in others:
                    b.heard(u, "person", k, day)


def _story(b: _Builder, a: str, other: str, who: str, start: float, span: float) -> None:
    """Stale storyline: state 1 said to `other` in a call; states 2-3 only in a's private texts."""
    title, states = _v(b.lang[a])["story"]
    if not b.g.key_ok([title]):
        return
    for i, (label, tmpl) in enumerate(states):
        day = start + span * (0.2 + 0.3 * i)
        sms = i > 0
        k = b.fact(f"{DX}stale_{a}_{other}_", who, a, b.fill(tmpl, b.lang[a], who), day, [other], sms=sms,
                   third_party=True, storyline={"title": title, "state": label})
        if k and not sms:
            b.evidence.append({"knower": other, "item": {"kind": "state", "key": k}, "ev": "heard", "day": round(day, 4)})


def _calls(b: _Builder, a: str, c: str, cast: list[str], start: float, end: float, months: int) -> None:
    r = b.rng
    for mo in range(months):
        for ci in range(CALLS_PER_MONTH):
            day = start + mo * 30 + ci * 7.5 + r.uniform(0, 3)
            if day >= end:
                continue
            talked: set[str] = set()
            for li in range(r.randint(*LINES)):
                sp, ot = (a, c) if li % 2 == 0 else (c, a)
                lang, at = b.lang[sp], day + li * LINE_GAP
                if r.random() < 0.3 and cast:
                    who = r.choice(cast)
                    if b.fact(f"{PAD}c", who, sp, b.fill(r.choice(_v(lang)["third"]), lang, who), at, [ot],
                              third_party=True):
                        talked.add((ot, who))
                else:
                    en, native, tmpl = r.choice(_v(lang)["self"])
                    b.fact(f"{PAD}c", sp, sp, b.fill(tmpl, lang), at, [ot], list(dict.fromkeys([en, native])))
            for knower, who in sorted(talked):
                b.heard(knower, "person", who, day)


def _texts(b: _Builder, u: str, start: float, end: float, months: int) -> None:
    lang = b.lang[u]
    for _ in range(TEXTS_PER_MONTH * months):
        en, native, tmpl = b.rng.choice(_v(lang)["self"])
        b.fact(f"{DX}sms", u, u, b.fill(tmpl, lang), b.rng.uniform(start, end), [], list(dict.fromkeys([en, native])),
               sms=True)


def pad(sc: Scenario, months: int = 3, seed: int = 0) -> Scenario:
    """A copy of `sc` with `months` of filler history before day min(0, earliest day); expect and probe untouched."""
    if months <= 0:
        return sc
    rng = random.Random(f"{seed}:{sc.id}")
    b = _Builder(sc, rng, _Guard(sc))
    days = [x.day for x in (*sc.facts, *sc.ties, *sc.edges, *sc.groups, *sc.evidence)]
    end = min([0.0, *days]) - 1
    start = end - 30 * months
    users = [p.key for p in sc.people if p.user]
    _near_names(b, users, start)
    for i, a in enumerate(users):
        for c in users[i + 1:]:
            cast = _cast(b, [b.lang[a], b.lang[c]], CAST_PER_PAIR, f"{a}_{c}")
            secret = _cast(b, [b.lang[a]], 1, f"dx_priv_{a}_{c}")  # only ever mentioned between a and c
            _calls(b, a, c, cast + secret, start, end, months)
            if cast:
                _story(b, a, c, cast[0], start, end - start)
        _texts(b, a, start, end, months)
    d = sc.model_dump(mode="json")
    d["tags"] = [*d["tags"], f"padded_{months}m"]
    d["people"] += b.people
    d["ties"] = b.ties + d["ties"]
    d["facts"] = b.facts + d["facts"]
    d["evidence"] = b.evidence + d["evidence"]  # list order is a schema contract: filler first, scenario rows after
    return Scenario.model_validate(d)


def history_size(sc: Scenario) -> tuple[int, int]:
    """(history lines, approx tokens) of the naive baseline's system + user message for this scenario."""
    from eval.run_cg import naive_system, render_user_message  # lazy: run_cg imports this module from main()
    user = render_user_message(sc.model_dump(mode="json"))
    text = naive_system() + user
    # ponytail: ~4 ASCII chars per token, ~1 token per non-ASCII char; swap in a real tokenizer if the number matters
    ascii_n = sum(ch.isascii() for ch in text)
    lines = user.split("\nHISTORY", 1)[1].split("\n\nCALL NOW", 1)[0].count("\n- ")
    return lines, ascii_n // 4 + (len(text) - ascii_n)


def pad_sets(base: list[Scenario], extra: list[Scenario], months: int) -> tuple[list[Scenario], list[Scenario]]:
    """run_cg --pad-months hook: pad both sets and print the naive history size per set."""
    out = []
    for name, xs in (("base", base), ("extra", extra)):
        padded = [pad(s, months) for s in xs]
        if padded:
            sizes = [history_size(s) for s in padded]
            print(f"--pad-months {months}, {name} set (n={len(padded)}): history lines mean "
                  f"{sum(x for x, _ in sizes) / len(sizes):.0f} max {max(x for x, _ in sizes)}; naive prompt approx "
                  f"tokens mean {sum(t for _, t in sizes) / len(sizes):.0f} max {max(t for _, t in sizes)}")
        out.append(padded)
    return out[0], out[1]
