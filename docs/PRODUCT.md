# KIN: product spec (agreed 2026-10-24)

This file is the product source of truth. KIN_BUILD_PLAN.md describes the original translation-first build; where they
disagree, this file wins. Every build session reads this first.

## Premise

Distance and language erode **common ground**, the shared context that makes conversation easy (Clark & Brennan,
"grounding in communication"). KIN is a **common-ground engine** for calls between people who live apart: it models
what each person knows about the other's world and **fills only the gaps, live, in each listener's language**. It speaks
only when someone would be lost.

It is NOT an AI notetaker or "recall on request" (commodity), NOT a language-learning app (learning is an optional
mode), and NOT a copy of Nudge (photos on mention, call reminders, AI topic lists) or Roots (Telugu grandma translator).

## Who it is for (one engine, every relationship)

| Relationship | Language gap | Distance/time gap | Generation gap |
|---|---|---|---|
| Grandparents and grandkids | yes | yes | yes |
| Friends in different countries | often | yes | no |
| Friends at different colleges, friend groups | no | yes | no |

Translation switches on automatically when two people's languages differ. Everything else works for every
relationship. Any of the 25 Muse Voice Transcribe languages, including Chinese, Japanese and Thai (no spaces).

## The app

1. **Built-in calls: video and audio, one-to-one** (LiveKit). One-to-one calls are the product. If more people join
   a call it still works (each listener still gets their own help), but nothing is designed or demoed around group
   calls. Everyone gets the same app; there is no special grandparent mode and no "family helper" role.
2. **Live suggestions during the call** (each listener sees their own; nothing is shown before the call):
   - **"Who's that?" cards (their world, your gap):** "Lin: Mei's friend from the Fudan climbing wall, first
     mentioned Sept 14." Filtered by the common-ground model: never heard of Lin -> card; heard last week -> nothing;
     six weeks ago and likely forgotten -> a reminder.
   - **Bridges (your world, their gap):** a private chip, only when the other person's words make your own news
     relevant: Mei talks about climbing -> "You haven't told Mei: you started bouldering." Driven by who has heard what
     about you, learned across all your calls and messages. Rate-limited, visible only to you, never a topic list.
     Bridges only ever use YOUR OWN facts: in a call with Paatti, "You haven't told Paatti: you went hiking with Mei
     when she visited" is fine (your experience); anything Mei told you is never suggested to anyone.
   - **Storyline cards:** where an ongoing thread stands ("Mei's job search: applied (Sep) -> second round (Oct)")
     when it comes up and you are behind on it.
   - **"Who is X?" learning cards:** a suggested relationship (kinship or social) plus a name; one tap adds the person
     to the right world and the next mention is grounded.
   - **On-demand context (a twist of the phone):** KIN's push cards will sometimes miss (it thought you remembered
     Lin). A quick double twist of the wrist (gyroscope and accelerometer, with a light haptic tap) brings up a card for
     whatever the conversation is about right now. KIN ranks what you might be lost on in the last few lines (people,
     places, terms, storylines you are allowed to see; most recent and least known first). If one candidate is clear it
     answers instantly; if not (e.g. "that trip was insane" with no name), Muse Spark picks which visible candidate the
     recent lines refer to, or says it cannot tell, and KIN looks further back. Private to you, never more than a push
     card could show, and it counts as evidence that you did not know. Tapping a word in the caption is a quiet
     fallback.
   - **Pause, kept tiny:** one tap in the "KIN on" pill pauses listening for everyone; both people see who paused;
     one tap resumes. No separate screen. Consent is per moment, not per install (Mei about to talk about her mom's
     surgery, Paatti about Saroja's health).
   - **Translation and cultural meaning** when languages differ: grounded on who people are ("your uncle Ravi", not
     "uncle"), plus cultural/pragmatic meaning ("you've gotten thin" from a grandma is care, not criticism).
     **Captions by default.** A translated voice is an optional per-person toggle (off by default), for someone who
     cannot read captions quickly; a voice talking over the real person is distracting, and captions keep the call
     human.
3. **Messages for context: one SMS number.** You keep texting it updates about your life ("started bouldering",
   "got the internship"). KIN parses each message into YOUR world and replies with a short acknowledgment. Messages
   are private: never forwarded to anyone; they only let KIN know your news and who has not heard it yet. Optional;
   mostly used between friends. Text only.

## Where context comes from

- **Baseline: calls.** Everything said in calls builds the speakers' worlds and the knowledge states of everyone who
  heard it. Nobody has to record anything (grandparents included).
- **Extra: SMS messages** from any user, about themselves.
- Nothing is pre-seeded. A new user starts with themselves and whoever they call.

## The connected graph

- **One connected graph with you at the center.** Circles: family, friends, and friend groups (a group is a node with
  members, e.g. "Fudan crew").
- **Relationships:** kinship (tables for all 25 languages already exist) plus social: friend, close friend, partner,
  roommate, classmate, coworker, teammate, member of a group, plus "their ___" for people in someone else's world.
- **Their worlds:** each person you talk to has people, places, events and storylines hanging off them
  (Mei -> Lin -> the climbing gym).
- **Cross-world mentions:** telling your grandma "Mei and I went hiking" gives grandma (in Tamil) "Mei: Arjun's friend
  from high school, now in Shanghai". Across circles KIN only shares YOUR facts (who Mei is to you), never what Mei
  said in her own calls.

## The engine (technical core)

1. **World graph:** people, places, events, storylines. Every fact has provenance (who said it, which call or
   message, which language, when), a status (active / resolved / contradicted / superseded), and a visibility rule.
2. **Common-ground model:** for each (knower, item) the probability the knower knows it, via knowledge tracing with
   forgetting (same family of math as Fade's BKT for words). Evidence: hearing it said in a call, a card being shown,
   saying it themselves. Items: people, things, facts, storyline states.
3. **Disclosure graph:** for each fact about YOU, which people have heard it. Drives bridges.
4. **Cross-script entity matching:** 林 / Lin / Lynn as one person; "her roommate", "that trip" resolved against past
   calls; names said in English inside a Tamil call matched to the right node; segmentation-free matching for
   Chinese, Japanese and Thai. Live on partial transcripts in milliseconds.
5. **Storylines:** threads with states (applied -> interview -> offer), updated from calls and messages, with
   contradiction detection ("moved to Beijing" vs "still in Shanghai") and unresolved flags.
6. **Per-listener delivery:** each listener gets their own captions language and their own cards (LiveKit private
   data per participant), plus their own translated voice track only if they turned voice on. This also makes a call
   with more than two people work, without being a focus.

## Privacy and consent (hard rules)

- Everyone in a call sees that KIN is on; anyone can pause it.
- Audio is processed and discarded; only transcripts and extracted facts are kept.
- **Bridges only use facts about you.** KIN never suggests repeating what someone else told you.
- **Third parties** (people discussed who are not users): only what was said, visible only to people who heard it,
  and it expires unless pinned.
- **Sensitive topics** (health, money, conflict) are stored as a topic word only unless someone taps "remember this".
- **Every fact carries its visibility** (who said it, who heard it); cards and prompts only use facts visible to that
  listener.
- **You own your world:** see, correct and delete what KIN holds about you; deleted means gone.
- SMS messages are private to their author.
- KIN never reads message histories (iMessage, WhatsApp, etc.).
- No engagement manipulation: no "you should call X", no streaks.

## Decided against (and why)

| Idea | Why not |
|---|---|
| Language learning as the premise | Overfits; Fade stays as an optional "learn their language" mode |
| Photos shown when an event is mentioned; call reminders; AI topic lists before calls | Nudge's product |
| Wikipedia pictures for culture terms as a headline feature | Roots' product; shelved (code stays) |
| Voice-note journal delivered to the other person; shared feed | Messages are private text for context only |
| Reading message histories | No consent from the other side, no APIs, surveillance feel |
| AI notetaker / recall on request | Commodity; KIN models the listener and speaks only on gaps |
| Special grandparent mode, family helpers, grandparents recording notes | Same app for everyone; context comes from calls |
| Many separate call surfaces as products | One app; desktop overlay and phone bridge remain in the repo as "bring KIN into any call" |
| Pre-seeded families | Everything is learned from use (seed data only in tests/eval) |

## Demo (all calls are one-to-one)

1. Call 1 (September), Arjun and Mei (Shanghai, speaks Mandarin): she mentions her new climbing friend Lin. Six weeks
   pass.
2. Arjun texts KIN "started bouldering", and tells Priya about it on a call. He never tells Mei.
3. Call 2 (six weeks later), Arjun and Mei: "I went climbing with Lin." Arjun gets the Lin card (he has likely
   forgotten). Because Mei is talking about climbing and has not heard his news, Arjun also gets a private bridge
   chip: "You haven't told Mei: you started bouldering."
4. Same sentence the next day: no card. "It only speaks when you would be lost."
5. Arjun and Paatti, in Tamil (captions): the two Ravis are named correctly, and when she asks about his friends Arjun
   gets "You haven't told Paatti: you went hiking with Mei when she visited" (his own experience, never anything Mei
   told him). When he mentions Mei, Paatti's caption and card explain who Mei is to him, in Tamil.

## Evaluation

- Grounding accuracy (exists: generic 54% vs KIN 1% entity error, eval/).
- **Gap precision/recall:** planted common-ground scenarios (who knows what, with time gaps); a card should appear
  exactly when the listener lacks the context.
- Bridge precision (only self-facts, only when relevant, only to people who have not heard).
- Latency per stage (glance on partials in ms; translation p50 ~1.9 s).
