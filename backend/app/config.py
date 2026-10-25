"""Environment-driven settings. Every external detail (model ids, base URLs, providers) lives here."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_HERE = Path(__file__).resolve().parent.parent  # backend/
_ENV_FILES = (str(_HERE.parent / ".env"), str(_HERE / ".env"))  # repo-root .env then backend/.env


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILES, env_file_encoding="utf-8", extra="ignore")

    # LLM (Meta Model API, OpenAI-compatible). VERIFIED 2026-10-24
    llm_base_url: str = "https://api.meta.ai/v1"
    llm_model: str = "muse-spark-1.3"
    model_api_key: str = ""
    model_api_key_backup: str = ""
    llm_reasoning_effort: str = "low"
    llm_timeout_s: float = 20.0

    # ASR
    asr_provider: str = "muse"  # muse | mock
    asr_sample_rate: int = 16000

    # TTS
    tts_provider: str = "elevenlabs"  # elevenlabs | mock
    elevenlabs_api_key: str = ""
    elevenlabs_model_live: str = "eleven_flash_v2_5"
    elevenlabs_default_voice_id: str = ""
    elevenlabs_base_url: str = "https://api.elevenlabs.io"

    # Calls (LiveKit)
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    # Fallbacks when LIVEKIT_* are unset: the credentials `livekit-server --dev` prints (local development only).
    livekit_dev_url: str = "ws://localhost:7880"
    livekit_dev_key: str = "devkey"
    livekit_dev_secret: str = "secret"

    public_wss_host: str = ""  # set when the server is reachable from the internet: the API key is then required

    # Data
    database_url: str = f"sqlite:///{_HERE / 'kin.db'}"  # absolute so scripts from any cwd share one DB
    kin_api_key: str = "change-me"
    sample_family_id: int = 1
    seed_sample_family: bool = False  # nothing pre-seeded; the evaluation opts in

    # World (common-ground engine)
    third_party_ttl_days: int = 120  # third-party facts expire after this many days unless pinned
    clock_offset_days: float = 0  # initial world/clock offset; /api/dev/clock changes it at runtime
    bridge_rerank: bool = False
    dev_endpoints: bool = False  # /api/dev/* (clock, plant, typed texts): local development only (DEV_ENDPOINTS=1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
