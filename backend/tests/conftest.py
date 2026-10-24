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
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()
