# KIN demo: common ground on one-to-one calls

The story is in [PRODUCT.md](PRODUCT.md) ("Demo"). Every call is one-to-one, captions are on by default, and the
translated voice stays off unless someone turns it on. `scripts/demo_common_ground.py` plays the whole story against a
real server and prints what each person received, so it doubles as the rehearsal and the fallback.

## Run

Three terminals from the repo root. The backend needs `MODEL_API_KEY` in `.env` (MT and the SMS parse are live).

```bash
livekit-server --dev                                   # ws://localhost:7880, devkey/secret
cd backend && rm -f kin.db && DEV_ENDPOINTS=1 .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
cd backend && .venv/bin/python ../scripts/demo_common_ground.py --next-day
```

`rm -f kin.db` matters: the driver creates Mei, Arjun, Priya and Paatti itself, and a second run on the same database
stops with "phone already linked". Dev routes are off unless the server has `DEV_ENDPOINTS=1`; the driver says so on
a 404. Set `KIN_BASE` for another host and `KIN_KEY` when the server has a real `KIN_API_KEY`. After a run the clock is
back at 0; `--reset-clock` does only that.

iOS app (`mobile/` is frozen):

```bash
cd ios && xcodegen generate                            # Kin.xcodeproj from project.yml
open Kin.xcodeproj                                     # Run on an iPhone simulator, or:
xcodebuild -project Kin.xcodeproj -scheme Kin -destination 'generic/platform=iOS Simulator' build
```

The simulator reaches `http://localhost:8000`. A phone needs the laptop's LAN address under Sign up > Server (for
example `192.168.1.20:8000`; the app adds `http://` when it is missing), and a LiveKit URL it can reach.

### Phones as Arjun, Mei and Paatti

The driver prints a `kin://signin?token=...` link for each person right after the planted history. On a debug build,
open the link on the phone (AirDrop or paste it into Notes and tap it), or paste it into Sign up > Server > "Sign-in
link". The phone checks the token with `GET /api/me` and becomes that person; a release build ignores these links.

```bash
cd backend && KIN_BASE=http://192.168.1.20:8000 .venv/bin/python ../scripts/demo_common_ground.py --plant-only
```

`--plant-only` plants call 1, Arjun's facts, Paatti's two Ravis, the SMS and the Priya call, sets the clock to 0,
prints the links and exits, so the phones play call 2 and the Paatti call themselves. Without it the driver joins
call 2 as Arjun and Mei with the same LiveKit identities a phone would use, and the two kick each other out. With
`KIN_BASE` set to the LAN address the links also carry `server=`; for `localhost` they do not, and the phone keeps the
server it has. `KIN_KEY` adds `key=`.

Lost the links? On the server host (on Vultr, over ssh), `curl -X POST http://localhost:8000/api/dev/signin -H
"X-KIN-Key: $KIN_KEY" -H 'content-type: application/json' -d '{"person": "p_arjun_2"}'` (the slug the driver
printed) returns a new token for that person, and the old one stops working. The route answers only loopback callers.
Wrap the token as `kin://signin?token=<token>`.

Starting a call from a phone and sharing the invite sends `http://<server>/?call=N&code=C`. Tapping it opens a small
page on the KIN server that hands off to the app as `kin://join`. The code is required for a new person to join, and
it changes when the server restarts, so share a fresh invite after a restart.

## What the driver does, and what to point at

1. **Call 1 (clock -42 days).** Planted with `POST /api/dev/apply`: Mei tells Arjun about Lin, her friend from the
   Fudan climbing wall (`林`, `Lin`, `Lynn` as forms). Also planted: Arjun's own facts, "Mei is my friend from high
   school, now in Shanghai" (heard by nobody) and "went hiking with Mei when she visited" (Mei heard it), and Paatti
   placed as Arjun's mother's mother with `POST /api/world/place`.
2. **News (clock -3).** `POST /api/dev/sms` from Arjun: "started bouldering". Then an Arjun-Priya call where Arjun
   types "I started bouldering last week." Priya gets the caption only. KIN now knows Priya has heard; Mei has not.
3. **Call 2 (clock 0), Arjun and Mei.** Mei types `我和林去攀岩了`. Arjun gets the caption "I went climbing with Lin",
   the card "Lin: Mei's friend Lin (from the Fudan climbing wall), first mentioned Sep 13" (a reminder: he heard it six
   weeks ago and has likely forgotten), and the private chip "You haven't told Mei: started bouldering". Mei gets no
   cards.
4. **Next day (`--next-day`, clock +1).** Same line: caption only. "It only speaks when you would be lost."
5. **Paatti (clock +2), in Tamil.** Paatti types `உன் நண்பர்கள் எல்லாம் எப்படி இருக்காங்க?` ("How are all your
   friends?"). Arjun gets "You haven't told Paatti: went hiking with Mei when she visited" (his own experience; nothing
   Mei said is ever suggested). Arjun types "I went hiking with Mei when she visited." Paatti gets a Tamil caption and
   a card for Mei ("your grandson Arjun's friend Mei, from high school, now in Shanghai"), followed by its Tamil
   version; Arjun's hiking chip is retracted because he just told her. Then Paatti types
   `ரவி மாமா நேத்து வந்தாரு, ரவி பெரியப்பா அடுத்த வாரம் வர்றாரு.` ("Ravi mama came yesterday; Ravi periyappa is coming
   next week."). Arjun's caption names each uncle for who he is: "your uncle Ravi (Mom's younger brother)" and "your
   uncle Ravi (Dad's elder brother)". Both were planted at clock -3: Paatti told Arjun about them, then Arjun placed
   each by kin path (by slug, so the second Ravi is not merged into the first).

Rehearsed 2026-10-25 on `livekit-server --dev` with the live model. All five beats printed as above (one run, about 70
seconds). The two-Ravis line and `--plant-only` were added after that rehearsal and have only run offline
(`backend/tests/test_demo_driver.py`); rehearse them live before the demo.

## Fallbacks

- **ASR fails or mishears 林:** type the line (`POST /api/calls/{id}/text`, the keyboard in the call screen). The
  driver uses typed text everywhere.
- **Call 1 extraction is weak live:** plant it with `/api/dev/apply` (what the driver does) instead of a real call 1.
- **SMS:** `/api/dev/sms` stands in for Twilio until a number is set up.
- **The live call misbehaves on stage:** run the driver and show its output; it goes through the same engine.

## Known gaps

- Paatti's own view of the Ravis is plain "Ravi": placing a sibling by kin path does not make him her son.
- `--next-day` needs the driver; phones playing call 2 can repeat the beat after `POST /api/dev/clock {"offset_days": 1}`.
