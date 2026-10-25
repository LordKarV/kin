# KIN demo: Karthik and Nithin, then Karthik and Paatti

Act it out in your own words. KIN only reacts to the people and topics below, so bring them up naturally, in any
order. The world was planted by `scripts/seed_demo.py` (context only; nothing in the app knows this script).

## Setup

- Mac and both iPhones on the hotspot; backend and LiveKit running on the Mac.
- Each phone: open KIN, tap **Sign up** (pre-filled as Karthik / Nithin, both English).

## Part 1: two high school friends (English)

Karthik studies CS at Carnegie Mellon; Nithin is a Turing Scholar at UT. They catch up on a call.

What KIN already knows (planted ~7 weeks ago, so each has probably forgotten):
- Nithin told Karthik about **Rohan**, his friend from the UT climbing gym, and that he **applied to Jane Street**.
- Karthik told Nithin about **Priya**, his robotics project partner at CMU.
- Karthik has news he has told nobody: he **started bouldering** at the CMU wall, and he is **flying to Austin for
  HackTX**.

Talking points and what each phone shows:
1. Nithin mentions going climbing with Rohan. Karthik's phone: who Rohan is (and when he first heard), plus a private
   chip: "You haven't told Nithin: started bouldering at the CMU climbing wall." Karthik tells him; the chip goes.
2. Nithin brings up Jane Street (heard back, superday, offer). Karthik's phone: where that thread stood ("applied").
3. Karthik talks about his project with Priya. Nithin's phone: who Priya is.
4. A minute or two later (chips are at least 90 s apart), Nithin asks if Karthik is doing any hackathons. Karthik's
   phone: "You haven't told Nithin: is flying to Austin for HackTX."
5. Repeat a name from earlier. Nothing shows on either phone: it only speaks when you'd be lost.
6. Optional: after a vague line, twist the wrist twice for a card about what you're talking about. Tap the KIN pill to
   pause; both phones show who paused.

Keep out of Part 1: Mei, Ravi, Saroja, Meena, music or singing. Those belong to Part 2.

## Switch (on stage, 15 s)

Hang up. On Nithin's phone: People > gear > name **Paatti**, language **Tamil**, save both. Call again. (Name and
language take effect on the next call.) Say: "Now the harder case: my grandmother. She speaks Tamil, I don't, and her
memory isn't what it was."

## Part 2: Karthik and his grandmother (Paatti speaks Tamil, Karthik English)

What KIN already knows:
- Paatti told Karthik about his two uncles named Ravi: **Ravi mama** (Mom's younger brother, Chennai) and **Ravi
  periyappa** (Dad's elder brother, Madurai), her sister **Saroja** in Coimbatore, and that cousin **Meena** got
  engaged.
- Karthik told Paatti about **Mei**, his roommate at CMU from Shanghai, about 8 weeks ago.
- Karthik went **hiking with Mei** when she visited; Paatti hasn't heard. Paatti **joined a bhajan group** at the
  temple; Karthik hasn't heard.

Talking points:
1. Paatti greets him: "kanna", has he eaten, he's gotten thin. Karthik's phone: English caption plus what "kanna" and
   "you've gotten thin" mean from a grandmother (care).
2. Paatti's family news: Ravi mama came from Chennai, Ravi periyappa is in Madurai; Meena's wedding; Saroja.
   Karthik's phone: which Ravi is which, who Saroja is, where Meena's wedding stands.
3. Paatti asks how his friends are (in Tamil). Karthik's phone: "You haven't told Paatti: went hiking with Mei when
   she visited home." He tells her. Paatti's phone: a Tamil card on who Mei is. Paatti answers like she remembers
   ("Oh, Mei! Your roommate from Shanghai?"); Karthik reads it in English.
4. Karthik asks if she's still singing. Paatti's phone: her own chip about the bhajan group; she tells him.
5. Repeat a name. Nothing shows.

## After the call (walkthrough on Karthik's phone)

People > Paatti: her world and where each fact came from. Karthik's own world (Mei, Priya). Messages: text KIN some
news live; it becomes a chip for anyone who hasn't heard. Delete an item. Settings: name and language.

## Not rehearsed

This seed has not been played end to end (the rehearsal run hit a network change). The same mechanisms were rehearsed
on the earlier seed: reminder cards, bridges, the Tamil Mei card, care cards, silence. Try one quick call first.

## Reset between runs

Every card shown changes what KIN thinks each person knows. Restore the planted state (phones stay signed in;
restart required):

```
kill $(lsof -ti tcp:8000 -sTCP:LISTEN)
cd backend && .venv/bin/python ../scripts/demo_snapshot.py restore
ASR_PROVIDER=muse DEV_ENDPOINTS=1 LIVEKIT_URL='ws://[<Mac IPv6>]:7880' .venv/bin/uvicorn app.main:app --host :: --port 8000
```

Then set Nithin's name and language back if you changed them. If the hotspot address changes, the phones need a
rebuild (the server address is baked in).
