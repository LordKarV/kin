"""Meta Muse Voice Transcribe realtime (VERIFIED 2026-10-24 at dev.meta.ai/docs/speech-to-text):
wss://api.meta.ai/v1/asr/realtime; first text frame = JSON handshake with authorization.accessToken (the HTTP header is ignored);
binary frames = signed 16-bit LE mono PCM (PCM_16KHZ or PCM_24KHZ); server events carry `type`; {"type":"endStream"} closes input.
Supports 25 languages incl. Tamil with code-switching; `keywords` biases names; NO word timestamps (turn-level only).
VERIFY at the venue: the exact `model` handshake value (docs list `muse-voice-transcribe-1.0` as the model id)."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator

from .asr import ASREvent

log = logging.getLogger("kin.asr.muse")
URL = "wss://api.meta.ai/v1/asr/realtime"


def muse_handshake(api_key: str, keywords: list[str], language_bias: list[str], model: str = "muse-voice-transcribe-1.0") -> dict:
    return {
        "authorization": {"accessToken": f"Bearer {api_key}"},
        "audioEncoding": "PCM_16KHZ",
        "model": model,
        "mode": "ENDPOINTING",
        "partialMode": "CUMULATIVE",
        "emitAudioProgress": False,
        "languageBias": language_bias,
        "keywords": keywords[:100],
    }


def parse_muse_event(msg: dict) -> ASREvent | None:
    t = msg.get("type")
    if t == "transcript":
        text = (msg.get("transcript") or "").strip()
        if not text or msg.get("final"):
            return None  # finals arrive as speechComplete
        return ASREvent(text=text, final=False, t_end=float(msg.get("audioProcessedMs", 0)) / 1000.0)
    if t == "speechComplete":
        text = (msg.get("transcript") or "").strip()
        return ASREvent(text=text, final=True, turn_id=msg.get("turnId")) if text else None
    if t == "error":
        log.warning("muse asr error: %s", msg.get("message"))
    return None


class MuseASR:
    def __init__(self, api_key: str, keywords: list[str], language_bias: list[str]):
        self.handshake = muse_handshake(api_key, keywords, language_bias)
        self._ws = None
        self._q: asyncio.Queue[ASREvent | None] = asyncio.Queue()
        self._reader: asyncio.Task | None = None

    async def start(self) -> None:
        import websockets
        self._ws = await websockets.connect(URL, open_timeout=10)
        await self._ws.send(json.dumps(self.handshake))
        first = json.loads(await asyncio.wait_for(self._ws.recv(), timeout=10))
        if "sessionId" not in first:
            raise RuntimeError(f"muse asr handshake failed: {first}")
        self._reader = asyncio.create_task(self._read())

    async def _read(self) -> None:
        try:
            async for raw in self._ws:
                if isinstance(raw, bytes):
                    continue
                ev = parse_muse_event(json.loads(raw))
                if ev:
                    await self._q.put(ev)
        except Exception as e:  # noqa: BLE001
            log.warning("muse stream closed: %s", e)
        finally:
            await self._q.put(None)

    async def send_audio(self, pcm16: bytes) -> None:
        if self._ws:
            await self._ws.send(pcm16)

    async def finish(self) -> None:
        if self._ws:
            try:
                await self._ws.send(json.dumps({"type": "endStream"}))
                await asyncio.wait_for(self._ws.close(), timeout=3)
            except Exception:  # noqa: BLE001
                pass

    async def events(self) -> AsyncIterator[ASREvent]:
        while True:
            ev = await self._q.get()
            if ev is None:
                return
            yield ev
