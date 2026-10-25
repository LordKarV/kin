# KIN table demo: Karthik (English) and Paatti (Tamil, played by Nithin)

Act it out. Nothing here is a line to read word for word: KIN reacts to the people, places and topics below, so bring
them up in any order, in your own words. The judge holds Karthik's phone and only ever reads English.

## Setup

- Mac and both iPhones on the same hotspot; backend and LiveKit running.
- Each phone: open KIN and tap **Sign up** (everything is pre-filled). If it opens into an old account: People > gear >
  Sign out, then Sign up.
- Hand Karthik's phone to the judge: "You're Karthik, on a call with your grandmother. She only speaks Tamil. Just read
  your screen."

## What KIN already knows (two months, planted on the dev clock)

| Whose | What | Who heard it | When it comes up |
|---|---|---|---|
| Paatti | Ravi mama (Mom's younger brother, Chennai) and Ravi periyappa (Dad's elder brother, Madurai) | Karthik, ~7 weeks ago | A card for each on Karthik's phone |
| Paatti | Saroja, her younger sister in Coimbatore | Karthik, ~6 weeks ago | Card on Karthik's phone |
| Paatti | Cousin Meena (Ravi mama's daughter) got engaged | Karthik, ~6 weeks ago | Storyline card on Karthik's phone |
| Karthik | Mei, his friend from high school, now in Shanghai | Paatti, ~8 weeks ago | Tamil card on Paatti's phone |
| Karthik | Rohan, his friend from the climbing gym | Paatti, ~7 weeks ago | Tamil card on Paatti's phone |
| Karthik | He applied for the Adobe internship | Paatti, ~7 weeks ago | Storyline card on Paatti's phone |
| Karthik | Went hiking with Mei when she visited | Nobody | Chip on Karthik's phone when Paatti asks about his friends |
| Karthik | Started bouldering at the campus gym (texted to KIN) | Nobody | Chip when climbing or the gym comes up |
| Paatti | Joined a bhajan singing group at the temple | Nobody | Chip on Paatti's phone when Karthik talks about friends or music |
| Karthik | Lin, Mei's friend from the Fudan climbing wall | Karthik (from Mei) | Shows in Mei's world in the walkthrough |

Meaning cards fire on their own for Tamil words and sayings: kanna (dear), da, "ilaichutta" (you've gotten thin, which
from a grandmother is care), food, festivals and the rest of the Tamil lexicon.

## A flow that shows everything

1. Paatti greets him, asks if he has eaten, says he looks thin. Karthik's phone: the caption and the care cards.
2. Paatti's family news: Ravi mama came from Chennai, Ravi periyappa is still in Madurai, Meena's engagement, Saroja.
   Karthik's phone: who each person is to him.
3. Paatti asks how his friends are. Karthik's phone: "You haven't told Paatti: went hiking with Mei when she visited."
   The judge says it out loud. Paatti's phone: a Tamil card about Mei. Nithin answers like she now remembers ("Oh,
   Mei! Your friend in Shanghai, right?"); the judge reads that answer in English.
4. Karthik brings up Rohan, climbing, or the Adobe internship (tell her the news). Paatti's phone: Tamil cards for
   what she half-remembers.
5. Karthik asks what she has been up to, or mentions music. Paatti's phone: her own chip about the bhajan group; she
   tells him.
6. Repeat any name from earlier. Nothing appears on either phone: "It only speaks when you'd be lost."
7. After a vague line ("that trip was so nice"), twist the wrist twice for an on-demand card. Tap the KIN pill to pause;
   both phones show who paused.
8. After the call, on Karthik's phone: People > Paatti (her world, and where each fact came from), Mei's world (Lin),
   Messages, delete one item, Settings (name, language).

Rehearsed against this seed on a throwaway server: steps 1, 2 (the two Ravis), 3 and 6. Not yet rehearsed: Saroja,
Meena, Rohan, Adobe and the bhajan chip, which were planted the same way.

## Change things without rebuilding

- Your own news: Messages > text KIN. It becomes a chip for anyone who has not heard it.
- Your name or language: People > gear. Others see the new name; a call in progress keeps the old one.
- Anything said on a call is remembered for the next call.
- More planted context: add it to `more()` in `scripts/seed_karthik_paatti.py`, then run it against the live server
  with `--extend` (phones stay signed in).

## Reset between judges

Every card shown changes what KIN thinks each person knows. To put the planted state back (phones stay signed in;
the restart is required because the server keeps the last call in memory, untested beyond that):

```
kill $(lsof -ti tcp:8000 -sTCP:LISTEN)
cd backend && .venv/bin/python ../scripts/demo_snapshot.py restore
ASR_PROVIDER=muse DEV_ENDPOINTS=1 LIVEKIT_URL='ws://[<Mac IPv6>]:7880' .venv/bin/uvicorn app.main:app --host :: --port 8000
```

From scratch (new sign-ins): stop the backend, move `backend/kin.db*` aside, start it, run
`cd backend && KIN_BASE='http://[::1]:8000' .venv/bin/python ../scripts/seed_karthik_paatti.py`, then
`demo_snapshot.py save`, and paste the printed links under Sign up > Server > Sign-in link on each phone.

## If a judge asks

- **Is the history real?** It was planted on the dev clock to stand in for two months of calls, through the same code
  path a real call or text uses. Everything during the demo is live.
- **Why not just give an AI the whole history?** We tested that: the same decisions on short histories, but about 2 to
  4 s per line, and at three months it missed 5 of 27 cards and leaked private news to two people.
