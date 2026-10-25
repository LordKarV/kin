# Working rules and capabilities

You are plain Claude Code (desktop app) without the user's plugin toolkit (no workflows, no custom skills, no custom
subagents). That is fine for this work. These are the user's standing rules, distilled.

## Tools you have and how to use them here

- Read/Write/Edit files, run shell commands, search. Use them directly; no orchestration needed.
- You can spawn plain subagents for independent research if your build supports it; keep it to one or two.
- macOS with Xcode 27 installed (`/Applications/Xcode-27.0.0.app`), iPhone 16 / 16 Pro / 16e simulators available
  (`xcrun simctl list devices available`).
- Python 3.12 and Node 24 are installed. Do not create a Python venv under `backend/` (that one belongs to the build).

## Verifying SwiftUI mockups (do this, don't just write code)

- Create a standalone Xcode project or Swift package under `design/` (for example `design/KinMockups/`). SwiftUI
  previews are the main artifact: every screen and component gets `#Preview` blocks with realistic sample data from
  `docs/collab/STORIES.md`.
- Build from the command line to prove it compiles, for example:
  `xcodebuild -scheme KinMockups -destination 'platform=iOS Simulator,name=iPhone 16 Pro' build`
- To show the user screens, boot a simulator, install and run the app, then screenshot it:
  `xcrun simctl boot "iPhone 16 Pro"`, `xcrun simctl install booted <path/to/.app>`,
  `xcrun simctl launch booted <bundle id>`, `xcrun simctl io booted screenshot design/screens/<name>.png`.
  Look at every screenshot yourself before claiming a screen is done.
- Sample data only. No networking, no LiveKit, no backend calls in the mockups.

## Git

- Your own branch only (see README). Commit messages: `type(scope): imperative summary`, for example
  `design(call): mockup call screen with gap cards`. Types: feat, fix, docs, design, test, chore.
- No "Co-Authored-By: Claude" or "Generated with Claude" lines in commits or PRs. The user is the only author.
- Commit when a piece is done and verified; push only when the user asks.

## Writing style (docs, comments, commit messages)

- Plain, specific, professional. No em dashes; use commas, colons, parentheses or two sentences. Straight quotes only.
  No emoji anywhere unless the user asks.
- Sentence case headings. Bold sparingly; no "**Label:** description" bullet on every line.
- Specific over generic: "card lands 2 s into the sentence", not "lightning fast".
- Cut puffery (seamless, robust, powerful, elegant, cutting-edge) and filler ("it is worth noting", "in summary").

## Product guardrails you must respect (from docs/PRODUCT.md)

- KIN only speaks when someone would be lost. Designs must make silence the default state: no persistent sidebars full
  of AI chatter, no topic lists, no "you should call X".
- Privacy is visible: everyone can see KIN is on and pause it; bridges are visible only to their owner; third-party
  details are clearly scoped.
- Same app for everyone. No special grandparent mode; design for large type and clarity everywhere instead.
- Do not look or behave like Nudge (photos popping up when events are mentioned, call reminders, AI topic suggestions)
  or Roots (grandma translator with Wikipedia picture bubbles).

## When unsure

Ask the user one specific question rather than guessing on product decisions. For implementation details inside your
own folders, make a sensible choice and note it in your summary.
