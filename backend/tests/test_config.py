from app.config import get_settings

def test_defaults_point_at_meta_model_api():
    s = get_settings()
    assert s.llm_base_url == "https://api.meta.ai/v1"
    assert s.llm_model == "muse-spark-1.3"
    assert s.asr_provider == "mock"

def test_env_overrides_model(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "muse-spark-1.1")
    get_settings.cache_clear()
    assert get_settings().llm_model == "muse-spark-1.1"
