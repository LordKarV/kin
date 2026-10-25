## Inspiration

A grandmother asks her grandson, in Spanish, whether he has eaten. He grew up in the US and his Spanish stopped at the kitchen table, so he catches about half of it. She mentions tío Beto, and he can't place which Beto: there are two. He mentions his roommate Mei, and she can't place Mei either. They slowly drift apart, and the calls get shorter.

For the three of us, this is personal: all of our grandparents live in India, speak Tamil or Telugu instead of English, and some of them are losing their memory, so every call home hits the same two walls.

This is the everyday reality of many immigrant families. About 1 in 4 US children lives with an immigrant parent, and the heritage language fades within a generation or two. Grandparents and grandkids end up talking across a language gap and a memory gap at once. And those calls already run on Meta: in India and across much of the world, WhatsApp is how families call home. Translation tools carry the words but lose the family. A general-purpose assistant handed everyone's history is too slow for a live call and cannot guarantee what each person is allowed to see.

We wanted a call that closes both gaps in real time, and stays silent whenever you already know.

## What it does

KIN is, to our knowledge, the fastest context engine for real-time human conversation: **listener-aware inference, provenance-aware memory, and privacy-constrained delivery.** It maintains a listener-specific model of **who knows what**, then uses it to surface the right context at the right moment---without exposing information that listener is not permitted to see.

During a call, each person sees only their own help:

- **Grounded live captions.** Each side reads the other in their own language, with family context: "Ravi mama" is rendered as Mom's younger brother in Chennai and never confused with Ravi periyappa (Dad's elder brother) in Madurai.
- **"Who's that?" cards, in both directions.** One quiet line when KIN predicts you'd be lost. The grandson learns which uncle is which; the grandmother gets a card in her own language on who his roommate is, built only from his facts. Cards often land before the speaker finishes the sentence.
- **Cultural meaning & sentiment.** "You've gotten so thin" from a grandmother reads as affection, and KIN says so.
- **Silence when you know.** Heard last week: no card. Heard two months ago: a one-line reminder, thanks to a probabilistic model determining a memory fading away. Seen once: silence.
- **Bridges.** A private nudge like *"You haven't told Grandma: you went hiking with Mei."* Only your own news, and it clears once you say it.
- **Twist for more.** Physically double-twist the phone for context on whatever was just said.
- **Privacy you can see.** Either person can pause KIN for both with one tap. Text KIN your news over SMS and it becomes a private fact, never forwarded. View, fix or delete anything KIN holds.

## How we built it

Every utterance runs through two parallel paths:

- **Context path (milliseconds):** Partial transcripts are resolved to entities in the listener's world graph, scored against that listener's knowledge state, and turned into a card only when the model predicts a gap.
- **Language path (seconds):** Settled sentences are captioned by Muse Spark, grounded in the relationship graph.

In the background, Muse Spark reads each conversation and writes structured, provenance-stamped facts back into every participant's world graph, so the next call starts with more context than the last.

The knowledge state is a tracing model with forgetting:

$$
P_u(i,\, t) = P_u(i,\, t_0)\, e^{-\lambda (t - t_0)}, \qquad \text{show card} \iff P_u(i,\, t) < \tau
$$

Hearing a mention or seeing a card raises a listener's estimate; time lowers it.

**Architecture:**

- **Real-time transport:** LiveKit audio sessions with an event-driven FastAPI backend and per-user sockets. Calls ring, answer, decline and time out like a native phone app, with no links to share.
- **Streaming perception:** Muse Voice Transcribe integrated through an RTC agent; incremental transcript events feed the context pipeline. Names from the family graph are passed in as hints, and Tamil-English code-switching is handled mid-sentence across 25 languages.
- **Context state:** Per-user world graphs with fact provenance, disclosure boundaries, and temporal relevance. Every fact records who said it, who heard it, and when, so "does Grandma know who Mei is?" is an exact query, not a similarity guess.
- **Decision engine:** Alias-aware entity resolution, knowledge-state tracing, forgetting, and candidate ranking determine when an intervention is useful. Cross-script aliases (林 = Lin = Lynn) and segmentation-free matching keep resolution fast on half-finished text.
- **Grounded language:** Muse Spark generates captions and extracts or localizes facts against the available context; optional ElevenLabs output supports translated speech. It also explains cultural meaning and resolves what you meant when you twist the phone.
- **Policy and delivery:** Visibility checks gate what each listener receives; SwiftUI delivers the iOS experience, with SQLite-backed state and Twilio SMS integration.

**Deployed on Vultr.** The FastAPI backend and the LiveKit media server run together on a Vultr cloud compute instance, brought up with a one-command deploy script that installs both as systemd services and generates their secrets on the box. Keeping media and context on the same machine means a transcript never crosses the network on its way to a decision, which is how cards stay in the millisecond range.

**Privacy is enforced in code, not requested in a prompt.** The card picker draws only from facts the listener can see, and a fail-closed guard re-checks every outgoing card, dropping any that cites a fact outside the listener's view. Audio is processed and discarded. Paused segments are never transcribed or stored. Deleted rows are overwritten, and third-party facts expire on a schedule.

## Challenges we ran into

- **Deciding before the sentence ends.** A card that arrives after the moment has passed is useless. Matching names on half-finished, still-changing text across writing systems took us down to 0.15 ms.
- **Beating the obvious baseline fairly.** "Just give an LLM everyone's history" sounds reasonable, so we built exactly that and tested it against KIN with the same model, the same scenarios and the same rules, across a simulated three months of history. Our system performed much faster and more accurately.
- **Making privacy structural.** Writing "don't reveal private info" in a prompt is easy, but is not fail proof. Designing a data model where every fact knows who heard it is much more difficult.
- **Family names.** Two uncles share a name, a grandmother switches languages mid-sentence, and one person has three spellings. We layered graph hints, cross-script aliases and "Who is X?" cards to keep them straight.

## Accomplishments that we're proud of

- **0.15 ms** median name-matching latency.
- **2 to 3 ms** per decision with three months of history, against roughly 4 s for a full-history LLM baseline: **1,370x to 2,200x faster**, with no slowdown as history grows.
- **1% vs. 54%** caption name/relationship errors against the evaluated baseline.
- **0% vs. 97%** same-name identity confusion in the tested cases.
- **26/27 vs. 22/27** relevant moments surfaced in a simulated three-month-history test.
- **0 vs. 2** private texts surfaced to the wrong listener.

Both sides of every comparison use the same model (`muse-spark-1.3`); the only variable is KIN's context engine.

## What we learned

- **The model wasn't the bottleneck; context was.** The same model went from 54% to 1% name errors once it could see the family graph.
- **Speed and privacy are actually the same design choice.** Keeping a dedicated knowledge-state model on the live path made decisions take milliseconds and made every card checkable.
- **Ideas from cognitive science and adaptive learning carry over.** Common-ground theory and knowledge tracing turned out to be the right tools for modeling a family conversation.

## What's next for KIN

Native-speaker review of our test set, accuracy runs in more languages, and a pilot with immigrant families, starting with grandparents and grandkids. The natural home for KIN is WhatsApp calling, which families in India and around the world already use to call home: the same engine could sit inside those calls, with Muse already powering the language.
