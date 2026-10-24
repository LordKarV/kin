"""Glossary artifact audio: each pragmatics card gets a short clip of its source phrase, spoken in the heritage language
(ElevenLabs eleven_multilingual_v2 when a key is present, otherwise the mock tone). Files live under backend/media and
are served at /media/...; the clip is the phrase only, never the whole utterance (plan §9: audio is not retained)."""
from __future__ import annotations

import asyncio
import io
import logging
import wave
from pathlib import Path

from ..config import get_settings
from ..db import models as m
from ..db.session import session_scope
from .tts import ElevenLabsTTS, MockTTS, TTS

log = logging.getLogger("kin.glossary")
MEDIA_DIR = Path(__file__).resolve().parents[2] / "media"
_tts: TTS | None = None


def media_dir() -> Path:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    return MEDIA_DIR


def get_glossary_tts() -> TTS:
    global _tts
    if _tts is None:
        s = get_settings()
        _tts = ElevenLabsTTS(s.elevenlabs_api_key, s.elevenlabs_model_glossary, s.elevenlabs_default_voice_id) if (s.tts_provider == "elevenlabs" and s.elevenlabs_api_key) else MockTTS()
    return _tts


def pcm16_to_wav(pcm: bytes, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm)
    return buf.getvalue()


async def synthesize_card_audio(entry_id: int, phrase: str, language_code: str, voice_id: str = "") -> str | None:
    try:
        chunks = [c async for c in get_glossary_tts().stream(phrase, voice_id=voice_id, language_code=language_code)]
        out = media_dir() / "glossary"; out.mkdir(exist_ok=True)
        path = out / f"{entry_id}.wav"
        path.write_bytes(pcm16_to_wav(b"".join(chunks)))
        url = f"/media/glossary/{entry_id}.wav"
        with session_scope() as s:
            e = s.get(m.GlossaryEntry, entry_id)
            if e:
                e.audio_url = url
        return url
    except Exception as e:  # noqa: BLE001
        log.warning("glossary audio failed for %s: %s", entry_id, e)
        return None


def schedule_card_audio(entries: list[tuple[int, str]], language_code: str, voice_id: str = "") -> None:
    for entry_id, phrase in entries:
        asyncio.create_task(synthesize_card_audio(entry_id, phrase, language_code, voice_id))
