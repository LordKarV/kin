# Memory loss research for the KIN reframe

Research brief for reframing KIN around older adults whose memory is slipping (age-related recall, mild cognitive
impairment, early-stage dementia). The engine stays the same; each finding below maps to a pitch line or a small
change. Gathered 2026-10-25 from web searches; most claims come from abstracts and secondary summaries, not full
papers. Confidence notes are inline. Do not cite a number in the pitch that is not in this file.

## Scope: who this is for

Older adults with slower recall from age, mild cognitive impairment (MCI), or early-stage dementia, and the family
they call. Not moderate or late dementia: cards need reading, and the memory techniques below lose most of their
benefit at that stage (errorless learning showed no benefit after a 10-minute delay in moderate-to-severe dementia,
MMSE 22 or below). Saying this out loud in the pitch is a strength, not a weakness.

## Numbers for the pitch (checked)

| Claim | Number | Source |
|---|---|---|
| People with dementia worldwide | 57 million (2021) | [WHO](https://www.who.int/mental_health/neurology/dementia/en/) |
| Americans 65+ with Alzheimer's | 7.2 million | [Alzheimer's Association 2025 Facts and Figures](https://www.alz.org/getmedia/c05f7ba4-9aea-4cb0-8898-5e8bff3f0930/executive-summary-2025-alzheimers-disease-facts-and-figures.pdf) |
| Unpaid family caregivers (US) | about 12 million in 2024 (the alz.org fact page says nearly 13 million; cite the year) | same |
| MCI prevalence by age | 10.1% at 70-74, 14.8% at 75-79, 25.2% at 80-84 | [AAN 2018 guideline](https://pubmed.ncbi.nlm.nih.gov/29282327/) (now marked retired on PubMed) |
| MCI to dementia | 14.9% within 2 years, over age 65 | same |
| Preventable share | 45% of dementia linked to 14 modifiable risk factors; social isolation and hearing loss (about 7%) are on the list | [Lancet Commission 2024, via Alzheimer Europe](https://www.alzheimer-europe.org/news/2024-lancet-commission-underscores-potential-dementia-risk-reduction-identifying-14-modifiable) |

Never say KIN lowers dementia risk. Say isolation is a known risk factor and KIN works inside the calls families
already have.

## Findings and what KIN does with each

### 1. Names go first
Tip-of-the-tongue failures rise with age and proper names are the most common target; older adults more often "go
blank" and take longer to recover the word (Burke, MacKay, Worthley and Wade 1991, via
[summary](https://archive.memory-key.com/research/Burke91)). One 2014 study found no proper-noun gap, so say "names
are among the first things to go", not "always first".
- KIN: the "who's that?" card already leads with a name. For memory-support listeners, lead with the relationship:
  "Your granddaughter Priya", then one fact.

### 2. A cue works where recall fails
Craik's environmental support account: age differences are large in free recall, smaller in cued recall, smaller
again in recognition. When the surroundings supply the cue, older adults' deficits shrink
([Rotman-Baycrest chapter](https://rotman-baycrest.on.ca/files/publicationmodule/@random45f5724eba2f8/_ChangesMemoryNormalAgingFunctionalView90_51_201.pdf)).
The exact ordering of cued recall vs recognition is not uniform across studies.
- KIN: a card is that cue, delivered at the moment the name is said. Pitch line: "Older memory is better at
  recognizing than recalling. KIN turns a recall problem into a recognition one."

### 3. Written memory aids improve conversation
Bourgeois's memory wallets and memory books (written sentences about the person's life) increased on-topic and
reduced off-topic talk with familiar partners, across day programs and nursing homes; oral reading is relatively
preserved in dementia, which is why the aids are written
([ASHA Perspectives](https://pubs.asha.org/doi/10.1044/2026_PERSP-26-00045),
[nursing home trial](https://pure.eur.nl/en/publications/memory-aids-as-an-augmentative-and-alternative-communication-stra/)).
Caveat: small studies, mostly from one group; one replication was mixed
([thesis](https://digitalcommons.humboldt.edu/etd/2332)).
- KIN: this is the closest research ancestor. Pitch line: "Speech therapists have used memory wallets for 30
  years. KIN writes the wallet from your calls and opens it to the right page while you talk."

### 4. Never quiz
Caregiver guidance built on the Alzheimer's Association's communication tips: avoid "Do you remember...?" and
"Remember me?", do not correct or argue, offer names and relationships instead
([Ohio State Wexner](https://wexnermedical.osu.edu/blog/how-to-communicate-with-someone-with-dementia),
[Alzheimer's blog](https://www.alzheimersblog.org/2015/09/08/alzheimers-basics-compassionate-commmunication/)).
- KIN: cards to a memory-support listener are statements, never questions. Today an ambiguous name can produce a
  "Which Ravi?" ask card (`backend/app/world/cards.py:150`); suppress it for these listeners and stay silent.
- KIN: do not add a family-side hint like "she has probably forgotten X". It would reveal her lapse to the other
  person, which works against finding 7.

### 5. The main problem is learning, not faster decay
When initial learning is equated, most studies find people with Alzheimer's forget at about the normal rate; the
deficit is mainly encoding (Kopelman 1985, Christensen 1998, an Edinburgh study of 40 patients, via
[search summary](https://www.research.ed.ac.uk/en/publications/forgetting-in-alzheimers-disease-is-it-fast-is-it-affected-by-rep/)).
Exceptions: steeper forgetting in the first hour in MCI due to Alzheimer's (Girtler 2023,
[J Alzheimers Dis](https://content.iospress.com:443/articles/journal-of-alzheimers-disease/jad220803)), and
accelerated long-term forgetting over days to weeks as an early presymptomatic sign (Weston 2018, Lancet Neurology,
[follow-up review](https://pmc.ncbi.nlm.nih.gov/articles/PMC11285641/)).
- KIN: a per-person memory profile should mostly lower the learning rate per exposure (`LEARN`,
  `backend/app/world/knowledge.py:13`) and only modestly shorten the half-life (`H0_DAYS`, line 14). Hearing
  something once should not count as knowing it.
- KIN: "said" evidence (0.95) is too strong for these listeners; saying a name today does not mean recalling it
  in two weeks. Scale it with the rest.
- This is the detail that shows judges we read the research: "We did not just make her forget faster. The research
  says the hard part is taking new things in, so KIN assumes each mention sticks less."

### 6. Spacing works
Spaced retrieval training (recall at growing intervals) is an evidence-based way to teach people with dementia
specific information such as names and faces: a 2005 review of 15 studies (Class II and III evidence), a 2014
meta-analysis of 12 studies ([ASHA evidence map](https://apps.asha.org/EvidenceMaps/Articles/ArticleSummary/d1982e30-ffe9-42d4-bbef-880b2a299df9),
[Oren et al. 2014](https://pubs.asha.org/doi/10.1044/1092-4388(2013/12-0352))). No effect on global cognition.
- KIN: the engine already grows an item's half-life at most once per distinct day of exposure
  (`knowledge.py` docstring, decision D5), so reminders space themselves out as she relearns a name. Pitch line:
  "Reminders space out on their own, the same way spaced-retrieval therapy does." Do not claim therapeutic effect.

### 7. Embarrassment drives withdrawal
Qualitative studies of early-stage dementia report embarrassment, shame and self-blame as daily struggles, with
word-finding trouble as a trigger ([UEA review manuscript](https://ueaeprints.uea.ac.uk/65103/1/Accepted_manuscript.pdf)).
In adults 55+ without dementia, fear of memory loss is linked to avoidance and lower quality of life
([Trinity College Dublin](https://www.tcd.ie/news_events/articles/fear-of-memory-loss-impacts-well-being-and-quality-of-life/)).
- KIN: cards are already private to each listener. Pitch line: "Nobody on the call knows she needed a reminder."

### 8. Errorless beats trial and error, early on
In early Alzheimer's (MMSE 18+), errorless face-name training improved recall of trained names, mostly kept at 6
months (Clare et al. 2002, n=12, [MRC CBU](https://www.mrc-cbu.cam.ac.uk/publications/articles/5216/)). Benefit is
limited in moderate-to-severe dementia.
- KIN: the card lands on the partial transcript (matcher p50 0.15 ms), before she has to guess. This also backs
  the scope statement above.

### 9. Bilingual elders return to their first language
In a UCLA study of 253 Alzheimer's patients, caregivers reported that 66 of 74 bilingual patients (89%) gradually
went back to mostly using their first language
([Mendez 2020, PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC7195235/),
[Stirling](https://www.stir.ac.uk/research/hub/publication/2079218)). Caveat: caregiver report, retrospective.
- KIN: this is what makes the reframe ours and not another dementia memory aid. A grandmother who spoke English
  with her grandkids for 30 years drifts back to Tamil; the grandkids never learned it. KIN gives her Tamil
  captions and cards and gives them English, on the same call. Translation is already built.

### 10. Consent is a process, not a form
Dewing's process consent: consent is revisited throughout, because capacity is task-specific and can change
([Dewing 2008, Research Ethics 4(2)](https://ro.uow.edu.au/smhpapers/2487),
[Frontiers in Dementia 2025](https://frontiersin.org/journals/dementia/articles/10.3389/frdem.2025.1536762/full)).
- KIN: the "KIN on" pill that anyone can pause at any moment is process consent. Set KIN up while she can decide;
  family cannot switch it on silently. Health mentions stay a topic word unless someone taps "remember this"
  (already a hard rule).

## Small changes, in order of value

1. Per-person memory profile: typical, slower recall, memory support. Scales `LEARN` (mainly) and `H0_DAYS`
   (lightly) for that knower in `kn.update`; the one call site is `backend/app/world/live.py:492`. One row in
   Settings next to language. Starting values (not from research, tune with `eval/run_cg`): slower recall learn
   x0.8, half-life x0.8; memory support learn x0.5, half-life x0.6. Test: same mention, same history, the
   memory-support listener gets a reminder and the typical listener does not.
2. No ask cards to memory-support listeners (`cards.py:150`).
3. Relationship-first card text for memory-support listeners ("Your granddaughter Priya").
4. Longer card time on screen and one card at a time for memory-support listeners (iOS card timers). UI choice,
   not from these sources.
5. Stretch, not minor: re-suggest your own news to a memory-support listener after enough time ("You told Paatti
   about your new job on Sep 3; she may not remember"). Today a fact heard once is told forever
   (`backend/app/world/visibility.py:58`, `other not in audience`), and heard-at times per listener are not
   stored.

Same app for everyone: memory support is a setting, not a grandparent mode (PRODUCT.md decided against the mode).

## Reframe language

One-liner: "KIN is a calling app for families when a grandparent's memory starts to slip. It knows what she has
probably forgotten and quietly reminds her, mid-call, in her own language."

Say: built on what the research says helps (cues instead of recall, memory aids in conversation, spacing, never
quizzing); for early memory loss; private to her.

Do not say: treats, slows, therapy, prevents, clinically validated, reduces dementia risk.

## Likely judge questions

- "Isn't this another dementia memory aid?" On Devpost about 1,300 projects mention dementia; most recognize faces,
  answer repeated questions, or keep a companion talking. KIN works inside a real call with family, models what she
  has probably forgotten, speaks her first language, and stays silent otherwise. (Note: a Devpost project named
  "Kin" exists, "A face, a name, and a memory for every text Grandma gets": https://devpost.com/software/kin-xwnemz.)
- "Can someone with dementia consent?" Process consent: she sets it up, sees it is on, pauses it anytime. Early
  stage only.
- "What about later stages?" Not for that. Cards need reading, and the research shows these techniques fade there.
- "Did you test with real patients?" No. The engine eval is synthetic; the design follows published findings,
  listed in this file.
