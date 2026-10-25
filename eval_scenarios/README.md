# Extra common-ground eval scenarios

Planted "who knows what" situations for the KIN common-ground eval, written to sit next to the build's 39 scenarios in
`backend/eval/common_ground/scenarios.jsonl`. Every scenario here is a one-to-one call (the product focus); the
existing set leans on three-person calls.

| File | What it is |
|---|---|
| `scenarios_extra.jsonl` | 24 scenarios, one `Scenario` (from `backend/eval/common_ground/schemas.py`) per line, same style as the existing file |
| `naive_baseline_prompt.md` | The comparison system: system prompt, deterministic history renderer, wiring and scoring notes |
| `validate.py` | Standard-library checker for both scenario files (format, references, test-set rules, knowledge math) |

## Conventions

- Day 0 is mid September. `validate.py` anchors it at 2026-09-14 12:00 UTC: noon, so a fractional day such as 41.9995
  stays on its UTC date for the once-per-day half-life growth rule (D5). The runner should use the same convention.
- People are written exactly as in the existing file (Mei `zh` with forms `["Mei","美"]`, Kamala Paatti `ta`, Lin as a
  non-user with `["林","Lin","Lynn"]`, and so on). New third parties: Saroja (`["Saroja","சரோஜா"]`), Sato
  (`["佐藤","Sato","Satō"]`), and Amma as in `robotics_bridge_self`.
- Every scenario has exactly 2 participants and the tag `one_to_one`. Existing tags are reused where they fit. In the
  existing file `group` means a three-person call, so it is never used here; the group-entity scenario is tagged
  `what_card`. New tags: `one_to_one`, `demo`, `threshold`, `heard_25_days`, `heard_35_days`, `spacing_growth`,
  `confirmed`, `family`, `kin_structural`, `cross_script`, `bridge_newest`, `bridge_window_over`,
  `other_persons_fact`, `what_card`, `third_party`, `third_party_ttl`, `term`.
- p values below come from `backend/app/world/knowledge.py` (FORGOT = 0.35). The speaker never gets cards.

## What each scenario tests

Forgetting and the demo (Mei and Arjun, Mei speaks Mandarin):

| Scenario | Expected for the listener | What it tests |
|---|---|---|
| `lin_six_weeks_1to1` | Arjun: who `lin` reminder (p 0.280) and bridge `boulder` | The demo as a one-to-one call: Lin forgotten after 42 days; Arjun told Priya, not Mei, about bouldering |
| `lin_next_day_1to1` | none (p 0.878) | Same sentence next day: shown and heard on day 42; bridge logged toward Mei on day 42, inside the 7-day rule |
| `heard_25_days_no_card` | none (p 0.405) | Just inside the one-hearing window |
| `heard_35_days_reminder` | who `lin` reminder (p 0.326) | Just past it (one hearing crosses 0.35 at about 32 days) |
| `heard_twice_spaced_no_card` | none (p 0.490) | Half-life growth: one hearing on day 20 alone gives 0.292, and two hearings without growth give 0.344 (a reminder), so only a correct spacing model passes |
| `cross_script_known_no_card` | none (p 0.617) | 佐藤 / Sato / Satō are one entity; Mei says "Sato" in English six days after Arjun heard of her roommate |

Family, Tamil (Paatti and Arjun):

| Scenario | Expected for the listener | What it tests |
|---|---|---|
| `confirmed_ask_80_days_no_card` | none (p 0.539) | Arjun answered "Who is Saroja?" 80 days ago; `confirmed` has a 90-day half-life |
| `saroja_knee_reminder_sensitive` | Arjun: who `saroja` reminder (p 0.241), cites `saroja_home`, must not cite `saroja_knee` | Story 7: the reminder may say where she lives, never the health detail, even though the line is about her knee |
| `structural_kin_mother_no_card` | none | "Your mom": kin distance 1 is structural; Arjun has no evidence rows at all, so a math-only system says "new" |
| `murukku_term_card` | Arjun: term `murukku` | Lexicon term card from Paatti's Tamil |
| `pongal_term_card` | Arjun: term `pongal_dish` | Same for "I made pongal": the dish, not `sweet_pongal` or `pongal_festival` (see gap 6 below) |
| `hiking_bridge_already_told_paatti` | none | Minimal pair to `hiking_with_mei_bridge`: Arjun already told Paatti about the hike |

Bridges:

| Scenario | Expected for the listener | What it tests |
|---|---|---|
| `intern_bridge_same_language_1to1` | Arjun: bridge `intern` | Story 5 from Priya's side, same language (no MT): Arjun told Mei about the offer, not Priya |
| `bridge_newest_of_two` | Arjun: who `lin` reminder and bridge `shoes` | Two relevant unheard self-facts: one bridge per 90 s, the newest `said_at` wins |
| `bridge_7_day_window_over` | Arjun: who `lin` reminder and bridge `boulder` | Bridge shown toward Mei 12 days ago and still untold: the 7-day suppression is over |
| `other_persons_news_never_bridges` | none | Priya's internship (which Arjun heard) is relevant to Mei's line but is never Arjun's bridge |
| `sensitive_money_never_bridges` | none | Arjun's own money fact matches "student loans" by keyword but is sensitive |

Cross-circle and leak traps:

| Scenario | Expected for the listener | What it tests |
|---|---|---|
| `cross_circle_no_mei_leak_to_paatti` | Paatti: who `mei` new, cites `mei_home_arjun`, must not cite `lin_mei`; no card about Lin | Story 9 with a trap: Arjun's own facts explain Mei; Lin is only in Mei's world, so nothing about her reaches Paatti |
| `third_party_unheard_detail_leak` | none | Priya repeats what Mei told her about Dana; Arjun never heard of Dana and nothing may cite `dana_quit` (Priya's own line already says who Dana is) |

Storylines, groups and third parties:

| Scenario | Expected for the listener | What it tests |
|---|---|---|
| `storyline_behind_1to1` | Arjun: storyline `job search`, cites `job_applied` and `job_second` | The owner raising her own storyline discloses her own states, including one Arjun never heard |
| `storyline_third_party_mention_no_leak` | Arjun: storyline `job search`, cites `job_applied`, must not cite `job_second` | Priya raises Mei's storyline: only the state Arjun heard (p 0.280, a reminder) is usable; Priya is not the owner |
| `group_reminder_what_card` | Arjun: what `fudan_crew` reminder (p 0.236) | A group heard of 50 days ago, said as 复旦小分队 |
| `third_party_ttl_boundary_110_days` | Arjun: who `dana` reminder (p 0.074) | Minimal pair to `third_party_expired`: day 110 is inside the 120-day TTL |
| `priya_roommate_reminder_same_language` | Arjun: who `jess` reminder (p 0.292) | Same-language friends, a roommate heard of 40 days ago |

## Assumptions for the build session to confirm

1. **Groups are carded with kind `what`, key = the group key.** None of the 39 existing scenarios has a `what` card, so
   `group_reminder_what_card` is the only scenario that relies on this.
2. **Term card keys are the plain lexicon key** (`murukku`, `pongal_dish`), per the schema comment "term: lexicon key".
   The engine delivers `lex:ta:murukku`, so the runner should strip the `lex:<lang>:` prefix before comparing.

## Changes from the brief, and why

- `saroja_knee_reminder_sensitive`: the brief's line "சரோஜாவுக்கு கால் வலி இப்போ பரவாயில்லை" does not match Saroja:
  `AliasIndex` accepts a name followed by the rest of its token only when that rest is in the Tamil suffix list, and
  "வுக்கு" is not in it (checked with the wave-1 matcher: no hit). The line is now "சரோஜாக்கு முழங்கால் வலி இப்போ
  பரவாயில்லை" (colloquial dative; "க்கு" is a listed suffix), with "முழங்கால்" (knee) instead of "கால்" (leg) so the
  English caption "Saroja's knee pain is better now." is exact. The lexicon matcher finds no term in it.
- `third_party_ttl_boundary_110_days`: dropped `cites: ["dana_quit"]`. A who card body (ARCHITECTURE 2.3) cites up to
  two IDENTITY facts (tie, lives_in, from, works_at, studies_at) and possibly the first-mention fact; `dana_quit` is a
  `did` fact, so a must-cite on it could fail the engine for a reason unrelated to the TTL. The card and gap are kept.
- `storyline_behind_1to1`: cites both `job_applied` and `job_second` instead of `job_second` alone. The 6.5 body shows
  the last three usable states and `job_applied` is usable (Arjun heard it), so the engine cites both.
- `hiking_bridge_already_told_paatti`: Paatti is in the hike fact's `told`, not its `audience`. She was not on the
  day-10 call; Arjun told her on day 12, which is what `told` records. Both become FactAudience rows, so the
  expectation is the same either way.
- `third_party_unheard_detail_leak`: added the tie Arjun -> Mei, so "Mei's" in the line is structural for Arjun and the
  expectation does not depend on how an unlinked user is treated.
- `cross_script_known_no_card`: tie context "from her Fudan dorm" instead of "her dorm roommate", since the rendering
  already says "Mei's roommate Sato (context)".
- `bridge_newest_of_two` keeps the canonical `boulder` fact (told Priya), so Priya is listed as a person.
- `confirmed_ask_80_days_no_card`: p is 0.5386, which rounds to 0.539 (the brief said 0.538). Same decision.

No other expectation changed: every p value and card in the brief agreed with my own check.

## Contradictions and gaps found in the spec

1. **`co_participant_structural` (existing) against the visibility rules.** Priya says "Mei and Lin went hiking with
   me" and Arjun is expected to get who `lin` new. Under 1.3 and 2.3 rule 4, Lin is not visible to Arjun: the only Lin
   tie is Mei's, heard by Priya, and Priya (the speaker) has no link to Lin. The card can only come from the 2.3 rule 6
   fallback ("Lin, mentioned by Priya") counting as "rendered through the speaker context" in 8.6. If that fallback
   counts, `cross_circle_no_mei_leak_to_paatti` (Lin for Paatti) and `third_party_unheard_detail_leak` (Dana for Arjun)
   should also expect a who card with gap new and no cited facts. If it does not count, `co_participant_structural`
   should expect no card for Arjun. The new scenarios and the baseline prompt follow the strict reading (rule 4 only);
   the build should pick one reading and fix the other side.
2. **Tamil dative after a long vowel.** The standard written form "சரோஜாவுக்கு" never matches a name ending in a long
   vowel, because "வுக்கு" is missing from the Tamil suffix table (`kin_tables` ta `suffixes`). Not fixed here (outside
   this folder); worth adding before the Paatti demo.
3. **Sensitive facts with keys.** 1.2 and 6.2 say a sensitive fact is stored with `keys = []`. `saroja_knee` and
   `loans` keep their keys on purpose (like the existing `sensitive_never_bridges`): planted data that would match the
   line if the `content_ok` gate were missing.
4. **Baseline output and strict mode.** `LLM.structured` runs `to_strict_schema`, which closes every object, so a
   participant-keyed dict cannot be returned that way (checked: `dict[str, ExpectS]` becomes an object with no allowed
   keys). `naive_baseline_prompt.md` says how to wire it (`LLM.text` plus validation, or a list wrapper).
5. **WARN lines in the existing file.** `validate.py` reports five, all in the 39-scenario file, each explained by a gate
   the math does not model: tie owner (`tie_owner_structural`), two group members (`group_member_structural`; note
   Arjun's `said` row decays to 0.349 by day 90, just under FORGOT, so only the structural gate keeps it silent), TTL
   expiry (`third_party_expired`) and the single-character Han cue rule (`cjk_single_char_negative`). None in the extra
   file.
6. **Duplicate lexicon forms.** `pongal_dish` and `pongal_festival` share the form "பொங்கல்". `cards.matcher` keeps the
   first entry for a repeated form, so `pongal_term_card` passes only while `pongal_dish` stays before
   `pongal_festival` in `app/cards/lexicons/ta.json`. The dish is the right reading of "I made pongal", but the engine
   gets it by file order, not by context.

## How I validated

1. Standalone checker (both files):

   ```
   cd eval_scenarios && python3 validate.py
   ```

   Output summary: `scenarios.jsonl` 39 valid, `scenarios_extra.jsonl` 24 valid (all 2-person); expected cards in the
   extra file: who 8, what 1, bridge 4, storyline 2, term 2, ask 0 (34 of 48 listener slots expect no card); knowledge
   checks 42 run, 37 agree, 5 WARN (all in the existing file, see above); bridge checks 8 run, 8 ok;
   `result: OK: 63 scenarios, 0 failures, 5 warnings`. `python3 validate.py scenarios_extra.jsonl` alone: 14 knowledge
   checks agree, 0 warnings. `-v` prints every check that agrees, with its p.

2. The real Pydantic model, read-only, with the existing venv:

   ```
   cd backend && PYTHONPATH=$PWD ../../../backend/.venv/bin/python -c "import json; from eval.common_ground.schemas import Scenario; rows=[Scenario.model_validate(json.loads(l)) for l in open('../eval_scenarios/scenarios_extra.jsonl') if l.strip()]; print('ok', len(rows))"
   ```

   Output: `ok 24`. Also with `load_scenarios` on both files: the `same_language` rule and the translation rule from
   `tests/test_cg_testset.py` hold for all 63, and ids are unique across both files. `pytest tests/test_cg_testset.py`
   still passes (27 passed; the existing file is untouched).

3. Engine pieces from wave 1, run read-only over the 24 probes (scratch script, not committed): `AliasIndex` matches
   every expected who/what entity in its probe (林 after 和, Sato, 复旦小分队, சரோஜா, அம்மா, Jess, Dana, Mei); the
   concept groups of every expected bridge pass the ARCHITECTURE 5 relevance rule (one strong hit); the Tamil lexicon
   matcher gives exactly `murukku` and `pongal_dish` on the two term lines and nothing on the other Paatti lines; p
   values recomputed with `knowledge.py` itself match the table above.

4. `validate.py` against Pydantic on 38 mutations of the first scenario (the 22 from `tests/test_cg_testset.py` plus 16
   more on types, literals, nested unknown keys and kin paths): the same accept or reject on all but two, where
   `validate.py` is deliberately stricter on types (`"user": "yes"` and `"day": "42"` pass Pydantic's lax mode).
