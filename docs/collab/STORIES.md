# Demo cast and stories

Every story we have used while designing KIN, collected in one place. All people are fictional. Use these names and
details in mockups, test scenarios and the demo script so everything lines up.

## The main cast

| Person | Who | Language(s) | Where |
|---|---|---|---|
| **Arjun** | The user. College student. | English (heritage: Tamil, learning) | Austin, UT Austin |
| **Mei** | Arjun's high school friend, now studying in China | Mandarin and English | Shanghai, Fudan University |
| **Priya** | Arjun's friend at a different college; also friends with Mei | English | Atlanta, Georgia Tech |
| **Kamala Paatti** | Arjun's maternal grandmother ("Paatti" = grandma) | Tamil | Madurai, India |

People who appear only inside other people's worlds (third parties, never users):

| Person | Whose world | Details |
|---|---|---|
| **Lin (林)** | Mei's | Mei's friend from the Fudan climbing wall; may be romanized as "Lin" or "Lynn" |
| **Ravi mama** | Arjun's family | Mom's younger brother, lives in Chennai (Adyar); "mama" = maternal uncle in Tamil |
| **Ravi periyappa** | Arjun's family | Dad's elder brother, lives in Coimbatore ("Kovai"); same first name as Ravi mama |
| **Saroja** | Paatti's | Paatti's younger sister, lives on the next street in Madurai; had knee trouble |
| **Divya** | Arjun's family | Arjun's elder sister |

Note: older test data names Arjun's mother "Priya". In new material call the friend "Priya" and Arjun's mother "Amma".

The friend group for the demo is **Arjun, Mei and Priya**: high school friends now at three universities in three
cities.

## Story 1: the six-week gap (the core demo)

- **Call 1, mid September.** Mei (in Mandarin and English) mentions she joined the Fudan climbing wall and keeps going
  with a new friend, Lin. Arjun says "nice" and forgets.
- **Six weeks pass.** Everyone is busy.
- **Call 2, late October, one-to-one (Arjun and Mei).** Mei: "我和林终于去了莫干山" / "Lin and I finally did the
  Moganshan trip." Mei is speaking Mandarin.
  - Arjun's screen: "Lin: Mei's friend from the Fudan climbing wall. She mentioned her Sept 14." Plus the English
    caption of her line.
  - Mei's screen: nothing (it is her own world).
- **The same sentence the next day:** no card. "It only speaks when you would be lost."
- All calls in KIN are designed as one-to-one. A call with more people still works, but it is not a focus.

## Story 2: the bouldering bridge

- Arjun started bouldering three weeks ago. He texted KIN's number "started bouldering at the campus gym" and told
  Priya on a call last week. He never told Mei.
- In Call 2, when Mei talks about climbing, Arjun alone sees a small private chip: "You haven't told Mei: you started
  bouldering." Now he has something of his own to say back.
- Mei sees nothing (bridges are only for their owner). Telling Priya counted only for Priya: KIN knows Mei has not
  heard it.

## Story 3: Mei's job search (a storyline)

- September: Mei says she applied for a summer internship at ByteDance.
- October: Mei mentions the second-round interview.
- Storyline card when it comes up and you are behind: "Mei's job search: applied (Sep) -> second round (Oct)."
- Possible next state: offer, or rejection. Unresolved storylines are flagged.

## Story 4: a contradiction

- In one call Mei says her family moved to Beijing; later she says her parents are "still in Shanghai."
- KIN marks the earlier fact as contradicted or superseded instead of trusting both. Useful for showing the storyline
  and fact-status design (active / resolved / contradicted / superseded).

## Story 5: the internship bridge

- Arjun got an internship offer. He told Priya on Tuesday, not Mei.
- When Mei talks about job hunting on Friday, Arjun sees: "You haven't told Mei: the internship offer."
- Privacy rule this demonstrates: bridges only use facts about Arjun himself, never what Priya told him.

## Story 6: the two Ravis (family, Tamil)

- Paatti says "ரவி நேத்து அடையாறுலேர்ந்து போன் பண்ணான்" ("Ravi called yesterday from Adyar"). That is **Ravi
  mama**, Mom's younger brother (Adyar is his flat in Chennai).
- Later: "ரவி கோவையில புது கடை திறந்திருக்காரு" ("Ravi opened a new shop in Kovai"). That is **Ravi periyappa**, Dad's
  elder brother, in Coimbatore. The respectful verb ending is another clue.
- Generic translation says "Ravi called" both times; KIN names the right uncle. Our eval: generic 54% entity errors,
  KIN 1%.
- The first time KIN hears "Ravi mama" with no Ravi in the graph, it shows "Who is Ravi mama?" with suggestions from
  the Tamil kinship table ("Mom's brother", "Dad's sister's husband"). One tap, and the next mention is grounded.

## Story 7: pongal, Saroja's knee, and cultural meaning (family)

- Paatti mentions pongal (a sweet rice dish and harvest festival) and Saroja's knee (last discussed seven weeks ago).
- Cultural meaning cards: a grandma saying "you've gotten thin" is worry and care, not criticism. The Mandarin
  equivalent from a Chinese grandma: "你最近胖了" ("you've gained weight") is affection, not an insult.

## Story 8: grandparent-side gaps and bridges

- Arjun changed his major to bioengineering in August and joined the robotics team; he told his mom, not Paatti.
  Paatti asks "how is school?". Arjun's bridge: "You haven't told Paatti: the robotics team."
- The same engine works on Paatti's screen if she uses the app: "Arjun changed his major in August (he told you
  then)." Her own news: she is teaching Divya her pongal recipe.

## Story 9: cross-world mention (and a bridge with Paatti)

- In Arjun's call with Paatti, she asks about his friends. Arjun gets a private bridge: "You haven't told Paatti: you
  went hiking with Mei when she visited." That is Arjun's own experience, so it is allowed. Nothing Mei said in her
  own calls is ever suggested.
- Arjun tells Paatti, "Mei and I went hiking when she visited." Paatti does not know Mei.
- Paatti's card, in Tamil: "Mei: Arjun's friend from high school, now in Shanghai."
- Privacy rule: across circles KIN shares only Arjun's own facts (who Mei is to him), never what Mei said in her own
  calls.

## Demo script order (about 2.5 minutes)

All calls are one-to-one. Translation is shown as captions; a translated voice is an optional per-person toggle.

1. Setup in 20 seconds: Arjun adds Mei; nothing pre-seeded.
2. Call 1 with Mei (September): she mentions Lin. Arjun texts KIN "started bouldering" and tells Priya on a call.
3. Call 2 with Mei, six weeks later: Story 1 (Lin card) and Story 2 (bouldering bridge), plus Story 3 if it comes up.
4. Next day, same sentence: silence.
5. 30 seconds with Paatti in Tamil: Story 6 (the two Ravis), Story 9 (the hiking-with-Mei bridge and Paatti's card
   about Mei), and a cultural meaning card.
6. One proof slide: generic 54% vs KIN 1% entity errors; cards shown only when needed vs a naive shared-context
   baseline (the eval in EVAL_SCENARIOS_BRIEF.md).
