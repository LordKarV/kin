import os
import pytest

@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    """Tests never touch real providers or the real DB."""
    for k in list(os.environ):
        if k.startswith(("LLM_", "MODEL_API", "DEEPGRAM", "ELEVENLABS", "TWILIO", "LIVEKIT", "ASR_", "TTS_", "KIN_", "DATABASE_URL", "TRANSPORT", "EMBEDDINGS")):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("ASR_PROVIDER", "mock")
    monkeypatch.setenv("TTS_PROVIDER", "mock")
    monkeypatch.setenv("MODEL_API_KEY", "test-key")
    from app import config
    from app.db.session import reset_engine
    from app.mt.translate import reset_translator_cache
    from app.audio.tts import reset_tts
    config.get_settings.cache_clear(); reset_engine(); reset_translator_cache(); reset_tts()
    yield
    config.get_settings.cache_clear(); reset_engine(); reset_translator_cache(); reset_tts()
