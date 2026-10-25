# Eval brief: planted common-ground scenarios and the naive baseline

Goal: prove KIN is not "an LLM with shared context". We need a test set of planted situations where we know exactly who
knows what, and a naive baseline to compare against. You write the data and the baseline prompt; the build session
wires them into `backend/eval/`.

Check `docs/ARCHITECTURE.md` (evaluation section) first: the build plan may already define a scenario format. If it
does, follow that format exactly instead of the sketch below, and note any field you could not express.

## What we measure

For each scenario and each listener, at a given moment in a call:
- **Gap card precision:** of the cards shown, how many were needed (the listener lacked the context).
- **Gap card recall:** of the moments a listener lacked context, how many got a card.
- **Bridge precision:** bridges shown only for facts about the listener themself, only when relevant to what was just
  said, only when the other person has not heard it.
- **Leaks:** any card or bridge that reveals something the listener should not see (another person's private news, a
  third party's details they did not hear). Target: zero.
- **Decision latency:** KIN decides in milliseconds; the naive baseline needs an LLM call per decision.

## Scenario format sketch (JSON files in `eval_scenarios/`)

One file per scenario, `eval_scenarios/<id>.json`. Keep it plain data:

```json
{
  "id": "lin-six-weeks",
  "description": "Arjun heard about Lin six weeks ago; Priya heard yesterday; Mei is the speaker.",
  "people": [
    {"id": "arjun", "name": "Arjun", "languages": ["en"]},
    {"id": "mei", "name": "Mei", "languages": ["zh", "en"]},
    {"id": "priya", "name": "Priya", "languages": ["en"]}
  ],
  "world": [
    {"id": "lin", "type": "person", "owner": "mei", "names": ["Lin", "林", "Lynn"], "relation": "friend", "context": "Fudan climbing wall"}
  ],
  "history": [
    {"day": 0, "event": "call", "participants": ["mei", "arjun"], "said_by": "mei", "text": "I joined the climbing wall and go with my friend Lin.", "lang": "en", "mentions": ["lin"]},
    {"day": 37, "event": "sms", "author": "arjun", "text": "started bouldering at the campus gym", "self_facts": ["arjun-bouldering"]},
    {"day": 41, "event": "call", "participants": ["mei", "priya"], "said_by": "mei", "text": "林 and I are planning Moganshan.", "lang": "zh", "mentions": ["lin"]}
  ],
  "self_facts": [
    {"id": "arjun-bouldering", "about": "arjun", "text": "Arjun started bouldering", "told": [{"to": "priya", "day": 38}], "topics": ["climbing", "bouldering"]}
  ],
  "probe": {
    "day": 42,
    "participants": ["mei", "arjun", "priya"],
    "said_by": "mei",
    "text": "我和林终于去了莫干山",
    "lang": "zh"
  },
  "expected": {
    "arjun": {"gap_cards": ["lin"], "bridges": ["arjun-bouldering"]},
    "priya": {"gap_cards": [], "bridges": []},
    "mei": {"gap_cards": [], "bridges": []}
  },
  "notes": "Priya heard about Lin yesterday, so no card. Arjun told Priya, not Mei, about bouldering, so Arjun gets the bridge."
}
```

Use the people and stories in `docs/collab/STORIES.md`. Aim for 30 to 50 scenarios covering:
- never heard / heard recently / heard long ago (forgetting) / said it yourself / told by a third person;
- group calls where listeners differ;
- bridges: relevant and unheard (should fire), relevant but already heard (should not), heard by someone else but not
  this person (should fire), facts about someone else (must never fire: leak test), irrelevant topic (should not fire);
- cross-language and cross-script names (林/Lin/Lynn, Tamil names said in English, mixed sentences);
- storyline states and a contradiction (Beijing vs Shanghai);
- family cases (the two Ravis, Paatti) and same-language college friends;
- privacy leak traps: a sensitive topic (health/money) that must not surface, a third party's detail that a listener
  did not hear.

## The naive baseline (write this too)

`eval_scenarios/naive_baseline_prompt.md`: the prompt for the comparison system. It is an LLM given the full shared
history of everyone involved as plain text and the probe line, asked: "Which cards and bridges, if any, should each
listener see now? Return JSON in the expected format." It represents "an AI with shared context between people". Write
it fairly (a reasonable, well-instructed prompt), so beating it means something.

## Done means

- 30 to 50 scenario files that follow the format exactly (validate them: every id referenced exists, days are
  consistent, expected listeners are participants).
- A small `eval_scenarios/README.md`: what each group of scenarios tests, and how you validated the files.
- `eval_scenarios/validate.py`: a standalone script (standard library only) that checks every file against the format
  and prints a summary. Run it and include the output in your summary to the user.
