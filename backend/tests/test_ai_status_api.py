from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_ai_status_returns_local_provider_by_default() -> None:
    response = client.get("/api/ai/status")

    assert response.status_code == 200
    assert response.json() == {
        "provider": "local",
        "mode": "local",
        "configured": True,
        "model": "",
        "base_url": "",
        "missing_config": [],
    }


def test_ai_status_reports_deepseek_configuration_without_secret(monkeypatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret-key")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-pro")

    response = client.get("/api/ai/status")

    assert response.status_code == 200
    payload = response.json()

    assert payload == {
        "provider": "deepseek",
        "mode": "remote",
        "configured": True,
        "model": "deepseek-v4-pro",
        "base_url": "https://api.deepseek.com",
        "missing_config": [],
    }
    assert "secret-key" not in str(payload)
