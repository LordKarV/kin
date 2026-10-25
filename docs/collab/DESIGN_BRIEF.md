# Design brief: the KIN iOS app

Goal: a genuinely good, calm, UX-first iOS design for KIN that the build session will implement in SwiftUI. The user
cares a lot about design and UX and will iterate on it with you. Deliver SwiftUI mockups (with previews and simulator
screenshots) in `design/`, plus short written rationale in `docs/collab/design-notes.md`.

## The principle everything follows

KIN only speaks when someone would be lost. The default state of a call is a clean, normal-feeling video or audio call.
Help appears briefly, privately, at the edge of attention, and leaves. Silence is a feature; design it on purpose.

## Screens and states to design

1. **First run / setup (about 20 seconds):** your name, your language(s), add the first person you want to call (name,
   how you know them: family relation or friend/roommate/classmate, their language). No account wall.
2. **People:** the people you call, grouped by circle (family, friends, groups). Tapping a person shows their world as
   KIN knows it: people in their life, ongoing storylines, places. It must feel like a shared notebook about your
   friendship, not a dossier. Every item shows where it came from ("Mei, Sept 14 call") and can be corrected or deleted.
3. **Call screen, 1:1 video:** remote video, self view, controls (mute, camera, flip, speaker, end, pause KIN). A clear
   but quiet "KIN is on" indicator that both people see.
4. **Call screen, group (3 people):** tiles, who is speaking, the same help layer.
5. **Live captions when languages differ:** the speaker's line in the listener's language, the original line smaller,
   live partial text while they speak. Readable at a glance, large type, never covering faces.
6. **"Who's that?" card:** e.g. "Lin: Mei's friend from the Fudan climbing wall. She mentioned her Sept 14." Appears
   mid-sentence, auto-dismisses, never vanishes while touched. Variants: new person, forgotten person (a gentle
   reminder), place, thing.
7. **Bridge chip:** "You haven't told Mei: you started bouldering." Only the owner sees it. It must feel like a private
   nudge from yourself, not an AI interruption: small, dismissible, rate-limited (at most one every few minutes).
8. **Storyline card:** "Mei's job search: applied (Sep) -> second round (Oct)". A tiny timeline.
9. **"Who is X?" learning card:** "Who is Ravi mama?" with suggested relations (from the language's kinship table) and a
   name field. One tap to add. Also the friend version: "Who is Lin? Mei's friend / roommate / classmate / ..."
10. **Cultural meaning card:** "You've gotten thin" -> "Care and worry, not criticism."
11. **Messages:** a simple screen explaining the SMS number (copy the number, example texts like "started bouldering"),
    and what KIN understood from recent texts (each editable). Messages are private and never forwarded.
12. **Privacy and control:** pause KIN in a call, what KIN knows about you (see/correct/delete), who has heard which of
    your news (the disclosure view), third-party items with expiry.
13. **Empty and edge states:** no people yet, first call (KIN knows nothing yet: it learns), poor connection, KIN
    paused, the other person does not have KIN running.

## Visual direction

- Meta-adjacent but its own product. The current client uses Meta's dark palette: background #18191A, surfaces #242526,
  fields #3A3B3C, primary Meta Blue #0064E0 (gradient #0064E0 -> #0082FB for the brand mark), accent #47A5FA, success
  #31A24C, warning #F7B928, error #E41E3F; radii 20 (cards) / 14 (images) / 8 (fields), pill buttons. Feel free to
  propose a better system (light mode too), with reasons.
- Type: the system font (SF Pro) with Dynamic Type support; large, legible captions. Respect Reduce Motion.
- Cards: glanceable in under a second (title, one line, source). Motion: slide in from the edge, gentle; never block the
  other person's face.
- Accessibility: Dynamic Type, VoiceOver labels, 44 pt targets, color is never the only signal.
- Do not look like Nudge (photo-sharing chips) or Roots (Wikipedia picture bubbles over captions).

## Deliverables

- `design/KinMockups/`: a SwiftUI project (or package) with components (cards, chips, captions, call controls,
  tiles) and full screens, each with `#Preview` blocks using data from `docs/collab/STORIES.md`.
- `design/screens/*.png`: simulator screenshots of each screen and state.
- `docs/collab/design-notes.md`: the design system (tokens, type scale, spacing, motion rules), and a short rationale
  per screen. Keep it concrete.
- Components should be easy to lift into the real app later: plain SwiftUI views taking simple value types, no
  networking, no singletons.

## Event shapes the real app will receive (for realistic mockups)

The authoritative contracts are in `docs/ARCHITECTURE.md` (section on event contracts); read it for the exact JSON of
cards, bridges, storylines and captions. Design against those shapes so components drop into the real app unchanged.
