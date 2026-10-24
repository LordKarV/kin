"""TTS: ElevenLabs HTTP streaming (pcm_16000) with optional consented voice clone; MockTTS for tests.
VERIFIED 2026-10-24: POST /v1/text-to-speech/{voice_id}/stream, header xi-api-key, body {text, model_id, language_code};
eleven_flash_v2_5 (~75 ms) and eleven_multilingual_v2 both support Tamil."""
from __future__ import annotations

import logging
import math
import struct
from typing import AsyncIterator, Protocol

import httpx

from ..config import get_settings

log = logging.getLogger("kin.tts")
BASE = "https://api.elevenlabs.io"


def elevenlabs_request(voice_id: str, text: str, model_id: str, api_key: str, language_code: str) -> tuple[str, dict, dict]:
    url = f"{BASE}/v1/text-to-speech/{voice_id}/stream?output_format=pcm_16000"
    headers = {"xi-api-key": api_key, "accept": "audio/pcm", "content-type": "application/json"}
    body = {"text": text, "model_id": model_id, "language_code": language_code,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8, "speed": 1.0}}
    return url, headers, body


class TTS(Protocol):
    async def stream(self, text: str, voice_id: str, language_code: str) -> AsyncIterator[bytes]: ...


class ElevenLabsTTS:
    def __init__(self, api_key: str, model_id: str, default_voice_id: str):
        self.api_key, self.model_id, self.default_voice_id = api_key, model_id, default_voice_id
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0))

    async def stream(self, text: str, voice_id: str, language_code: str) -> AsyncIterator[bytes]:
        url, headers, body = elevenlabs_request(voice_id or self.default_voice_id, text, self.model_id, self.api_key, language_code)
        async with self._client.stream("POST", url, headers=headers, json=body) as r:
            if r.status_code != 200:
                detail = (await r.aread())[:300]
                raise RuntimeError(f"elevenlabs {r.status_code}: {detail!r}")
            async for chunk in r.aiter_bytes(chunk_size=3200):  # 100 ms of 16 kHz PCM16
                if chunk:
                    yield chunk

    async def clone_voice(self, name: str, wav_bytes: bytes, description: str = "KIN consented voice sample") -> str:
        """Instant voice clone. Caller MUST have checked consents.voice_clone (plan §9)."""
        r = await self._client.post(f"{BASE}/v1/voices/add", headers={"xi-api-key": self.api_key},
                                    data={"name": name, "description": description}, files={"files": ("sample.wav", wav_bytes, "audio/wav")})
        r.raise_for_status()
        return r.json()["voice_id"]


class MockTTS:
    """Emits a short 440 Hz tone (so the audio path is exercised end to end) without any network."""

    async def stream(self, text: str, voice_id: str, language_code: str) -> AsyncIterator[bytes]:
        n = max(1600, min(16000, 800 * len(text.split())))  # ~50 ms per word, 0.1–1 s
        frames = [int(6000 * math.sin(2 * math.pi * 440 * i / 16000)) for i in range(n)]
        pcm = struct.pack(f"<{n}h", *frames)
        for i in range(0, len(pcm), 3200):
            yield pcm[i:i + 3200]


_default: TTS | None = None


def get_tts() -> TTS:
    global _default
    if _default is None:
        s = get_settings()
        if s.tts_provider == "elevenlabs" and s.elevenlabs_api_key:
            _default = ElevenLabsTTS(s.elevenlabs_api_key, s.elevenlabs_model_live, s.elevenlabs_default_voice_id)
        else:
            if s.tts_provider == "elevenlabs":
                log.warning("TTS_PROVIDER=elevenlabs but no ELEVENLABS_API_KEY; using MockTTS tone")
            _default = MockTTS()
    return _default


def reset_tts() -> None:
    global _default
    _default = None
