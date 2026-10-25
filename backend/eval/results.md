# KIN eval results

Generated 2026-10-25 00:06 UTC · model `muse-spark-1.3` · live

## Entity grounding (error rate, lower is better)

| Condition | Overall | Kin terms | Name collisions | Dishes/places | Kin flattening | MT p50 | MT p95 | API errors |
|---|---|---|---|---|---|---|---|---|
| linker-only (no LLM) | 2% (n=150) | 4% (n=54) | 3% (n=32) | 0% (n=41) | 0% | 2 ms | 24 ms | 0 |
| generic (same model + same context, no family graph) | 54% (n=150) | 72% (n=54) | 97% (n=32) | 24% (n=41) | 36% | 1793 ms | 4127 ms | 0 |
| grounded (KIN) | 1% (n=150) | 4% (n=54) | 0% (n=32) | 0% (n=41) | 0% | 3015 ms | 4800 ms | 0 |

## Idiom cards

| Condition | Precision | Recall | TP | FP | FN | n |
|---|---|---|---|---|---|---|
| generic | 90% | 86% | 36 | 4 | 6 | 83 |
| grounded (KIN) | 100% | 83% | 35 | 0 | 7 | 83 |

<details><summary>linker-only (no LLM): 3 misses</summary>

| item | span | expected node | output |
|---|---|---|---|
| K16 | மாமா | p_ravi_mama | மாமாவும் மாமியும் Pongal இங்க வர்றாங்க. |
| K16 | மாமி | p_lakshmi | மாமாவும் மாமியும் Pongal இங்க வர்றாங்க. |
| N19 | ரவி | p_ravi_periyappa | your uncle Ravi mama (Mom's younger brother) இந்த வருஷம் ஐம்பத்தேழு வயசு ஆகுது. |

</details>

<details><summary>generic (same model + same context, no family graph): 81 misses</summary>

| item | span | expected node | output |
|---|---|---|---|
| K01 | மாமா | p_ravi_mama | Your uncle called yesterday. |
| K02 | பெரியப்பா | p_ravi_periyappa | Periyappa bought a new machine for the shop. |
| K03 | அத்தை | p_meena | My aunt is coming from Singapore next month. |
| K04 | மாமி | p_lakshmi | I heard a lot of kids have joined Maami's class. |
| K05 | அக்கா | p_divya | Your sister is really busy at the hospital, I hear. |
| K06 | மகன் | p_ravi_mama | My son's coming to Madurai this week. |
| K07 | தங்கச்சி | p_saroja | My younger sister is laid up with knee pain. |
| K11 | சின்ன பாட்டி | p_saroja | Little Granny is knitting you a sweater. |
| K12 | மாமா பையன் | p_karthik | My cousin scored a century in the cricket match. |
| K13 | பெரியப்பா பையனுக்கு | p_vishnu | Elder uncle's son is getting married next year. |
| K13 | கல்யாணம் | ev_vishnu_wedding | Elder uncle's son is getting married next year. |
| K14 | விஷ்ணு | p_vishnu | Your older brother Vishnu said you must definitely come to the wedding. |
| K15 | கார்த்திக் | p_karthik | Karthik is just like you — he just won't study. |
| K16 | மாமா | p_ravi_mama | Uncle and aunty are coming here for Pongal. |
| K16 | மாமி | p_lakshmi | Uncle and aunty are coming here for Pongal. |
| K17 | அப்பாவோட அண்ணன் | p_ravi_periyappa | Your dad's elder brother is the one who runs a shop in Coimbatore. |
| K18 | அம்மாவோட தம்பி | p_ravi_mama | Your uncle got promoted at the bank. |
| K19 | பாப்பா | p_priya | When she was little, Pappa would only eat rasam rice. |
| K20 | சின்னு | p_divya | When is Chinnu coming on leave? |
| K21 | ஊரு | pl_madurai_house | Grandson, when are you coming to our hometown? |
| K22 | மாமா | p_ravi_mama | Uncle says he'll buy you a new phone. |
| K23 | பெரியப்பா | p_ravi_periyappa | I heard Periyappa's sugar is high — tell him to be careful. |
| K24 | அத்தை | p_meena | Auntie sent you chocolate from Singapore. |
| K25 | அக்கா | p_divya | Your sister's on night shift, she's not sleeping at all. |
| K26 | மாமி | p_lakshmi | Auntie made payasam and sent it over, it was really good. |
| K28 | கோவில் | pl_meenakshi_kovil | Your mom used to come to the temple with me every day when she was little. |
| K29 | மருமகள் | p_lakshmi | My daughter-in-law is a really good girl, she'll always make sure you're fed. |
| K30 | மாப்பிள்ளை | p_senthil | My son-in-law's birthday is next month. |
| K31 | பெரியப்பா | p_ravi_periyappa | It's not your younger uncle, it's your elder uncle who lives in Coimbatore. |
| K32 | திவ்யா | p_divya | Granddaughter Divya has become a doctor, you study hard too. |
| K33 | கார்த்திக் | p_karthik | Uncle's son Karthik turned sixteen. |
| K34 | மீனா | p_meena | Your aunt Meena will help you with the visa. |
| K36 | மாமா | p_ravi_mama | Your uncle got beaten a lot by Grandpa when he was little. |
| K37 | பெரியப்பா | p_ravi_periyappa | Is everyone well at uncle's house? |
| K38 | அக்கா | p_divya | I'd be really happy if you and your sister came together. |
| K39 | சின்ன பாட்டி | p_saroja | Chinna Patti's house is just on the next street, she'll check in every day. |
| K40 | மாமி | p_lakshmi | Mami's Bharatanatyam class has its arangetram next month. |
| K41 | பொண்ணு | p_priya | My daughter spoiled you rotten. |
| K42 | தம்பி | p_ravi_mama | Your mom doesn't have an elder sister, she only has a younger brother. |
| N01 | ரவி | p_ravi_mama | Ravi called from Adyar yesterday. |

</details>

<details><summary>grounded (KIN): 2 misses</summary>

| item | span | expected node | output |
|---|---|---|---|
| K16 | மாமா | p_ravi_mama | Mama and mami are coming here for Pongal. |
| K16 | மாமி | p_lakshmi | Mama and mami are coming here for Pongal. |

</details>
