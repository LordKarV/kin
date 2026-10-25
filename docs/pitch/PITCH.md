# KIN 3-minute pitch (in person, live demo)

Setup at the table: two iPhones on stands (phone A is Arjun's, phone B is Mei's account), the laptop with the launch
film open and paused at shot 7, and the slides (SLIDES.md). Server state S4 from LAUNCH_VIDEO.md, ready for call 2.

The live demo uses a judge, not a teammate acting. Hand phone B to the judge and ask them to read Mei's line. If the
venue wifi or the call fails, play the film from shot 7 and keep talking over it.

| Time | Slide | Spoken | On the table |
|---|---|---|---|
| 0:00-0:20 | 1 | "Think of a friend who moved far away. Six weeks between calls. She says 'Lin and I finally did the trip', and you nod, because asking 'who's Lin?' feels like admitting you weren't listening. She told you. You forgot. And she never heard your news either." | Slide 1 |
| 0:20-0:40 | 2 | "Psychologists call this common ground, the shared context that makes conversation easy. Clark and Brennan studied it inside a single conversation. KIN applies it to calls between people who live apart. It's a calling app that keeps track of what each person knows about the other's world, and fills only the gaps." | Slide 2 |
| 0:40-1:10 | demo | "This is a real one-to-one call. Six weeks ago on our dev clock, Mei mentioned a new friend. Could you read this line?" (Judge reads 我和林终于去了莫干山, or the English "Lin and I finally did the Moganshan trip.") "My screen: the caption, and one card, who Lin is and when I heard about her. Underneath, a private chip: I haven't told Mei I started bouldering. I told Priya, so KIN knows Mei hasn't heard. Look at your phone: captions, nothing else." | Phone A shows the card and chip; phone B shows captions only |
| 1:10-1:25 | demo | "Say it once more." (Judge repeats.) "Nothing. KIN has shown me Lin, so it stays quiet. It only speaks when you would be lost." | Phone A, no card |
| 1:25-1:50 | film | "Same app with my grandmother, in Tamil. She mentions two uncles, both named Ravi, and KIN names the right one each time. When I mention Mei, Paatti gets a card in Tamil about who Mei is to me. My facts only, never anything Mei said." | Film shot 10, 20 s |
| 1:50-2:15 | 3 | "Why the AI matters. Muse Spark grounds every caption in who people are. On our 105-sentence Tamil family test set, the same model without KIN's graph gets 54% of names and relationships wrong. With KIN, 1%. Two uncles with the same name: 97% wrong, versus 0%. Muse Voice Transcribe gives us live speech with Tamil-English code-switching. Where AI isn't needed we don't use it: finding names is a fast linker, and matching cards on partial transcripts takes under a millisecond." | Slide 3 |
| 2:15-2:35 | 4 | "Privacy is built into the engine. Everyone on the call sees KIN is on, and anyone can pause it. Audio isn't kept. Bridges only use your own news, never what someone told you, and every card is checked against what that listener is allowed to see before it's sent. Delete means gone." | Slide 4 |
| 2:35-2:50 | 5 | "Built this weekend on Muse Spark and Muse Voice Transcribe, with LiveKit for the calls, ElevenLabs for an optional voice, Twilio for texts, and a SwiftUI app. We wrote the code with Claude Code." | Slide 5 |
| 2:50-3:00 | 6 | "Meta asked for AI that identifies common interests that could spark a connection. KIN does that from your own life, one call at a time. Thank you." | Slide 6 |

## Notes for the presenter

- Say 54%, not 53%. If asked what it measures: grounded translation on the Tamil test set, not the common-ground
  engine. That eval has no runner yet.
- Captions take about 3 s (p50 3.0 s). Never say translation is instant. "Under a millisecond" is only the card
  matcher (p50 0.15 ms).
- The linker number: 2 ms per sentence in the eval, 10-17 ms in the live path. Say "fast", or give both if asked.
- If a judge cannot read Mandarin, they read the English line; the card still appears.
- If the judge's line misses in ASR, type it with `/api/calls/{id}/text` from the laptop and say so.
- Answers to hard questions are in QA.md.
