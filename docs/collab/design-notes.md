# KIN iOS design notes

Mockups: `design/KinMockups/` (SwiftUI package). Screens: `design/screens/*.png` (40 states, plus `_contact-sheet.png`).
Brand: `design/brand/` (app icon, launch screen, launch film cards).
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

System font (SF Pro). Display styles (largeTitle, title, title2, title3) use SF Pro Rounded, which reads friendlier at
large sizes without looking childish; everything you read at length stays SF Pro. On iOS every style is a Dynamic Type
text style, so everything scales with the user's setting; the sizes below are the iOS defaults. Sentence case everywhere.

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
reminder is marked "Mentioned before" with a clock icon; a new person is marked "New to you". The avatar uses the person's own
script (林) so cross-script names are visible at a glance.

**Bridge chip (call-04).** Right side, your blue, two lines: "Mei hasn't heard yet" and "You started bouldering". A
white "Only you see this" tag sits on its edge so the privacy is explicit, not implied. It reads like a note from yourself,
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

**Edge states (call-11 to 14).** Paused (in the pill and one quiet line in the caption area; see "Round 3"), weak
connection, the other person joined without KIN, and the first call ("KIN on, learning" plus one line explaining that
it learns as you talk). Each is one short line under the KIN pill, never a modal.

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

## Round 2: the remaining states

Added for the iOS shell's real screens (signup, home, call, ended) and the launch film shot list
(`docs/pitch/LAUNCH_VIDEO.md`):

| Screen | File | Why |
|---|---|---|
| Waiting for the other person | call-17-waiting-invite | The shell starts a call, then shares an invite. One obvious action: Share invite (plus Copy) |
| Mei's own phone, Chinese captions | call-18-mei-view-chinese | Film shot 7: Arjun's English as a Chinese caption, no card on her side |
| Next day, no card | call-19-next-day-silence | Film shot 8: the same sentence, captions only |
| The two Ravis | call-20-two-ravis | Film shot 10: each Ravi named for who he is to Arjun |
| Paatti asks about friends | call-21-paatti-hike-bridge | Film shot 10: "Paatti hasn't heard yet / You went hiking with Mei when she visited" |
| Paused by me | call-22-paused-by-me | Film shot 12 |
| Joining from an invite | app-11-invited-signup | The shell's "Sign up and join" path: who invited you, name, languages, Join |
| Welcome and SMS number | app-12-welcome-sms | The shell's post-sign-up screen, with "Maybe later is fine too" |
| Adding a relative | app-13-add-relative | Film state S6 (placing Ravi mama): relation from the kinship table plus the word the family uses |
| Call ended | app-14-call-ended | What KIN picked up from this call, to confirm or correct. No ratings, no "call again soon" |
| Delete confirmation | app-15-delete-confirm | Film shot 12. Calm, specific, and "Keep my account" is as easy to hit as Delete |

## Warmth review

The question for every screen: would a nervous first-time user, or a grandmother, feel watched, judged or rushed? Five
places read harsh and were changed.

| Where | Before | After | Why |
|---|---|---|---|
| Bridge chip | "You haven't told Mei" | "Mei hasn't heard yet" / "You started bouldering" | The old line reads like a scolding. The new one is an opportunity, about her, not your failure |
| Who card | "Reminder" | "Mentioned before" | Clinical, like a to-do app. The new label just states a fact |
| Pause | "KIN is paused for this call. No captions or cards, and nothing is transcribed or remembered until someone resumes." | "KIN is taking a break. Nothing is captioned or saved right now. Either of you can resume whenever you like." | Same facts, without the legal tone; a cup icon instead of a pause icon |
| Contradiction | "Unclear" with a warning triangle, "Two calls disagree", "Fix this" | "Not sure" with a question mark, "You heard both... Which is right?", and three answers (Beijing, Shanghai, Not sure yet) | Nobody did anything wrong; asking is friendlier than a warning, and answering is one tap |
| Banners | "Weak connection. Captions may lag." / "Mei joined from a link without KIN. Only you get captions." | "The connection is a little slow, so captions may lag." / "Mei joined without KIN, so captions are just for you." | Plain sentences instead of system messages |

Also softened: setup copy ("gets to know the people in your life"; "only speaks up when it would really help"), the SMS
reply ("Got it, thanks! Noted that you started bouldering."), the delete button (red text on a pale red fill instead of
a solid red slab), and the first-call banner icon (a wave instead of a sparkle, which reads as "AI").

Voice and tone rules for any new copy:
- Talk like a thoughtful friend: plain words, second person, short sentences.
- Never blame or guilt anyone ("you haven't", "you forgot", "you missed"). Frame gaps as something to share or ask.
- No urgency and no engagement pressure (no streaks, no "call again soon", no counts of days apart).
- Errors say what happened and what to do next, without "invalid", "failed" or "error".
- KIN never sounds like it is watching: "KIN picked up" and "you heard", not "KIN detected" or "KIN recorded".

Proposed copy changes on the build side (not in my folders):
- Bridge card from the engine: `title` "{name} hasn't heard yet" and `body` phrased in the second person ("you started
  bouldering"), instead of "You haven't told {name}" and "started bouldering".
- iOS shell alerts: "That link is not a KIN invite." could become "This link doesn't open a KIN call. Ask for a new
  invite."; "Please sign up again." could become "Your sign-in expired. Sign up again in a few seconds.";
  "Hang up first to join another call." is fine.
- The shell forces dark mode (`preferredColorScheme(.dark)`). The design supports both; the call screen is always dark.

## Brand: icon, launch screen, film cards

The mark is two overlapping circles: two people's worlds. The overlap, the common ground, is warm amber; the worlds are
translucent white on Meta blue. It stays readable from 1024 down to the 40 point Spotlight size (see
`design/brand/previews/app-icon-sheet.png`). Colors: blue #2A8BFF to #0058D6, amber #FFC94D to #FFA826. The wordmark is
"KIN" in SF Pro Rounded Bold next to the icon tile.

`design/brand/Assets.xcassets` is ready to copy into `ios/Kin/Resources/` (the build session owns `ios/`):
- `AppIcon.appiconset`: one 1024 PNG per iOS 18 appearance (light, dark, tinted). The light icon has no alpha channel,
  as the App Store requires. XcodeGen apps use the `AppIcon` name by default; if not, set
  `ASSETCATALOG_COMPILER_APPICON_NAME: AppIcon`.
- `LaunchBackground.colorset` (#F0F2F5 light, #18191A dark) and `LaunchMark.imageset` (the icon tile, 112 points). In
  `ios/project.yml`, replace `UILaunchScreen: {}` with `UILaunchScreen: {UIColorName: LaunchBackground, UIImageName:
  LaunchMark}`. Previews: `design/brand/previews/launch-screen-light.png` and `-dark.png`. No text on the launch screen,
  per the HIG.
- `AccentColor.colorset`: #0064E0 light, #47A5FA dark.

Launch film cards in `design/brand/film/` (1920 by 1080, for the shot list in `docs/pitch/LAUNCH_VIDEO.md`):

| File | Shot |
|---|---|
| 02a-whos-lin, 02b-six-weeks-ago | 2, the problem (white SF Pro on black, one line each) |
| 03-reveal | 3, wordmark and "Common ground for people who live apart." |
| 06-six-weeks-later | 6, with "Time advanced with a dev clock for this demo." |
| 11-proof | 11, 54% vs 1% bars and "97% wrong vs 0%" for same-name pairs, numbers from `backend/eval/results.md` |
| 13-close | 13, wordmark, tagline, credits line and repo URL |
| overlay-september, overlay-next-day, overlay-no-card | Lower thirds and the "No card." overlay, transparent PNGs |

Render them again with `.build/debug/KinRender --brand ../brand` after any change.

## Round 3: on-demand context and a tiny pause

From the 2026-10-25 additions to PRODUCT.md and the design brief (`POST /api/calls/{id}/explain`, ARCHITECTURE
amendment 5).

### Tap a word for context (call-23 to 25)

KIN's push cards will sometimes miss: it thought Arjun remembered Lin (he heard about her 25 days ago, p 0.40, so no
card). On-demand context is the safety net.

- **Three word treatments in a caption, strongest first.** A word that triggered a card: tinted and dotted-underlined.
  A word KIN recognizes (a name, place or term in the listener's own grounded or linker spans): a faint 1 point solid
  underline at 32 percent white, quiet enough that captions never look like a page of links. Every other word: plain.
- **Any word is tappable,** not only underlined ones. Tapping an unrecognized word sends that word plus its neighbors
  (two-word names like "Xiao Wang") to `explain`; the server's matcher finds the span.
- **Tapping** puts a soft highlight behind the word while the request runs, then the answer appears in the usual card
  slot, replacing any card there. The card says "You asked" (with a tap icon) instead of "New to you" or "Mentioned
  before", so it is obviously a response to you and not KIN interrupting.
- **Nothing known yet** returns the "Who is X?" card, with one extra line: "KIN doesn't know Xiao Wang yet. Add them,
  and next time it can tell you." Relations are social ones from the speaker's world ("Mei's friend", "Mei's
  classmate"), plus "Someone else" and "Not now".
- **Not a name or term** (empty `items`): the highlight fades and nothing else happens. No error, no toast.
- **Discoverability:** a one-time tip above the captions on the first call: "Tap a name to see who it is". It goes away
  after the first tap or the first dismiss and never returns.
- **No gestures** (tilt, shake, long press): phones move too much during calls, and a tap is the most learnable action.
- **Privacy:** the tap and its answer are private to the person tapping; the other person sees nothing change.
- **Implementation hint for SwiftUI:** build the caption as an `AttributedString`, give tappable runs a `.link` like
  `kin://explain?text=Lin&u=91`, style them with `underlineStyle` instead of the default link color, and handle the
  tap with an `OpenURLAction` in the environment. VoiceOver reads links in `Text` as separate elements, so the names in
  a caption become individually reachable without extra work.

### Pause stays tiny (call-11, call-22)

- One tap on the pause button inside the "KIN on" pill. No confirmation and no separate screen.
- Both people's pills change at once: "KIN paused · Resume" for the person who paused, "Paused by Mei · Resume" for the
  other. Either of them can resume with one tap.
- The caption area shows one quiet line, "KIN is taking a break. Nothing is captioned or saved.", and nothing else.
- The point is consent in the moment (Mei about to talk about her mom's surgery, Paatti about Saroja's health), so the
  control has to be instant and the state impossible to miss, but it must not turn the call into a settings screen.
