# KIN common-ground eval

Generated 2026-10-25 06:01 UTC by `python -m eval.run_cg`. FORGOT = 0.35. Day 0 = 2026-09-14 12:00 UTC.
KIN made 0 network calls: 83 structured LLM calls (localization, extraction) were blocked and failed closed.
Naive shared-context = one Muse call per scenario with the full plain-text history (eval_scenarios/naive_baseline_prompt.md).

## Base set (n=39)

| Metric | KIN | Naive shared-context |
|---|---|---|
| Gap (who/what) precision | 100% (17/17) | 100% (16/16) |
| Gap (who/what) recall | 94% (17/18) | 89% (16/18) |
| Bridge precision | 100% (4/4) | 100% (4/4) |
| Bridge recall | 100% (4/4) | 100% (4/4) |
| Storyline precision | 100% (3/3) | 100% (4/4) |
| Storyline recall | 75% (3/4) | 100% (4/4) |
| Ask (Who is X?) precision | 100% (1/1) | 50% (1/2) |
| Ask (Who is X?) recall | 50% (1/2) | 50% (1/2) |
| Term precision | n/a (0/0) | n/a (0/0) |
| Term recall | n/a (0/0) | n/a (0/0) |
| Gap-kind accuracy (new vs reminder) | 100% (17/17) | 100% (16/16) |
| Entity kind accuracy (who vs what) | 100% (17/17) | 100% (16/16) |
| Decision latency p50 / p95 (ms) | 0.8 / 7.6 | 1961.3 / 3470.5 |
| Baseline parse failures | n/a | 0 |

| Hard fails | KIN | Naive shared-context |
|---|---|---|
| non-self bridge | 0 | 0 |
| bridge to someone who heard it | 0 | 0 |
| LiveWorld.guard_drops | 0 | n/a |
| SMS fact in a non-author's card | 0 | 0 |
| card cites a must_not_cite fact | 0 | 0 |
| card cites a fact not usable for its listener | 0 | 0 |
| card for the speaker | 0 | 0 |
| cites an unknown fact key | 0 | 0 |

## Extra set (n=24)

| Metric | KIN | Naive shared-context |
|---|---|---|
| Gap (who/what) precision | 100% (9/9) | 100% (9/9) |
| Gap (who/what) recall | 100% (9/9) | 100% (9/9) |
| Bridge precision | 100% (4/4) | 100% (4/4) |
| Bridge recall | 100% (4/4) | 100% (4/4) |
| Storyline precision | 100% (2/2) | 100% (2/2) |
| Storyline recall | 100% (2/2) | 100% (2/2) |
| Ask (Who is X?) precision | n/a (0/0) | n/a (0/0) |
| Ask (Who is X?) recall | n/a (0/0) | n/a (0/0) |
| Term precision | 100% (2/2) | 100% (2/2) |
| Term recall | 100% (2/2) | 100% (2/2) |
| Gap-kind accuracy (new vs reminder) | 100% (9/9) | 100% (9/9) |
| Entity kind accuracy (who vs what) | 89% (8/9) | 100% (9/9) |
| Decision latency p50 / p95 (ms) | 0.8 / 9.2 | 1664.0 / 2715.3 |
| Baseline parse failures | n/a | 0 |

| Hard fails | KIN | Naive shared-context |
|---|---|---|
| non-self bridge | 0 | 0 |
| bridge to someone who heard it | 0 | 0 |
| LiveWorld.guard_drops | 0 | n/a |
| SMS fact in a non-author's card | 0 | 0 |
| card cites a must_not_cite fact | 0 | 0 |
| card cites a fact not usable for its listener | 0 | 0 |
| card for the speaker | 0 | 0 |
| cites an unknown fact key | 0 | 0 |

## Base + extra (n=63)

| Metric | KIN | Naive shared-context |
|---|---|---|
| Gap (who/what) precision | 100% (26/26) | 100% (25/25) |
| Gap (who/what) recall | 96% (26/27) | 93% (25/27) |
| Bridge precision | 100% (8/8) | 100% (8/8) |
| Bridge recall | 100% (8/8) | 100% (8/8) |
| Storyline precision | 100% (5/5) | 100% (6/6) |
| Storyline recall | 83% (5/6) | 100% (6/6) |
| Ask (Who is X?) precision | 100% (1/1) | 50% (1/2) |
| Ask (Who is X?) recall | 50% (1/2) | 50% (1/2) |
| Term precision | 100% (2/2) | 100% (2/2) |
| Term recall | 100% (2/2) | 100% (2/2) |
| Gap-kind accuracy (new vs reminder) | 100% (26/26) | 100% (25/25) |
| Entity kind accuracy (who vs what) | 96% (25/26) | 100% (25/25) |
| Decision latency p50 / p95 (ms) | 0.8 / 7.6 | 1840.6 / 3285.8 |
| Baseline parse failures | n/a | 0 |

| Hard fails | KIN | Naive shared-context |
|---|---|---|
| non-self bridge | 0 | 0 |
| bridge to someone who heard it | 0 | 0 |
| LiveWorld.guard_drops | 0 | n/a |
| SMS fact in a non-author's card | 0 | 0 |
| card cites a must_not_cite fact | 0 | 0 |
| card cites a fact not usable for its listener | 0 | 0 |
| card for the speaker | 0 | 0 |
| cites an unknown fact key | 0 | 0 |

## Latency (KIN on_partial, in memory)

| Latency | p50 ms | p95 ms | n |
|---|---|---|---|
| scenarios, all listeners | 0.12 | 5.47 | 89 |
| scenarios, per listener | 0.11 | 5.47 | 89 |
| synthetic 500 people / 1500 aliases, 8 listeners | 0.68 | 0.76 | 200 |
| synthetic, per listener | 0.08 | 0.10 | 200 |

p95 limit: 10 ms.

## Differences from the expected cards

- co_participant_structural / arjun / entity: expected ['lin'], got []
- tamil_kin_word_unknown / arjun / ask: expected ['சித்தி'], got []
- contradiction_one_audience / arjun / storyline: expected ['family home'], got []
- [extra] group_reminder_what_card / arjun / entity kind for fudan_crew: expected what, got who
- [naive] tie_owner_structural / arjun / entity: expected ['lin'], got []
- [naive] co_participant_structural / arjun / entity: expected ['lin'], got []
- [naive] tamil_kin_word_unknown / arjun / ask: expected ['சித்தி'], got ['chithi']
