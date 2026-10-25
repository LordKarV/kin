# KIN common-ground eval

Generated 2026-10-25 06:31 UTC by `python -m eval.run_cg`. FORGOT = 0.35. Day 0 = 2026-09-14 12:00 UTC.
KIN made 0 network calls: 124 structured LLM calls (localization, extraction) were blocked and failed closed.
Naive shared-context = one Muse call per scenario with the full plain-text history (eval_scenarios/naive_baseline_prompt.md).

## Base set (n=39)

| Metric | KIN | Naive shared-context |
|---|---|---|
| Gap (who/what) precision | 100% (17/17) | 100% (14/14) |
| Gap (who/what) recall | 94% (17/18) | 78% (14/18) |
| Bridge precision | 100% (4/4) | 80% (4/5) |
| Bridge recall | 100% (4/4) | 100% (4/4) |
| Storyline precision | 100% (3/3) | 67% (4/6) |
| Storyline recall | 75% (3/4) | 100% (4/4) |
| Ask (Who is X?) precision | 100% (1/1) | 50% (1/2) |
| Ask (Who is X?) recall | 50% (1/2) | 50% (1/2) |
| Term precision | n/a (0/0) | n/a (0/0) |
| Term recall | n/a (0/0) | n/a (0/0) |
| Gap-kind accuracy (new vs reminder) | 100% (17/17) | 100% (14/14) |
| Entity kind accuracy (who vs what) | 100% (17/17) | 100% (14/14) |
| Decision latency p50 / p95 (ms) | 2.7 / 8.5 | 4423.7 / 7955.7 |
| Baseline parse failures | n/a | 0 |

| Hard fails | KIN | Naive shared-context |
|---|---|---|
| non-self bridge | 0 | 0 |
| bridge to someone who heard it | 0 | 0 |
| LiveWorld.guard_drops | 0 | n/a |
| SMS fact in a non-author's card | 0 | 2 |
| card cites a must_not_cite fact | 0 | 0 |
| card cites a fact not usable for its listener | 0 | 2 |
| card for the speaker | 0 | 0 |
| cites an unknown fact key | 0 | 0 |

## Extra set (n=24)

| Metric | KIN | Naive shared-context |
|---|---|---|
| Gap (who/what) precision | 100% (9/9) | 100% (8/8) |
| Gap (who/what) recall | 100% (9/9) | 89% (8/9) |
| Bridge precision | 100% (4/4) | 67% (4/6) |
| Bridge recall | 100% (4/4) | 100% (4/4) |
| Storyline precision | 100% (2/2) | 100% (2/2) |
| Storyline recall | 100% (2/2) | 100% (2/2) |
| Ask (Who is X?) precision | n/a (0/0) | n/a (0/0) |
| Ask (Who is X?) recall | n/a (0/0) | n/a (0/0) |
| Term precision | 100% (2/2) | 100% (2/2) |
| Term recall | 100% (2/2) | 100% (2/2) |
| Gap-kind accuracy (new vs reminder) | 100% (9/9) | 100% (8/8) |
| Entity kind accuracy (who vs what) | 89% (8/9) | 100% (8/8) |
| Decision latency p50 / p95 (ms) | 2.0 / 6.8 | 3678.9 / 7168.9 |
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
| Gap (who/what) precision | 100% (26/26) | 100% (22/22) |
| Gap (who/what) recall | 96% (26/27) | 81% (22/27) |
| Bridge precision | 100% (8/8) | 73% (8/11) |
| Bridge recall | 100% (8/8) | 100% (8/8) |
| Storyline precision | 100% (5/5) | 75% (6/8) |
| Storyline recall | 83% (5/6) | 100% (6/6) |
| Ask (Who is X?) precision | 100% (1/1) | 50% (1/2) |
| Ask (Who is X?) recall | 50% (1/2) | 50% (1/2) |
| Term precision | 100% (2/2) | 100% (2/2) |
| Term recall | 100% (2/2) | 100% (2/2) |
| Gap-kind accuracy (new vs reminder) | 100% (26/26) | 100% (22/22) |
| Entity kind accuracy (who vs what) | 96% (25/26) | 100% (22/22) |
| Decision latency p50 / p95 (ms) | 2.0 / 7.2 | 4164.0 / 7286.1 |
| Baseline parse failures | n/a | 0 |

| Hard fails | KIN | Naive shared-context |
|---|---|---|
| non-self bridge | 0 | 0 |
| bridge to someone who heard it | 0 | 0 |
| LiveWorld.guard_drops | 0 | n/a |
| SMS fact in a non-author's card | 0 | 2 |
| card cites a must_not_cite fact | 0 | 0 |
| card cites a fact not usable for its listener | 0 | 2 |
| card for the speaker | 0 | 0 |
| cites an unknown fact key | 0 | 0 |

## Latency (KIN on_partial, in memory)

| Latency | p50 ms | p95 ms | n |
|---|---|---|---|
| scenarios, all listeners | 0.13 | 5.23 | 89 |
| scenarios, per listener | 0.11 | 5.23 | 89 |
| synthetic 500 people / 1500 aliases, 8 listeners | 0.70 | 0.74 | 200 |
| synthetic, per listener | 0.09 | 0.09 | 200 |

p95 limit: 10 ms.

## Differences from the expected cards

- co_participant_structural / arjun / entity: expected ['lin'], got []
- tamil_kin_word_unknown / arjun / ask: expected ['சித்தி'], got []
- contradiction_one_audience / arjun / storyline: expected ['family home'], got []
- [extra] group_reminder_what_card / arjun / entity kind for fudan_crew: expected what, got who
- [naive] tie_owner_structural / arjun / entity: expected ['lin'], got []
- [naive] co_participant_structural / arjun / entity: expected ['lin'], got []
- [naive] cross_circle_no_own_fact / paatti / entity: expected ['mei'], got []
- [naive] cross_circle_own_fact / paatti / entity: expected ['mei'], got []
- [naive] tamil_kin_word_unknown / arjun / ask: expected ['சித்தி'], got ['chithi']
- [naive] sms_only_fact_private / mei / storyline: expected [], got ['internship']
- [naive] sms_only_fact_private / priya / storyline: expected [], got ['internship']
- [naive] non_self_fact_never_bridges / arjun / bridge: expected [], got ['pad_dx_sms609']
- [naive] [extra] cross_circle_no_mei_leak_to_paatti / paatti / entity: expected ['mei'], got []
- [naive] [extra] murukku_term_card / arjun / bridge: expected [], got ['pad_dx_sms368']
- [naive] [extra] pongal_term_card / arjun / bridge: expected [], got ['pad_dx_sms362']
