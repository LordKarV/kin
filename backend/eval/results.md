# KIN eval results

Generated 2026-10-25 15:15 UTC · model `muse-spark-1.3` · MOCK (no LLM)

## Entity grounding (error rate, lower is better)

| Condition | Overall | Kin terms | Name collisions | Dishes/places | Kin flattening | MT p50 | MT p95 | API errors |
|---|---|---|---|---|---|---|---|---|
| linker-only (no LLM) | 2% (n=150) | 4% (n=54) | 3% (n=32) | 0% (n=41) | 0% | 3 ms | 31 ms | 0 |

## Idiom cards

| Condition | Precision | Recall | TP | FP | FN | n |
|---|---|---|---|---|---|---|
| linker-only (no cards in mock) | n/a | n/a | 0 | 0 | 42 | 83 |

<details><summary>linker-only (no LLM): 3 misses</summary>

| item | span | expected node | output |
|---|---|---|---|
| K16 | மாமா | p_ravi_mama | மாமாவும் மாமியும் Pongal இங்க வர்றாங்க. |
| K16 | மாமி | p_lakshmi | மாமாவும் மாமியும் Pongal இங்க வர்றாங்க. |
| N19 | ரவி | p_ravi_periyappa | your uncle Ravi mama (Mom's younger brother) இந்த வருஷம் ஐம்பத்தேழு வயசு ஆகுது. |

</details>
