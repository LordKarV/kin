# KIN 3-minute pitch (in person, live demo)

Setup at the table: two iPhones on stands side by side, screens facing the judges (phone A is Arjun's, phone B is
Mei's account). If the venue has a projector, mirror both phones into one side-by-side window on the laptop so the room
sees both screens at once. The laptop also has the launch film open and paused at shot 7, and the slides (SLIDES.md).
Server state S4 from LAUNCH_VIDEO.md, ready for call 2.

The live demo uses a judge, not a teammate acting. Hand phone B to the judge and ask them to read Mei's line. If the
venue wifi or the call fails, play the film from shot 7 and keep talking over it.

| Time | Slide | Spoken | On the table |
|---|---|---|---|
| 0:00-0:20 | 1 | "This is Mei. We sat next to each other all through high school, and two years ago she moved to Shanghai. Now we talk every few weeks. Last call she said 'Lin and I finally did the trip', and I nodded. She told me who Lin was six weeks ago. And I still haven't told her I started bouldering." | Slide 1: Arjun and Mei mid-call, both faces, both phones |
| 0:20-0:35 | 2 | "Psychologists call this common ground: what two people both know, which makes talking easy. Distance wears it down. KIN is a calling app that keeps track of what each person knows about the other's world, and fills only the gaps, while you talk." | Slide 2 |
| 0:35-1:00 | demo | "Both phones are on one real call. You're Mei. Six weeks ago, on our dev clock, Mei told me about a new friend. Could you read this line?" (Judge reads 我和林终于去了莫干山, or the English "Lin and I finally did the Moganshan trip.") "My screen: who Lin is, and when she told me. Under it, just for me: I haven't told Mei I started bouldering. I told Priya, not her. Your screen shows nothing, because you know Lin." | Phone A: Lin card and bridge chip. Phone B: captions only |
| 1:00-1:12 | demo | "Say it once more." (Judge repeats.) Say nothing for two seconds. Then: "Nothing. On either phone." | Both phones: captions only, no new card |
| 1:12-1:25 | demo | To the judge: "Mei, I actually started bouldering." Point at phone A as the chip goes. "Now she's heard it." | Phone A: the chip is gone. Phone B: captions only |
| 1:25-1:48 | film | "Same app with my grandmother, in Tamil. She mentions two uncles, both named Ravi, and each caption names the right one. When I say Mei and I went hiking, Paatti's phone tells her who Mei is to me, in Tamil. Never anything Mei told me." | Film shot 11, both phones split-screen, 20 s |
| 1:48-2:15 | 3 | "We tested the obvious alternative: an AI given everyone's full history. Across [N] planted situations it showed a card to someone who already knew [X%] of the time, and passed one person's words to someone else [Y leaks] times. KIN: [X%], and [Y leaks]. For captions, the same Muse Spark model without KIN's graph gets 54% of names and relationships wrong on our 105-sentence Tamil family test set. With KIN, 1%. Muse Voice Transcribe gives us live speech with Tamil-English code-switching. Where AI isn't needed we don't use it: matching cards on partial transcripts takes under a millisecond." | Slide 3 |
| 2:15-2:33 | 4 | "Privacy is built into the engine. Everyone on the call sees KIN is on, and anyone can pause it. Audio isn't kept. Bridges only use your own news, never what someone told you, and every card is checked against what that listener is allowed to see before it's sent. Delete means gone." | Slide 4 |
| 2:33-2:48 | 5 | "Built this weekend on Muse Spark and Muse Voice Transcribe, with LiveKit for the calls, ElevenLabs for an optional voice, Twilio for texts, and a SwiftUI app. We wrote the code with Claude Code." | Slide 5 |
| 2:48-3:00 | 6 | "Meta asked for AI that identifies common interests that could spark a connection. KIN does that from your own life, one call at a time. Thank you." | Slide 6 |

## Notes for the presenter

- The three demo beats carry the idea without explanation: a card for one person, then the same line with nothing,
  then the chip gone once she has heard. Do not explain why the second line shows nothing; let the room work it out.
- Before beat 2, wait until the Lin card has left phone A (about 20 s untouched), so the screen is visibly empty when
  the judge repeats the line. The chip stays 30 s untouched; touch it once before beat 2 so it is still there for beat
  3 (a touch restarts its timer).
- [VERIFY] Beat 3: saying the news on the call records that Mei heard it (live.py `_told`), but that path sends no
  retract to phone A, so the chip may stay until it times out. Either build the retract before judging, or tap the
  chip's dismiss as you say the line and do not claim it cleared on its own.
- Slide 3 numbers in brackets are placeholders until the common-ground eval runs. [CONFIRM: from eval 4A] If they are
  not in by judging, cut the first two sentences of 1:48 and say "we built that comparison; the numbers are not in
  yet."
- Say 54%, not 53%. If asked what it measures: grounded translation on the Tamil test set, not the common-ground
  engine.
- Captions take about 3 s (p50 3.0 s). Never say translation is instant. "Under a millisecond" is only the card
  matcher (p50 0.15 ms).
- The linker number: 2 ms per sentence in the eval, 10-17 ms in the live path. Say "fast", or give both if asked.
- If a judge cannot read Mandarin, they read the English line; the card still appears.
- If the judge's line misses in ASR, type it with `/api/calls/{id}/text` from the laptop and say so.
- Answers to hard questions are in QA.md.
