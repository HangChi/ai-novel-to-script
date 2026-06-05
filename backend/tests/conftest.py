import pytest


@pytest.fixture(autouse=True)
def use_local_ai_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "local")
