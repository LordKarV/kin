# KIN launch film: plan and shot list

A 2:20 product launch film for the Devpost video field. It is shot with real people on real calls through the real
iOS app, then edited like a product launch: a cold open, the reveal, feature beats in use, one number, one privacy
promise, the close. Cast details are in CASTING.md; rules in RULES.md.

## Length and format

- HackTX publishes no video length limit (see RULES.md). Target 2:20, hard cap 3:00.
- 16:9, 1080p, 30 fps. Phone screen recordings are composited into the frame next to or over the camera footage.
- Upload as a public YouTube video. Burned-in English subtitles for all spoken lines, so it works muted.

## What has to be true on screen

- Every card, chip and caption on a phone screen was produced live by KIN on the real server during the take. No
  mockups, no captions typed in the edit, no redrawn cards.
- The six-week gap is simulated with the dev clock, and the film says so on screen.
- A beat whose code does not run end to end at the go/no-go check is cut, not faked. The minimum film is listed at
  the end.
- The proof number is 54% vs 1% (backend/eval/results.md). PRODUCT.md and STORIES.md say 53%; that is a typo. The
  gap-precision number against a naive shared-context baseline is not measured yet, so it is not in the film unless
  someone builds and runs that eval before the edit locks.
- Never show: photos popping up on a mention, call reminders, follow-up nudges, topic lists, Wikipedia pictures, a
  family-tree archive. Those read as Nudge, Roots or HeirLoom.

## App state recipe (how to set up each shot)

Server: one fresh database (delete the old `kin.db`), `DEV_ENDPOINTS=true` (the default in `app/config.py`),
`CLOCK_OFFSET_DAYS=0`. Dev routes from docs/ARCHITECTURE.md section 9:

- `POST /api/dev/clock {offset_days}` sets the world clock offset.
- `POST /api/dev/apply {speaker, audience, update}` plants call extraction through the same apply path.
- `POST /api/dev/sms {from, body}` ingests a text as if Twilio delivered it.
- `POST /api/calls/{id}/text {text}` types a line into a live call (backup for ASR misses).

Status check, 2026-10-24: `backend/app/api/dev.py` has the `/api/dev` router but no routes yet, and `app/api/sms.py`
and `app/api/world.py` are empty routers. Confirm all four routes exist before the shoot. Without the clock route,
restart the server with `CLOCK_OFFSET_DAYS=42` between call 1 and call 2 (the setting is read at startup).

| State | Clock offset | How to get there | Backup |
|---|---|---|---|
| S0 empty | 0 | Create users Arjun, Mei, Priya, Paatti in the app (or `POST /api/users`). Arjun adds Mei as "friend from high school, now in Shanghai" and Paatti as grandmother | none needed |
| S1 call 1 done | 0 | Real call 1, Mei says the Lin line | `/api/dev/apply` with speaker Mei, audience [Arjun], fact "Lin: friend from the Fudan climbing wall" |
| S2 news told to Priya | 35 | Arjun texts KIN "started bouldering at the campus gym", then real call with Priya where he says it | `/api/dev/sms`; or `/api/dev/apply` speaker Arjun, audience [Priya] |
| S3 Mei's hike | 36 | Arjun texts KIN "Mei visited and we went hiking" (his own fact) | `/api/dev/apply` speaker Arjun, audience [] |
| S4 call 2 | 42 | Real call 2 | Typed line via `/api/calls/{id}/text` if ASR drops 林 |
| S5 next day | 43 | Same call 2 line again | same |
| S6 Paatti | 43 | Before the call, Arjun places Ravi mama (Mom's younger brother, Adyar, Chennai) and Ravi periyappa (Dad's elder brother, Coimbatore) from the graph screen (`POST /api/world/place`) | Typed Tamil lines |

Planting call 1 with `/api/dev/apply` is fine for rehearsal. For the film, try the real call 1 first, since it is
also footage.

## Shot list

Framing terms: OTS = over the shoulder of the person holding the phone, phone in focus, face soft. SCREEN = clean iOS
screen recording composited in edit. PIP = the other person's face in a small window.

### 1. Cold open (0:00-0:10)

- **Location:** Arjun's room or a quiet corner, evening, a lamp on, window behind camera.
- **On screen:** Arjun, on a video call. Mei in his phone.
- **Arjun's phone:** call 2 (state S4). Mei's video; her Mandarin line with the English caption under it.
- **Framing:** start medium close on Arjun's face, laughing at something she said. Then a slow push-in as she says
  "我和林终于去了莫干山". His face goes blank for a beat.
- **Audio:** real call audio only. No music, no VO.
- **Edit:** cut to black before the Lin card appears (it arrives about 3 s after she finishes). This is the same
  take as shot 7, so the payoff later is literally the next second.

### 2. The problem (0:10-0:18)

- **On screen:** black, white text, one line at a time: "Who's Lin?" ... "She told him. Six weeks ago."
- **Audio:** silence, then one soft piano note.
- **Edit:** text in a plain sans (SF Pro or Inter), centered, 1 s fades.

### 3. Reveal (0:18-0:25)

- **On screen:** KIN wordmark (the app icon) on black. Tagline under it: "Common ground for people who live apart."
- **VO:** "Introducing KIN."
- **Music:** the main track starts here (warm, sparse piano or plucked guitar, around 90 BPM).

### 4. It starts empty (0:25-0:37)

- **Location:** same as shot 1, daytime. Lower third: "September".
- **On screen:** SCREEN of Arjun's phone (state S0): an empty graph, add Mei. Then OTS of call 1: Mei says the Lin
  line in Mandarin; the English caption appears under her video.
- **VO:** "KIN is a calling app for one-to-one video and audio calls. Nothing is pre-loaded. It learns who is in each
  other's lives from the calls themselves."
- **Edit:** 4 s on the empty graph, 8 s on call 1. Captions are on by default; show the voice toggle off.

### 5. His news, told to someone else (0:37-0:45)

- **Location:** a hallway or campus bench (different from shot 1, so it reads as another day).
- **On screen:** Arjun, phone to ear or on speaker, Priya on the line. If the SMS route works, a 2 s SCREEN of the
  text "started bouldering at the campus gym" and KIN's short reply.
- **Audio:** Arjun: "I started bouldering at the campus gym." Priya reacts.
- **VO:** "He tells Priya his news. Not Mei."

### 6. Time card (0:45-0:49)

- **On screen:** "Six weeks later" with a smaller line: "Time advanced with a dev clock for this demo."
- **Edit:** something visible changes for shot 7: Mei's shirt, the light, the date on the phone status bar.

### 7. Hero: the reminder card and the bridge chip (0:49-1:12)

- **Location:** shot 1 again.
- **On screen:** split screen, both phones side by side as SCREENs, Arjun's face OTS behind his.
- **Arjun's phone (S4):** English caption of Mei's line, then the card "Lin: Mei's friend from the Fudan climbing
  wall. She mentioned her Sept 14." About a second later the private chip "You haven't told Mei: you started
  bouldering."
- **Mei's phone:** captions of Arjun's English in Chinese. No card, no chip.
- **Audio:** real call. Arjun: "Oh, I actually started bouldering!" Mei reacts.
- **VO (over the card, ducked under the call):** "Arjun has probably forgotten Lin, so he gets one line of context.
  Mei is talking about climbing and hasn't heard his news, so he gets something of his own to say back. Only on his
  screen."
- **Edit:** a soft highlight ring on Mei's empty screen for 1 s. Do not speed up the card arrival; real timing is
  part of the claim.

### 8. Silence (1:12-1:19)

- **On screen:** lower third "Next day". SCREEN of Arjun's phone (S5): the same sentence, captions, no card. Text
  overlay: "No card."
- **VO:** "Say it again tomorrow, and KIN stays quiet. It only speaks when you would be lost."
- **Music:** drops to a single sustained note.

### 9. How it works (1:19-1:28)

- **On screen:** one motion graphic, built in Keynote and exported as video. Two columns, "What Arjun knows" and
  "What Mei knows". Lin sits in Mei's column; a faint copy in Arjun's column fades over six weeks. The faded item
  turns into the card. Arjun's "started bouldering" sits in his column with a dot for Priya and none for Mei; that
  gap turns into the chip.
- **VO:** "KIN keeps a model of what each person knows about the other's world, and forgets the way people do. A card
  appears only where there is a gap."

### 10. Paatti (1:28-1:52)

- **Location:** Paatti's home (remote video call), morning light. Arjun in shot 1's location.
- **On screen:** OTS of Arjun's phone first, then a SCREEN of Paatti's phone.
- **Arjun's phone (S6):** Tamil line 1 with the caption "your uncle Ravi mama (Mom's younger brother) called from
  Adyar". Line 2: "Ravi periyappa (Dad's elder brother) opened a new shop in Kovai". Then she asks about his friends
  and his chip reads "You haven't told Paatti: you went hiking with Mei when she visited."
- **Paatti's phone:** Tamil captions of his English, then the Tamil card "Mei: Arjun's friend from high school, now
  in Shanghai."
- **Audio:** real call. Arjun: "Mei and I went hiking when she visited."
- **VO:** "Same app, every relationship. With his grandmother, KIN knows which Ravi is which. When he mentions Mei,
  Paatti gets a card in Tamil about who Mei is to him. Only his facts, never anything Mei said."
- **Edit:** show the Tamil card full screen for 2 s with the English meaning as a subtitle. If Paatti's card is not
  built, cut it and end the beat on the two Ravis.

### 11. Proof (1:52-2:02)

- **On screen:** two bars. "Generic translation: 54% entity errors" and "KIN: 1%". Under them: "Two people with the
  same name: 97% wrong vs 0%." Small print: "Muse Spark 1.3, same model and context with and without KIN's graph.
  105-sentence Tamil family test set, 150 entity spans."
- **VO:** "Same model, with and without KIN's graph: 54% of names and relationships wrong, versus 1%."
- **If the common-ground eval has run:** add one line, "Cards shown when needed: X% for KIN vs Y% for a shared-context
  baseline (N scenarios)", with the measured values only.

### 12. Privacy (2:02-2:10)

- **On screen:** SCREEN of the "KIN is on" banner both people see, a finger tapping Pause, then the "your world"
  screen and Delete.
- **VO:** "Everyone on the call sees KIN is on, and anyone can pause it. Audio isn't kept. KIN only suggests your own
  news. Delete means gone."

### 13. Close (2:10-2:20)

- **On screen:** KIN wordmark and "Common ground for people who live apart." Then the credits line: "Built at HackTX
  2026 on Meta Muse Spark and Muse Voice Transcribe, with LiveKit, ElevenLabs, Twilio and SwiftUI. Code written with
  Claude Code." Repo URL: https://github.com/LordKarV/hacktx. If Option B names were used (CASTING.md), add "Real
  people on real calls through KIN. Names and the six-week gap were set up for this demo."
- **Music:** resolves and ends on the last frame.

## Music

Royalty-free and safe for YouTube Content ID:

- YouTube Audio Library (YouTube Studio > Audio Library, filter "Attribution not required"). First choice: no claim
  risk on YouTube.
- Pixabay Music (pixabay.com/music, Pixabay Content License, no attribution required).
- Uppbeat free tier (credit line required in the description).

Mood: cold open silent; reveal to shot 10 warm and sparse (piano or acoustic, around 90 BPM); proof and privacy pulled
back to a pad; close resolves. No vocals. Duck music to -18 dB under call audio and VO.

## Equipment

- Three iPhones with the KIN build: Arjun, Mei (or her own via TestFlight), Paatti (or her family member's).
- A fourth phone or any camera for the face shots.
- A tripod or a stack of books, and a phone clamp if available.
- A quiet room with good window light; a desk lamp for the evening shots.
- AirPods or a lav mic for each speaker. Each person also records a Voice Memo as a backup audio track (clap at the
  start to sync).
- A laptop running the server and the edit (CapCut desktop, iMovie or DaVinci Resolve).
- Device frames for compositing: Apple Design Resources (developer.apple.com/design/resources).
- Phone settings: Do Not Disturb on, battery above 50%, time on the status bar consistent within each scene.

## Production schedule (working back from 11:30am CDT Oct 25)

| When (CDT) | What |
|---|---|
| Oct 24 by 6:00pm | Cast confirmed, lines and release sent (CASTING.md). Remote install path decided |
| 6:00-7:00pm | Feature freeze for filmed beats. Fresh DB, users created, every dev route checked |
| 7:00-8:00pm | Dry run of every beat with teammates on the real server. Go/no-go for each beat, written down |
| 8:00-9:00pm | Mei: rehearsal, call 1, call 2, next-day take (9-10am Shanghai) |
| 9:00-9:45pm | Paatti call (7:30-8:15am IST) |
| 9:45-10:30pm | Priya call, SMS screen, empty-graph and privacy screens, B-roll |
| 10:30pm-12:00am | Retakes. Native checkers review raw captions |
| 12:00-3:00am | Rough cut, how-it-works graphic, proof card |
| 3:00-5:00am | VO recorded against the cut, music, subtitles |
| 5:00-7:00am | Fine cut, native check of the final captions, team review |
| 7:00-8:00am | Export, upload to YouTube as Public, wait for HD processing |
| 8:00-9:00am | Check the link plays signed out, paste into Devpost |
| 11:30am | Deadline. Nothing should be left to do after 9:00am |

## Retake and backup plan

| Problem on the day | What we do |
|---|---|
| ASR misses 林 or the Tamil line | Retake. On the third miss, type the line with `/api/calls/{id}/text` and show the typed caption honestly (a quick on-screen note "typed") or cut the beat |
| A caption or card is wrong (native checker) | Retake. Never fix it in the edit |
| Card arrives late | Keep the real timing; trim the reaction around it |
| SMS route not built | Cut the SMS shot; Priya call alone carries the news |
| Bridge chip not built | Cut the chip from shots 7 and 10; VO loses the bridge lines |
| Paatti's Tamil card not built | End shot 10 on the two Ravis |
| Dev clock route missing | Restart the server with `CLOCK_OFFSET_DAYS` set per state |
| Mei or Paatti cannot make it | Fallbacks in CASTING.md; Paatti audio-only is better than a stand-in |
| LiveKit call drops | Retake; record both screens every take so either side can be used |
| Upload stuck processing | Upload by 8:00am; if still SD at 9:00am, submit the link anyway, it upgrades later |

Minimum film if most new beats fail: cold open, reveal, call 2 with the Lin card only, next-day silence, the two
Ravis, proof, privacy, close. About 1:40.
