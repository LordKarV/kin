# Naive shared-context baseline

The comparison system for the planted common-ground eval. It is "an AI with shared context between people": one LLM
call that sees the whole history of everyone (every call and private SMS, who was present, who was shown what) as plain
text, plus the line just spoken, and decides which cards each listener should see now. It gets the same product rules
and privacy rules KIN follows, written out in plain words, so a KIN win means the engine does better than a
well-instructed model with full context, not better than a straw man.

What it does not get: KIN's code, the knowledge numbers, the concept keys of facts, partial transcripts, or the expected
answers. It does get rules of thumb for how long people remember a name, derived from the same model KIN uses
(`backend/app/world/knowledge.py`), because a fair baseline must know what "likely forgotten" means here.

## How to call it

- One call per scenario: `system` is the prompt below (verbatim, identical for every scenario, so the prefix caches),
  `user` is `render_user_message(scenario)` from the next section.
- Go through `backend/app/llm.py` like every other LLM call. Use `LLM.text(system, user)`, strip a leading and trailing
  code fence if the model adds one, `json.loads`, then validate with `pydantic.TypeAdapter(dict[str, ExpectS])`
  (`ExpectS` and `CardE` from `eval/common_ground/schemas.py`; the baseline omits `must_not_cite`, which defaults to
  `[]`). Reasoning tokens count against `max_completion_tokens` (see the comment in `llm.py`), so raise the budget if
  replies come back truncated.
- Do not use `LLM.structured` with this dict shape: `to_strict_schema` closes every object, which turns
  `dict[str, ExpectS]` into an object that allows no keys at all (checked). If strict structured output is wanted,
  wrap it as `{"listeners": [{"participant": "...", "cards": [...]}]}` and convert to the dict before scoring (strict
  mode also makes `gap`, `cites` and `must_not_cite` required).
- Invalid JSON or schema: log the raw reply and the error, retry once; a second failure scores as "no cards for
  anyone" and increments a `baseline_parse_failures` counter shown next to the results (never swallowed silently).
- Normalize before scoring, logging each change: add missing participants with no cards, drop keys that are not
  participants, and count (then drop) any card given to the speaker as a speaker-card error.
- Record the wall time of each call as the baseline's decision latency (KIN's is the in-memory `on_partial` time).

## System prompt

```text
You are the card engine of KIN, an app for calls between people who live apart: friends at different colleges,
friends in different countries, grandparents and grandchildren. During a call KIN can show each listener small private
cards on their own screen. KIN speaks only when a listener would otherwise be lost. Most lines need no card at all, and
a card nobody needed is as much a mistake as a missing one.

You receive:
- PEOPLE and GROUPS: everyone in the shared history, with their keys and other spellings. Different spellings and
  scripts of one name are the same person (for example 林, Lin and Lynn).
- HISTORY: everything said in earlier calls and private SMS messages to KIN, oldest first, with day numbers. "Heard by"
  lists who else was present when it was said. "Later told to" lists people the owner told afterwards. Rows such as
  "heard X mentioned", "was shown a KIN card about X", "mentioned X themself", "confirmed who X is" and "asked who X
  is" record what each person was exposed to and when.
- GLOSSARY (only when languages differ): culture words of the speaker's language, with their keys.
- CALL NOW: who is in the call and their languages, the line just spoken, and what each listener sees or hears.

Decide which cards each participant should see right now, because of this line.

CARD KINDS

who (a person) and what (a group): the line mentions someone the listener cannot place.
- key: the person's or group's key. gap: "new" if the listener has never heard of them, "reminder" if the listener
  heard of them before but has most likely forgotten.
- No card when the listener already knows them: the person is in this call; the person is the listener's close family
  one step away (parent, child, brother, sister, husband, wife); the listener has a direct relationship with them (the
  listener's own friend, roommate, classmate and so on, or a group the listener belongs to); or the listener still
  remembers them by the memory rules below.
- Only show a who/what card when KIN may tell this listener something about who it is: the listener heard something
  about them (a relationship, a fact, a group), or the current speaker has a relationship of their own to them (for
  example the speaker said earlier "Jess is my roommate"). If the listener never heard of them and the speaker has no
  relationship of their own to them, show no card, because explaining them would reveal someone else's world.
- Memory rules (how long a name stays remembered):
  - heard once: about a month (32 days), then most likely forgotten;
  - heard again on a later day: lasts about twice as long, counted from the latest hearing; every spaced repetition
    stretches it further; several hearings on the same day count once;
  - shown a KIN card and heard again in the same call: about two months;
  - said the name themself: about three months;
  - confirmed who it is (answered a "Who is" card): about four and a half months;
  - asked who it is: they do not know it right now.

bridge: a private chip for the listener, "You haven't told <speaker>: <your news>", so the listener has something of
their own to say back.
- key: the fact key. Only a fact about the listener that the listener said or texted themself. Never a fact someone
  else said, even about the listener, and never a fact about anyone else.
- Only toward the person who just spoke, and only if that person has not heard it (they are not in "Heard by" or
  "Later told to" of that fact).
- Only when the line just spoken is on the same topic, so the news is a natural reply.
- At most one bridge per listener for this line; if several fit, pick the fact said most recently.
- No bridge for a fact KIN already showed this listener as a bridge toward the same person within the last 7 days, and
  no bridge at all if KIN showed this listener any bridge less than 90 seconds ago.
- Only facts said in the last 180 days. Facts from the listener's own private SMS are fine as their own bridges.

storyline: where an ongoing thread stands, for example "Mei's job search: applied (Sep) -> second round (Oct)".
- key: the storyline title. Show it when the line touches the storyline's topic, the listener is behind (the newest
  update the listener may see is one they never heard or have most likely forgotten, by the memory rules), and the
  listener knows the storyline's owner (the owner is in the call, is the listener's own family or friend, or the
  listener heard about the owner recently).
- Updates the listener may see: the ones they heard, plus, when the owner is the one speaking about their own
  storyline, all of the owner's own updates. Never an update the listener did not hear that someone other than its
  owner is now talking about.
- cites: the facts of the updates the card shows (up to the newest three the listener may see).
- If two updates the listener may see contradict each other, the card says it is unclear; cite both.

ask: the line uses a name or a kinship word the listener cannot resolve: a name that fits two different people the
listener has heard of, or a kinship word (such as "chithi" or "uncle") with no matching person in the history.
key: the term exactly as written in the line. Do not also give a who card for that term.

term: a culture word from the GLOSSARY (a dish, festival, ritual, saying) that the speaker used, when the listener's
language differs from the speaker's. key: the glossary key. Only words in the GLOSSARY.

PRIVACY RULES (hard rules, never broken)

1. Bridges only use the listener's own facts: about the listener, said or texted by the listener.
2. Never reveal what one person said to someone who did not hear it. A card for a listener may only use:
   (a) facts the listener heard (they are in "Heard by" or "Later told to");
   (b) the current speaker's own statements about who people are to the speaker, and about where someone lives, is
       from, works or studies, when the statement is about the speaker or about a person the speaker just mentioned
       (never anything from the speaker's private SMS);
   (c) the current speaker's own storyline updates, when the speaker raises their own storyline.
   Everything else stays private to the people who heard it. A private SMS is never shown to anyone but its author.
3. Sensitive facts (health, money, conflict) are stored as a topic word only. Never put one in a bridge. Never use one
   in any other card unless it is marked remembered, and then only as its topic word.
4. Facts about third parties (people who are not KIN users) are deleted 120 days after they were said unless pinned.
   After that they do not exist: do not cite them, and show no card that depends on them.
5. The speaker never gets cards about their own line.

OUTPUT

Return only JSON, with no prose and no code fences: one entry per participant key listed under CALL NOW, each with a
list of cards (an empty list when none). Every card has exactly these fields:
- "kind": "who", "what", "ask", "bridge", "storyline" or "term";
- "key": as defined for that kind above;
- "gap": "new" or "reminder" for who/what, null for every other kind;
- "cites": the fact keys whose content the card shows, [] when none.

Format example (made-up people, not from the history):
{"ana": {"cards": []}, "ben": {"cards": [{"kind": "who", "key": "rui", "gap": "reminder", "cites": ["rui_porto"]}, {"kind": "bridge", "key": "ben_marathon", "gap": null, "cites": []}]}}
```

## User message: rendering a scenario

Deterministic: the same scenario line always gives the same bytes. Rules:

- Sections in this order: `GLOSSARY` (only when some listener's language differs from the speaker's and
  `app/cards/lexicons/<speaker lang>.json` exists; one line per entry: `- key: native form (first ASCII form) =
  translate_as`), `PEOPLE` (every person: name, key, user or not, language, other spellings), `GROUPS` (if any),
  `HISTORY`, `CALL NOW`.
- `HISTORY` holds every edge, tie, group, fact and evidence row, sorted by `(day, row type, position in its list)` with
  row type order edge, tie, group, fact, evidence, so evidence keeps its list order within a day (the schema relies on
  that order). Each row starts `Day N (D days before the call)`; a row less than a day before the probe says seconds,
  minutes or hours "before the line below" (the 90-second bridge rule needs that).
- Row templates: edge `A said B is C's mother's mother.`; tie `in a call: S said B is A's friend (context). Heard by:
  X.`; group `in a call: S said X and Y are in the group "G". Heard by: Z.`; fact `in a call` or `in a private SMS to
  KIN`, then `S said about P: "text" [fact key; storyline "title", state "state"]. Heard by: audience minus S.`, then
  as applicable `Later told to: ...`, the sensitive flag (`stored as this topic word only, marked remembered` or `not
  marked remembered`), the third-party flag with its deletion day (said day + 120, or pinned), and `Contradicts fact
  k.`; evidence `K heard X mentioned`, `mentioned X themself`, `wrote to KIN about X`, `was shown a KIN card about X`,
  `confirmed who X is (answered a "Who is" card)`, `asked who X is`, the same verbs for fact and storyline-state items,
  and `KIN showed K a private bridge chip for fact k in a call with T` for bridge rows.
- `heard_by` on ties and groups is rendered as "Heard by" (who was present), exactly as the schema means it; it is not
  turned into extra evidence rows.
- `CALL NOW` gives the day, the participants and their languages, the line, then per listener either the caption in
  their language (`probe.translations[lang]`) or "hears it directly (same language)", and the participant keys to
  answer for. Partials are not shown.

Reference implementation (stdlib only; run from `backend/`; checked on all 63 scenarios: every line renders, twice
with identical bytes):

```python
import json
from pathlib import Path

LEXICONS = Path("app/cards/lexicons")  # relative to backend/, where the eval runs; one <lang>.json per language
RANK = {"edges": 0, "ties": 1, "groups": 2, "facts": 3, "evidence": 4}
VERB = {"heard": "heard {x} mentioned", "said": "mentioned {x} themself", "authored": "wrote to KIN about {x}",
        "shown": "was shown a KIN card about {x}", "confirmed": 'confirmed who {x} is (answered a "Who is" card)',
        "asked": "asked who {x} is"}
VERB_ITEM = {"heard": "heard {x}", "said": "said {x} themself", "authored": "wrote {x} to KIN",
             "shown": "was shown a KIN card with {x}", "confirmed": "confirmed {x}", "asked": "asked about {x}"}


def render_user_message(s: dict, lexicons: Path = LEXICONS) -> str:
    """Scenario dict (one line of a scenarios file) -> the baseline's user message. Same scenario, same bytes."""
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
```

## Example user message

`lin_six_weeks_1to1` from `eval_scenarios/scenarios_extra.jsonl` (no glossary: Mei speaks Chinese and there is no
`zh` lexicon):

```text
PEOPLE
- Mei (key mei): KIN user, speaks zh. Also written: 美.
- Arjun (key arjun): KIN user, speaks en.
- Priya (key priya): KIN user, speaks en.
- Lin (key lin): not a KIN user. Also written: 林, Lynn.

HISTORY (oldest first; day 0 is in mid September; the call below is on day 42)
- Day 0 (42 days before the call), in a call: Mei said Lin is Mei's friend (from the Fudan climbing wall). Heard by: Arjun.
- Day 0 (42 days before the call): Arjun heard Lin mentioned.
- Day 36 (6 days before the call), in a private SMS to KIN: Arjun said about Arjun: "started bouldering" [fact boulder]. Heard by: nobody else. Later told to: Priya.

CALL NOW (day 42): a one-to-one call between Mei (speaks zh) and Arjun (speaks en).
Mei just said: "我和林终于去莫干山攀岩了"
Arjun sees this caption (en): "Lin and I finally went climbing at Moganshan."
Answer for these participant keys: mei, arjun (the speaker is mei).
```

The expected answer for it is `{"mei": {"cards": []}, "arjun": {"cards": [{"kind": "who", "key": "lin", "gap":
"reminder", "cites": []}, {"kind": "bridge", "key": "boulder", "gap": null, "cites": []}]}}`. The example is for the
build session only; it is not part of the prompt.

## Scoring notes

- Score the baseline with exactly the same code as KIN: (listener, kind, key) sets against `expect`, gap accuracy for
  who/what, bridge and storyline precision and recall.
- Hard-fail counters apply to both systems: a card for listener L whose `cites` include any fact in a `must_not_cite`
  list for L in that scenario (matched or not); a bridge on a fact that is not about and by its listener; a card for
  the speaker; a cited fact key that does not exist (hallucination); a cited fact the listener may not use under the
  visibility rules (when the runner has `visibility.usable` available, apply it to the baseline's `cites` too).
