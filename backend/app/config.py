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
    elevenlabs_base_url: str = "https://api.elevenlabs.io"
    glossary_audio: bool = False  # per-card TTS clips cost ElevenLabs characters; opt in with GLOSSARY_AUDIO=1

    # Transport
    transport: str = "websocket"  # websocket | livekit
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    # Fallbacks when LIVEKIT_* are unset: the credentials `livekit-server --dev` prints (local development only).
    livekit_dev_url: str = "ws://localhost:7880"
    livekit_dev_key: str = "devkey"
    livekit_dev_secret: str = "secret"

    # Phone bridge
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_number: str = ""
    public_wss_host: str = ""
    twilio_heritage_lang: str = ""  # override; default = the family language table's locale (VERIFY in ConversationRelay voice configuration)

    # Data
    database_url: str = f"sqlite:///{_HERE / 'kin.db'}"  # absolute so scripts from any cwd share one DB
    embeddings_provider: str = "none"
    kin_api_key: str = "change-me"
    demo_family_id: int = 1
    seed_demo_family: bool = False  # nothing pre-seeded: families are built by the user (setup + cards). Tests/eval opt in.

    # World (common-ground engine)
    third_party_ttl_days: int = 120  # must exceed the 6-week demo gap (ARCHITECTURE D11)
    clock_offset_days: float = 0  # initial world/clock offset; /api/dev/clock changes it at runtime
    bridge_rerank: bool = False
    dev_endpoints: bool = False  # /api/dev/* (clock, plant, simulated SMS): on only for tests, eval and the demo (DEV_ENDPOINTS=1)
    sms_number: str = ""  # the KIN SMS number shown in the app


@lru_cache
def get_settings() -> Settings:
    return Settings()
