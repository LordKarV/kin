# KIN live demo script: Karthik (English) and Nithin (Tamil)

Every line below was rehearsed against the same seed on a throwaway server; the outcomes listed are what came back.
The real accounts have not been used, so every beat is still fresh. After any practice run, re-seed (see the end).

## Setup (once)

- Mac and both iPhones on the same hotspot. Servers running (backend on IPv6, LiveKit dual-stack).
- Each phone: open KIN. Everything is pre-filled (name, language, server, sign-in). Tap **Sign up**.
  If KIN opens straight into an old account: People > gear > **Sign out**, then tap **Sign up**.
- Both phones on the table, screens facing the judges. Keep KIN open on both (it only rings while open).

## What KIN already knows (two months, planted on the dev clock)

| When | What happened | Who heard it |
|---|---|---|
| ~8 weeks ago, call | Nithin: his new friend **Rohan** from the climbing gym | Karthik |
| ~7 weeks ago, call | Nithin: **Ravi mama** (mom's younger brother, Chennai) and **Ravi periyappa** (dad's elder brother, Madurai) | Karthik |
| ~6 and ~4 weeks ago, calls | Nithin's **Adobe internship**: applied, then final round | Karthik |
| ~2 weeks ago, text to KIN | Karthik: **started bouldering at the campus gym** | Nobody (private) |
| Karthik's own | **Mei**: his friend from high school, now in Shanghai | Nobody yet |

## The script (about 3 minutes)

### 0. Before the call (Karthik, 20 s)
- Open People > **Nithin**. Show his world: Rohan (climbing gym), the two Ravis, the Adobe internship thread, each
  with where it came from.
- Open **Messages**: "What KIN understood" shows *started bouldering at the campus gym*, texted, private.
- Say: "KIN builds this from our calls and the occasional text to it. Nithin speaks Tamil, I speak English."

### 1. Ring (5 s)
- Karthik taps **Call** on Nithin. Nithin's phone rings; he taps **Accept**.
- Say: "No links. We're connected, so it's just a call."

### 2. The gap: someone you would have forgotten
- **Nithin:** "டேய், போன வாரம் ரோஹன் கூட Enchanted Rock-ல climbing போனேன்!"
  (*Dei, pona vaaram Rohan kooda Enchanted Rock-la climbing ponen!*: Dude, last week I went climbing at Enchanted
  Rock with Rohan!)
- **Karthik's phone:** English caption, a **Rohan** card mid-sentence ("Nithin's friend Rohan (from the climbing
  gym), first mentioned Aug 30", a reminder), and a private chip: **"You haven't told Nithin: started bouldering at
  the campus gym."**
- **Nithin's phone:** nothing. He knows Rohan.
- Say: "He told me about Rohan two months ago. I'd have nodded along. Different help on each phone, same sentence."

### 3. Silence (the most important beat)
- **Nithin** says the same line again.
- **Both phones:** nothing. Hold the pause for two seconds.
- Say: "I just saw it, so KIN stays quiet. It only speaks when you'd be lost."

### 4. The bridge closes
- **Karthik:** "Wait, I actually started bouldering two weeks ago!"
- **Karthik's phone:** the chip disappears. **Nithin's phone:** the Tamil caption of what Karthik said.
- Say: "Now he's heard it, so KIN never suggests it again. It only ever uses my own news, never his."

### 5. Two people with the same name
- **Nithin:** "ரவி மாமா சென்னையில இருந்து வந்திருக்கார், ரவி பெரியப்பா மதுரையிலேயே இருக்கார்."
  (*Ravi maama Chennai-la irundhu vandhirukkaar, Ravi periyappa Madurai-laye irukkaar*: Ravi mama came from Chennai;
  Ravi periyappa is still in Madurai.)
- **Karthik's phone:** the caption keeps the two Ravis apart, with a card for each.
- Say: "Two uncles named Ravi. A generic translator gets names and relationships wrong 54% of the time on our Tamil
  family test set. With KIN's graph, 1%."

### 6. What it means, not just what it says
- **Nithin:** "சாப்டியா டா? ரொம்ப இளைச்சுட்ட மாதிரி இருக்கே."
  (*Saaptiya da? Romba ilaichutta maadhiri irukke*: Did you eat, man? You look like you've gotten thin.)
- **Karthik's phone:** the caption, plus a meaning card (டா: a familiar "hey, buddy").
- Say: "Tone and culture, not just words."

### 7. Ask without asking: twist the phone
- **Nithin:** "Adobe-ல இருந்து இன்னும் எதுவும் வரல, final round முடிஞ்சு ஒரு மாசம் ஆச்சு."
  (*Adobe-la irundhu innum edhuvum varala, final round mudinju oru maasam aachu*: Still nothing from Adobe; it's
  been a month since the final round.)
- **Karthik:** quick double twist of the wrist. A card tagged **You asked**: **Adobe internship: applied ->
  final round.**
- Or tap **Rohan** in an earlier caption for the same kind of card.
- Say: "If KIN guessed wrong that I remembered, I twist and it fills me in, without Nithin knowing."

### 8. Your world, explained in their language
- **Karthik:** "Mei visited from Shanghai last month and we went hiking at Enchanted Rock."
- **Nithin's phone:** a Tamil caption and a **Tamil card about Mei** (Karthik's school friend, now in Shanghai).
- Say: "It shares only my own facts about Mei, never anything Mei told me."

### 9. Off the record
- **Nithin** taps the **KIN** pill. Both phones: **KIN paused (Nithin)**. Nothing is captioned or saved.
- Tap again to resume.
- Say: "Anyone can take it off the record, and everyone sees it."

### 10. After the call (15 s)
- Karthik: People > Nithin. The Enchanted Rock trip with Rohan is now in his world, with where it came from.
- Delete one item. Say: "You own your world. Deleted means gone."
- Optional: People > gear > change language. "Takes effect on the next call."

### Close
"KIN only speaks when you'd be lost. It decides in two milliseconds, privacy is enforced in code, and with three
months of history an AI given everyone's chats missed 1 card in 5 and leaked a private text. KIN didn't."

## If a judge asks
- **Is the history real?** It was planted on the dev clock to stand in for two months of calls, through the same
  code path a real call or text uses. Everything during the demo is live.
- **Why not just give an AI the whole history?** We tested exactly that: same decisions on short histories, but
  about 2 to 4 s per line, and at three months it missed 5 of 27 cards and leaked private news to two people.

## Reset after a rehearsal
Every card shown changes what KIN thinks you know. To start fresh: stop the backend, move `backend/kin.db*` aside,
start it again, run `cd backend && KIN_BASE='http://[::1]:8000' .venv/bin/python ../scripts/seed_karthik_nithin.py`,
then rebuild both phones with the new tokens (or paste them under Sign up > Server > Sign-in link).
