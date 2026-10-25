"""Streaming ASR abstraction. Providers: muse (Meta Muse Voice Transcribe), deepgram, mock. Chosen by ASR_PROVIDER."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import AsyncIterator, Protocol

from ..config import get_settings


@dataclass
class ASREvent:
    text: str
    final: bool
    t_start: float = 0.0          # seconds from stream start (0 if the provider has no timestamps)
    t_end: float = 0.0
    lang_tags: list[str] = field(default_factory=list)
    words: list[dict] = field(default_factory=list)  # [{word, start, end, language}] when available
    speaker: str | None = None
    turn_id: str | None = None
    confidence: float = 0.0


class ASRSession(Protocol):
    async def start(self) -> None: ...
    async def send_audio(self, pcm16: bytes) -> None: ...
    async def finish(self) -> None: ...
    def events(self) -> AsyncIterator[ASREvent]: ...


class MockASR:
    """No real recognition: audio is swallowed; tests and the typed-input demo path bypass ASR entirely."""

    def __init__(self, *_, **__):
        self._q: asyncio.Queue[ASREvent | None] = asyncio.Queue()

    async def start(self) -> None:
        return None

    async def send_audio(self, pcm16: bytes) -> None:
        return None

    async def inject(self, text: str) -> None:
        await self._q.put(ASREvent(text=text, final=True))

    async def finish(self) -> None:
        await self._q.put(None)

    async def events(self) -> AsyncIterator[ASREvent]:
        while True:
            ev = await self._q.get()
            if ev is None:
                return
            yield ev


def make_asr(language: str, keyterms: list[str]) -> ASRSession:
    s = get_settings()
    if s.asr_provider == "deepgram":
        from .asr_deepgram import DeepgramASR
        return DeepgramASR(api_key=s.deepgram_api_key, language=language, sample_rate=s.asr_sample_rate, keyterms=keyterms)
    if s.asr_provider == "muse":
        from ..graph.kin_tables import MUSE_LANGUAGES
        from .asr_muse import MuseASR
        # VERIFIED: languageBias takes language NAMES (the docs example lists full names), not codes
        name = MUSE_LANGUAGES.get(language, language)
        heritage = MUSE_LANGUAGES.get(s.asr_heritage_lang, s.asr_heritage_lang)
        bias = [name, "English"] if language != "en" else ["English", heritage]
        return MuseASR(api_key=s.model_api_key, keywords=keyterms, language_bias=list(dict.fromkeys(bias)))
    return MockASR()


def make_bilingual_asr(heritage_lang: str, keyterms: list[str]) -> ASRSession:
    """One stream that hears BOTH people on a merged phone call. That needs code-switching across the heritage
    language and English, which Muse Voice Transcribe does (25 languages); Deepgram here is one language per stream."""
    s = get_settings()
    if s.asr_provider == "mock":
        return MockASR()
    from ..graph.kin_tables import MUSE_LANGUAGES
    from .asr_muse import MuseASR
    bias = [MUSE_LANGUAGES.get(heritage_lang, heritage_lang), "English"]
    return MuseASR(api_key=s.model_api_key, keywords=keyterms, language_bias=list(dict.fromkeys(bias)))
