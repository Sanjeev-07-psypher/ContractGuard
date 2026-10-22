import pytest

from contractguard.config import clear_caches


@pytest.fixture(autouse=True)
def _fresh_config(monkeypatch):
    """Isolate tests from a developer's .env and cached settings."""
    for var in ("LLM_PROVIDER", "LLM_MODEL", "GEMINI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    clear_caches()
    yield
    clear_caches()
