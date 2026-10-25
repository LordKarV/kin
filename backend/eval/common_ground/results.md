# KIN common-ground eval

Generated 2026-10-25 15:16 UTC by `python -m eval.run_cg`. FORGOT = 0.35. Day 0 = 2026-09-14 12:00 UTC.
KIN made 0 network calls: 16 structured LLM calls (localization, extraction) were blocked and failed closed.
Naive shared-context = one Muse call per scenario with the full plain-text history (eval_scenarios/naive_baseline_prompt.txt); not run (pass --live).

## Base set (n=39)

| Metric | KIN | Naive shared-context |
|---|---|---|
| Gap (who/what) precision | 100% (17/17) | not run (--live) |
| Gap (who/what) recall | 94% (17/18) | not run (--live) |
| Bridge precision | 100% (4/4) | not run (--live) |
| Bridge recall | 100% (4/4) | not run (--live) |
| Storyline precision | 100% (3/3) | not run (--live) |
| Storyline recall | 75% (3/4) | not run (--live) |
| Ask (Who is X?) precision | 100% (1/1) | not run (--live) |
| Ask (Who is X?) recall | 50% (1/2) | not run (--live) |
| Term precision | n/a (0/0) | not run (--live) |
| Term recall | n/a (0/0) | not run (--live) |
| Gap-kind accuracy (new vs reminder) | 100% (17/17) | not run (--live) |
| Entity kind accuracy (who vs what) | 100% (17/17) | not run (--live) |
| Decision latency p50 / p95 (ms) | 1.0 / 6.4 | not run (--live) |
| Baseline parse failures | n/a | not run (--live) |

| Hard fails | KIN | Naive shared-context |
|---|---|---|
| non-self bridge | 0 | not run |
| bridge to someone who heard it | 0 | not run |
| LiveWorld.guard_drops | 0 | n/a |
| SMS fact in a non-author's card | 0 | not run |
| card cites a must_not_cite fact | 0 | not run |
| card cites a fact not usable for its listener | 0 | not run |
| card for the speaker | 0 | not run |
| cites an unknown fact key | 0 | not run |

## Latency (KIN on_partial, in memory)

| Latency | p50 ms | p95 ms | n |
|---|---|---|---|
| scenarios, all listeners | 0.16 | 5.41 | 52 |
| scenarios, per listener | 0.11 | 5.41 | 52 |
| synthetic 500 people / 1500 aliases, 8 listeners | 0.70 | 0.90 | 200 |
| synthetic, per listener | 0.09 | 0.11 | 200 |

p95 limit: 10 ms.

## Differences from the expected cards

- co_participant_structural / arjun / entity: expected ['lin'], got []
- tamil_kin_word_unknown / arjun / ask: expected ['சித்தி'], got []
- contradiction_one_audience / arjun / storyline: expected ['family home'], got []
