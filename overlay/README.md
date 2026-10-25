# KIN overlay

A desktop layer over the call you are already on (Zoom, Google Meet, FaceTime, WhatsApp desktop, anything that plays
audio). It listens to the other side of the call, sends it to the KIN backend, and pops up family-grounded captions
and "who / what is this" cards in always-on-top transparent windows. No bot joins the meeting and the other person
installs nothing.

The overlay is language-agnostic: it shows whatever the backend returns for the family's `heritage_lang`, and names
the language with `Intl.DisplayNames`.

## Run

```bash
# backend running on :8000 (see ../README.md)
cd overlay
npm install
npm run build:native   # macOS only: builds native/syscap (needs Xcode command line tools)
npm start
```

Pick who is on the other end, leave the source on "Call audio (system)", press Start listening, then start or join
the call. Ctrl/Cmd+Shift+K hides and shows the overlay.

| Env var | Default | Meaning |
|---|---|---|
| `KIN_URL` | `http://localhost:8000` | KIN backend |
| `KIN_KEY` | (empty) | API key when the backend is locked (`KIN_API_KEY`) |
| `KIN_CAPTURE_APPS` | (all audio) | macOS only: comma-separated bundle ids to capture, e.g. `us.zoom.xos,com.google.Chrome,com.apple.FaceTime,net.whatsapp.WhatsApp` |

## How audio is captured

| OS | Source | How |
|---|---|---|
| macOS 13+ | Call audio | `native/syscap`: ScreenCaptureKit audio-only stream, 16 kHz mono, PCM16 to stdout (same pattern as Cluely clones such as cheating-daddy's `SystemAudioDump`). Needs Screen Recording permission for the app (in dev, for your terminal). |
| Windows | Call audio | Electron `setDisplayMediaRequestHandler` with `audio: 'loopback'` in a hidden window. Not yet tested on a Windows machine. |
| any | Microphone | `getUserMedia`; works with the call on laptop speakers, and is the fallback if system capture is blocked. |

The overlay joins the call as the `grandparent` leg only, so the backend never sends TTS audio to play (the call
already carries their voice). The reply direction (grandchild to grandparent) is not wired here: playing a translated
reply into Zoom needs a virtual microphone.

## Screen share

All overlay windows call `setContentProtection(true)`. That hides them from screen share on Windows; on macOS,
ScreenCaptureKit-based sharers can still capture them, so treat it as best effort.

## Tests

`npm test` runs the pure-logic tests in `test/` (caption HTML escaping, card dedupe, PCM framing, speaker picker).
