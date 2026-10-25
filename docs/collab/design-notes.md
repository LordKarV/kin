# KIN iOS design notes

Mockups: `design/KinMockups/` (SwiftUI package). Screens: `design/screens/*.png` (26 states, plus `_contact-sheet.png`).
Every component takes the real wire types from `ios/Kin/Sources/Contracts/Contracts.swift` (mirrored at commit dc5bc87),
and all sample data is the exact JSON of ARCHITECTURE section 9, decoded through those types. If the server shape
changes, the mockups stop compiling or decoding, which is intended.

## The one rule: silence is the default

A KIN call should look like a normal call. Everything below exists to keep help small, brief, private where it should
be, and out of the way of faces.

## Layout rules for the call screen

1. **Left is them, right is you.** This is the convention of every messaging app, so nobody has to learn it. The other
   person's captions and the cards about their world (who's that, storylines, meanings, terms) are left-aligned. Your
   private bridge chip is right-aligned in your blue, on the same side as your self view.
2. **Help lives in the lower third.** Faces in a portrait call sit in the upper middle (head center around 33 percent of
   the height, chin around 48 percent). Cards, captions and controls stack upward from the bottom and stay below the
   chin in every state rendered here.
3. **One card about their world at a time,** plus at most one bridge chip. A new card replaces the old one. Bridges are
   rate limited to one per 90 seconds (same as the engine).
4. **Cards appear next to the words that caused them.** The word in the caption that triggered a card is tinted and
   dotted-underlined ("Lin"), so it is always obvious why a card showed up.
5. **The big caption line does not jitter.** It shows the latest line you can read. While the other person is still
   talking, their live words (in their language) show small underneath with a typing indicator. The big line is
   replaced only when the new translation lands.
6. **The previous caption line is hidden while a card is up** to keep the stack short.
7. **KIN's state is always visible to both people,** top left: "KIN on" with a green dot (state is written, color is not
   the only signal). The pause control lives inside that pill, one tap, never in a menu. When paused, both people see
   who paused and a Resume button, and the caption area explains that nothing is transcribed or remembered.

## Design system

### Color

Neutrals follow Meta's own light and dark system (Facebook, Messenger), so KIN feels at home next to Meta apps. KIN's
identity comes from restraint, type and layout, not from a new palette. Tokens live in `Theme/Tokens.swift` as
`KinColor` values that resolve light or dark from the SwiftUI environment.

| Token | Light | Dark | Use |
|---|---|---|---|
| `bg` | #FFFFFF | #18191A | Plain screens |
| `grouped` | #F0F2F5 | #18191A | Background behind grouped sections |
| `surface` | #FFFFFF | #242526 | Sections, cards, fields |
| `raised` | #F0F2F5 | #3A3B3C | Icon buttons, unselected tags |
| `separator` | #E4E6EB | #3E4042 | Hairlines, field borders |
| `text` / `text2` / `text3` | #050505 / #65676B / #8A8D91 | #E4E6EB / #B0B3B8 / #8A8D91 | Primary, secondary, tertiary text |
| `primary` | #0064E0 | #0064E0 | Filled buttons, your bubble and bridge chip |
| `link` | #0064E0 | #47A5FA | Tinted text and icons |
| `primarySoft` | #E6F0FD | #1D3557 | Selected chips, info backgrounds |
| `warning` | #B07A00 | #F7B928 | "Unclear" facts (darkened in light mode for contrast on white) |
| `error` | #E41E3F | #F0284A | Destructive actions |

The call screen is always dark (it sits on video), so its overlay colors are fixed: card #242526 at 96 percent, text
white at 100, 72 and 52 percent, the caption highlight #8CC4FF, your chip #0064E0, end call #E41E3F.

Changes from the brief's palette, with reasons: success green is used only as the small "KIN on" dot; the warning
yellow is darkened in light mode because #F7B928 on white fails contrast; there is no brand gradient anywhere in the
UI (it is reserved for the app icon), because gradients on functional surfaces are the fastest way to look generated.

### Type

System font (SF Pro). On iOS every style is a Dynamic Type text style, so everything scales with the user's setting;
the sizes below are the iOS defaults. Sentence case everywhere.

| Style | Size, weight | Use |
|---|---|---|
| `largeTitle` | 34 bold | Tab titles |
| `title` | 28 bold | Setup questions, a person's name |
| `title3` | 20 semibold | Section heroes |
| `headline` | 17 semibold | Card titles, row names |
| `body` / `callout` | 17 / 16 regular | Body text |
| `subhead` | 15 regular | Card bodies, row subtitles |
| `footnote` | 13 regular | Sources, footers |
| `caption` | 12 semibold | Eyebrows, tags |
| `captionLine` | 22 semibold (title2) | The live caption: the largest text on the call screen |
| `captionOriginal` | 15 regular | The original line above it |

### Spacing, radius, targets

4 point grid: 4, 8, 12, 16, 20, 24, 32. Screen gutter 16. Radii: cards 20, images 14, fields 12 (the brief's 8 looks
dated at a 52 point field height), chips and buttons are capsules. Every tappable thing has a 44 point target, even
when it draws smaller (the pause button in the pill, the chip dismiss).

### Motion

- Cards slide up from the caption area with a spring (response 0.38, damping 0.9). With Reduce Motion they cross-fade.
- A card stays 7 seconds, a bridge chip 10. A touch pauses the timer; when the finger lifts, the card stays 2 more
  seconds. Cards never vanish while touched. There is no visible countdown bar (it adds anxiety and noise).
- "Who is X?" cards wait for an answer or "Not now"; they never block the call.

## Screens and rationale

**Setup (app-01 to 03).** Three steps, about 20 seconds, no account wall. Step 1 asks your name and languages, with a
"Tamil, a little" option because many users understand some of their heritage language. Step 2 asks who to call first:
name, Family or Friend, an optional refinement (close friend, roommate...), where you know each other from, and their
languages. Step 3 states the three promises (quiet, visible, deletable) and ends in "Invite Mei to a call", not a
generic "Get started".

**People (app-04, 09 dark, 05 empty).** Grouped by circle (family, friends, groups). Each row: who they are to you,
their local time and city ("11:04 PM in Shanghai", which matters for calling across time zones), and their language
when it differs from yours. One call button per row; tapping the row opens their world, where audio and video are both
offered. There are deliberately no recency nudges ("you haven't called in 3 weeks"); PRODUCT.md rules out engagement
manipulation. The empty state explains KIN in one sentence and offers one action.

**A person's world (app-06, 10 dark).** A shared notebook, not a dossier: plain sentences ("Her friend from the Fudan
climbing wall"), each with where it came from ("Mei, Sep 14 call") and a menu to correct or delete. Storylines show as a
small vertical timeline; a contradiction is shown honestly as "Unclear: two calls disagree" with "Fix this". The footer
says the page is built only from your calls with this person and that she has her own version.

**Call, default (call-01) and speaking (call-02).** Just the call and captions. When she is mid-sentence, her live words
show small under the last line you can read.

**"Who's that?" card (call-03).** "Lin 林 / Mei's friend from the Fudan climbing wall / First mentioned Sep 14". A
reminder is marked "Reminder" with a clock icon; a new person is marked "New to you". The avatar uses the person's own
script (林) so cross-script names are visible at a glance.

**Bridge chip (call-04).** Right side, your blue, two lines: "You haven't told Mei" and "Started bouldering". A white
"Only you see this" tag sits on its edge so the privacy is explicit, not implied. It reads like a note from yourself,
not an AI interruption: no avatar, no sparkle, no "Suggestion" label.

**Storyline card (call-05).** "Catching up: Mei's job search", a two-node timeline. States you already knew are quiet;
the one you missed is marked "new to you".

**Cultural meaning (call-06) and terms (call-08).** The meaning card leads with the literal line in quotes, then the
meaning in bold ("It's care, not criticism."). Term cards (murukku) use a category icon instead of a picture, on
purpose: picture bubbles over captions are Roots' product.

**"Who is X?" (call-07).** "Paatti mentioned / Who is Ravi mama?" with the two most likely relations from the Tamil
kinship table as equal-width buttons (one tap adds the person), plus "Someone else" and "Not now" as quiet text.

**Same-language call (call-09).** No language route and no voice toggle, because there is nothing to translate; cards
still work ("Jess: Priya's roommate at Georgia Tech").

**Voice toggle (call-10).** Off by default, next to the captions, written out ("Voice off" / "Voice on") with an icon.
On means a translated voice for this listener only.

**Edge states (call-11 to 14).** Paused (who paused, Resume, and what pausing means), weak connection, the other person
joined without KIN, and the first call ("KIN on, learning" plus one line explaining that it learns as you talk). Each is
one short line under the KIN pill, never a modal.

**Paatti's view, in Tamil (call-15).** Same app for everyone: her captions and cards arrive in Tamil, and the chrome
strings around them come from `KinStrings.ta`. When Arjun mentions Mei, Paatti's card says who Mei is to him using only
what Arjun himself has said.

**Audio-only call (call-16).** No video, so the conversation is the main surface: name, call time and their local time
up top, then the last lines as a transcript with cards inline under the line that triggered them (same left and right
rule), and the voice toggle by the language route.

**Messages (app-07).** The SMS number with Copy, one example exchange in messaging bubbles, and "What KIN understood"
(each editable). Footer: private, never forwarded.

**You (app-08).** Privacy and control in one place. "Your news, and who has heard it" is the disclosure view: each fact
with a checked or dashed tag per person (check and dash, not only color). "From other people's calls" lists third
parties with their expiry and a pin, and sensitive topics marked "kept as a topic only". Delete everything at the
bottom.

## Accessibility

- Dynamic Type on every text style (iOS); captions are the largest text and wrap to 3 lines.
- VoiceOver: each card is one combined element; the bridge chip's label starts with "Private to you."; the pause button
  says "Pause KIN for this call"; the voice toggle states its current state and what tapping does.
- Color is never the only signal: KIN state is written, selection chips carry a checkmark, disclosure tags carry a
  check or a dash, "Unclear" carries a warning icon.
- Reduce Motion: cross-fades instead of slides.

## Proposed contract additions (for the build session)

- `GET /api/contacts` and `GET /api/world` people: add `native` (initial in their own script) and `tz` (for "11:04 PM in
  Shanghai"). The mockups use `native`, `place` and `local_time` on `Contact` (`Sample/WorldSample.swift`).
- Bridge `body`: phrase it as a fact that reads after "You haven't told Mei" (today "started bouldering" works; the chip
  capitalizes the first letter).
- Storyline `title`: include the owner ("Mei's job search") so the card reads without context.
- `GlanceItem` for `who`: keep the ", first mentioned Mon D" suffix in `body`; the card splits it into its own quieter
  line. A separate `source` field would be cleaner.
- `Contact`, `MeFact` and `HeardBy` (REST 9.2) are not in `Contracts.swift` yet; the mockup versions use the JSON field
  names so they can be replaced one for one.

## How these were made, and what to verify on a device

- This Mac has no Xcode or iOS SDK (only the Command Line Tools), so: previews use `PreviewProvider` instead of the
  `#Preview` macro (the macro needs Xcode's plugin; both show in Xcode's canvas), and screenshots are the same SwiftUI
  views rendered with `ImageRenderer` on macOS at the iPhone 16 Pro point size (393 by 852, saved at 2x).
- `ImageRenderer` does not draw `ScrollView` contents or real blur materials. `KinScroll` is a `ScrollView` on iOS and a
  top-pinned stack in renders; overlays use solid translucent scrims instead of materials (also more legible over
  video).
- Status bar, Dynamic Island and home indicator are drawn by `PhoneChrome` for realism; the real app draws none of it.
- The video frames are a drawn, defocused stand-in, not real video.
- On a device, check: caption legibility over bright video, Dynamic Type at the largest sizes (the card stack height),
  VoiceOver reading order on the call screen, and that the pill and controls do not collide with the Dynamic Island in
  landscape.
- Mobbin references were not used yet (the connector needs the user's account). Next pass: compare the call screen,
  captions and card patterns against Mobbin's FaceTime, Messenger, WhatsApp and Live Captions references.
