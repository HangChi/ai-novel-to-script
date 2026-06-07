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
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)

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


def test_ai_models_lists_selectable_models_without_secrets(monkeypatch) -> None:
    monkeypatch.setenv("KIMI_API_KEY", "kimi-secret")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("GLM_API_KEY", raising=False)

    response = client.get("/api/ai/models")

    assert response.status_code == 200
    payload = response.json()
    models = {model["id"]: model for model in payload["models"]}

    assert payload["default_model_id"] == "local"
    assert models["local"]["configured"] is True
    assert models["deepseek-v4-pro"]["model"] == "deepseek-v4-pro"
    assert models["deepseek-v4-pro"]["missing_config"] == ["DEEPSEEK_API_KEY"]
    assert models["kimi-2.6"]["configured"] is True
    assert models["kimi-2.6"]["model"] == "kimi-k2.6"
    assert models["glm-4.7-flashx"]["missing_config"] == ["GLM_API_KEY"]
    assert "kimi-secret" not in str(payload)
