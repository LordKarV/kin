# KinMockups

SwiftUI mockups of the KIN iOS app: components and full screens with previews, built against the real wire contracts.
Design rationale and the design system are in `docs/collab/design-notes.md`.

## Build and render

```bash
cd design/KinMockups
swift build
.build/debug/KinRender ../screens            # every screen + _contact-sheet.png
.build/debug/KinRender ../screens call-04    # only screens whose name starts with call-04
.build/debug/KinRender --brand ../brand      # app icon, launch screen assets, film cards
```

Works with the Command Line Tools alone (no Xcode needed). Open `Package.swift` in Xcode to see the previews.

## Layout

- `Sources/KinDesign/Contracts/Contracts.swift`: mirror of `ios/Kin/Sources/Contracts/Contracts.swift` (do not edit; re-copy).
- `Theme/`: tokens (color, type, spacing, motion), localized chrome strings, phone chrome and the render-safe scroll view.
- `Components/`: KIN indicator, call controls, captions, cards (who/what/term, meaning, storyline, ask, bridge), avatar,
  video stand-in, and the shared app UI kit.
- `Screens/`: call states, audio call, setup, people, a person's world, messages, you.
- `Sample/`: demo data as wire JSON, decoded through the contracts.
- `Sources/KinRender/`: renders `design/screens/`.

## Lifting into the app

Components are plain views over value types with no networking or singletons. Delete the mirrored `Contracts.swift`
and the sample data, keep `Theme/` and `Components/`, and they compile against the real contracts unchanged. The
renderer-only pieces (`PhoneChrome`, `VideoPlaceholder`, the macOS branch of `KinScroll`) are not needed in the app.
