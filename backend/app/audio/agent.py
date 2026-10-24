"""Optional LiveKit Agents worker (TRANSPORT=livekit). Not wired in the default build: the team has no LiveKit key yet,
so the WebSocket transport in api/ws.py is primary (plan §3.4 FALLBACK). This adapter shows where LiveKit plugs in:
subscribe to each participant's audio track → CallSession.on_audio(role, pcm16) → publish TTS bytes via an AudioSource.
Install with `pip install -e ".[livekit]"` and VERIFY the current livekit-agents API before use."""
from __future__ import annotations


def main() -> None:  # pragma: no cover
    raise SystemExit("LiveKit transport is optional and not configured; see docs/DECISIONS.md")
