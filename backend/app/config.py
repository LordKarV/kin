"""Environment-driven settings. Every external detail (model ids, base URLs, providers) lives here."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_HERE = Path(__file__).resolve().parent.parent  # backend/
_ENV_FILES = (str(_HERE.parent / ".env"), str(_HERE / ".env"))  # repo-root .env then backend/.env


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILES, env_file_encoding="utf-8", extra="ignore")

    # LLM (Meta Model API, OpenAI-compatible). VERIFIED 2026-10-24, see docs/DECISIONS.md
    llm_base_url: str = "https://api.meta.ai/v1"
    llm_model: str = "muse-spark-1.3"
    model_api_key: str = ""
    model_api_key_backup: str = ""
    llm_reasoning_effort: str = "low"
    llm_timeout_s: float = 20.0

    # ASR
    asr_provider: str = "muse"  # muse | deepgram | mock
    deepgram_api_key: str = ""
    asr_heritage_lang: str = "ta"
    asr_sample_rate: int = 16000

    # TTS
    tts_provider: str = "elevenlabs"  # elevenlabs | mock
    elevenlabs_api_key: str = ""
    elevenlabs_model_live: str = "eleven_flash_v2_5"
    elevenlabs_model_glossary: str = "eleven_multilingual_v2"
    elevenlabs_default_voice_id: str = ""

    # Transport
    transport: str = "websocket"  # websocket | livekit
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""

    # Phone bridge
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_number: str = ""
    public_wss_host: str = ""

    # Data
    database_url: str = f"sqlite:///{_HERE / 'kin.db'}"  # absolute so scripts from any cwd share one DB
    embeddings_provider: str = "none"
    kin_api_key: str = "change-me"
    demo_family_id: int = 1


@lru_cache
def get_settings() -> Settings:
    return Settings()
