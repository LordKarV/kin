# The 20 hardest judge questions

Short, honest answers. If the true answer is "not measured" or "not built", say that.

1. **Isn't this just recall with shared context? Give a chatbot the history and it does the same.**
   A model with the history explains Lin every time she comes up, to both people. KIN keeps a separate knowledge
   state per listener, with forgetting: Arjun gets the card after six weeks, nothing the next day, and Mei never sees
   one. The quiet second time is the feature. We have not yet measured gap precision against a shared-context
   baseline; 39 scenarios are written and the runner is next.

2. **How is this different from Nudge?**
   Nudge starts calls and shows photos when you mention an event, then nudges you to follow up. KIN has no reminders,
   no photos, no topic lists. It works inside a call and shows something only when one listener lacks context, and
   most of the time it shows nothing.

3. **Isn't this a grandma translator?**
   Translation is one feature, on only when languages differ. The lead story is two friends who both speak English;
   the engine is the same for friends abroad, friends at other colleges and grandparents.

4. **What does 54% vs 1% actually measure?**
   Entity errors in translation on 105 Tamil family sentences (150 entity spans), same Muse Spark model and same
   context, with and without KIN's graph. It measures grounded translation. It does not measure the common-ground
   engine.

5. **How accurate is it in other languages?**
   Measured only in Tamil. Kinship tables exist for all 25 Muse Voice Transcribe languages, but 24 are model drafts
   marked "draft" in the UI. We have no Mandarin accuracy number; the Mandarin captions in our video were checked by a
   native speaker.

6. **Who wrote the test set? Is it biased toward you?**
   It was drafted with Claude and has not had a native-speaker review. The linker's cue words were written alongside
   it, so there is no held-out split. The comparison is still fair between the two conditions, because both see the
   same sentences and context.

7. **How fast are captions?**
   p50 3.0 s, p95 4.8 s per sentence for grounded translation, plus about 3.5 s of ASR end-of-turn detection. A split
   path gets 1.9 s but flattened 4% of kinship terms, so we did not ship it. Card matching on partial transcripts is
   p50 0.15 ms, which is why cards can show before the caption.

8. **The other person didn't agree to an AI on the call.**
   Everyone on the call sees KIN is on, and anyone can pause it. While paused, nothing is transcribed or stored. Both
   people are users of the same app.

9. **What about people who are talked about but never agreed to anything, like Lin?**
   KIN stores only what was said, shows it only to people who heard it, and deletes it after 120 days unless someone
   pins it. Anyone can delete a third party they mentioned.

10. **Could KIN leak what Mei said to Paatti?**
    No. Bridges and cross-world cards use only the speaker's own facts. Every card lists the facts it uses, and a
    final check drops and logs any card citing a fact that listener cannot see.

11. **What do you keep, and can I delete it?**
    Transcripts and extracted facts, not audio. You can see, edit and delete facts about you, or delete your whole
    world; SQLite secure_delete is on, so deleted rows are overwritten.

12. **Sensitive things: health, money, a fight?**
    Stored as a single topic word (for example "health") unless someone taps "remember this". No details are kept by
    default.

13. **Why Meta?**
    One key gives us live multilingual ASR with Tamil-English code-switching (Muse Voice Transcribe) and a reasoning
    model with strict structured output (Muse Spark). The track asked for AI that identifies common interests that
    could spark a connection; that is what bridges do.

14. **Where is AI not used?**
    Name detection (alias tables and fuzzy matching), the knowledge model (knowledge tracing with forgetting) and
    privacy checks are deterministic. Muse Spark is used for meaning: translation, cultural cards, extraction.

15. **What if the ASR gets a name wrong?**
    Names in the graph are passed as keyword hints, aliases cover different spellings (林, Lin, Lynn), and an
    ambiguous mention asks "Who is X?" instead of guessing. There is also a typed-text fallback.

16. **What happens with two people with the same name?**
    That is the two Ravis. KIN uses co-mentioned places, speaker, and the respectful verb ending to pick one. Generic
    translation got 97% of these wrong; KIN 0% on our set.

17. **Is the six-week gap in your video real?**
    No. We advanced the server clock with a dev endpoint and say so on screen. The calls, people and cards are real.

18. **What was built during the hackathon?**
    [Answer from git history before judging: which commits predate 11:30am Oct 24, and what they contain.] Be exact.
    Do not guess.

19. **What did AI coding tools do?**
    The code was written with Claude Code from our specs. We listed it in the submission, as MLH rules require.

20. **Would anyone use this after the weekend?**
    Not measured; we have no user study. The use case is the one every long-distance friendship has: you forget who
    someone is, and your news reaches some people and not others. Next steps are the gap-precision eval and a small
    pilot with friends abroad.
