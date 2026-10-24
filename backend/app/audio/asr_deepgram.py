"""Deepgram nova-3 streaming (VERIFIED 2026-10-24: wss://api.deepgram.com/v1/listen, `keyterm` repeated, Tamil = language=ta,
not available in `multi`). Auth header: `Authorization: Token <key>`."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator
from urllib.parse import urlencode

from .asr import ASREvent

log = logging.getLogger("kin.asr.deepgram")
MAX_KEYTERMS = 100


def deepgram_url(language: str, sample_rate: int, keyterms: list[str]) -> str:
    params = [("model", "nova-3"), ("language", language), ("encoding", "linear16"), ("sample_rate", str(sample_rate)), ("channels", "1"),
              ("interim_results", "true"), ("smart_format", "true"), ("punctuate", "true"), ("endpointing", "300"), ("utterance_end_ms", "1200"),
              ("vad_events", "true")]
    params += [("keyterm", k) for k in keyterms[:MAX_KEYTERMS]]
    return "wss://api.deepgram.com/v1/listen?" + urlencode(params)


def parse_deepgram_message(raw: str) -> ASREvent | None:
    msg = json.loads(raw)
    if msg.get("type") != "Results":
        return None
    alts = (msg.get("channel") or {}).get("alternatives") or []
    if not alts:
        return None
    a = alts[0]
    text = (a.get("transcript") or "").strip()
    if not text:
        return None
    words = a.get("words") or []
    final = bool(msg.get("is_final"))
    start = float(msg.get("start", 0.0))
    t_end = max((w.get("end", 0.0) for w in words), default=start + float(msg.get("duration", 0.0)))
    langs = sorted({w["language"] for w in words if w.get("language")})
    return ASREvent(text=text, final=final, t_start=start, t_end=t_end, lang_tags=langs, words=words, confidence=float(a.get("confidence", 0.0)))


class DeepgramASR:
    def __init__(self, api_key: str, language: str, sample_rate: int, keyterms: list[str]):
        self.url = deepgram_url(language, sample_rate, keyterms)
        self.api_key = api_key
        self._ws = None
        self._q: asyncio.Queue[ASREvent | None] = asyncio.Queue()
        self._reader: asyncio.Task | None = None
        self._ka: asyncio.Task | None = None

    async def start(self) -> None:
        import websockets
        self._ws = await websockets.connect(self.url, additional_headers={"Authorization": f"Token {self.api_key}"}, open_timeout=10)
        self._reader = asyncio.create_task(self._read())
        self._ka = asyncio.create_task(self._keepalive())

    async def _read(self) -> None:
        try:
            async for raw in self._ws:
                try:
                    ev = parse_deepgram_message(raw)
                except Exception as e:  # noqa: BLE001
                    log.warning("bad deepgram message: %s", e); continue
                if ev:
                    await self._q.put(ev)
        except Exception as e:  # noqa: BLE001
            log.warning("deepgram stream closed: %s", e)
        finally:
            await self._q.put(None)

    async def _keepalive(self) -> None:
        try:
            while True:
                await asyncio.sleep(5)
                await self._ws.send(json.dumps({"type": "KeepAlive"}))
        except Exception:  # noqa: BLE001
            return

    async def send_audio(self, pcm16: bytes) -> None:
        if self._ws:
            await self._ws.send(pcm16)

    async def finish(self) -> None:
        if self._ka:
            self._ka.cancel()
        if self._ws:
            try:
                await self._ws.send(json.dumps({"type": "CloseStream"}))
                await asyncio.wait_for(self._ws.close(), timeout=3)
            except Exception:  # noqa: BLE001
                pass

    async def events(self) -> AsyncIterator[ASREvent]:
        while True:
            ev = await self._q.get()
            if ev is None:
                return
            yield ev
