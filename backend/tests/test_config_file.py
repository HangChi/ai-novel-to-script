import os
from pathlib import Path

from app.ai_provider import get_ai_provider_status_from_env
from app.config_file import load_config_files


def test_load_config_file_sets_missing_environment_values(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / ".env"
    config_path.write_text(
        "\n".join(
            [
                "# local AI configuration",
                "AI_PROVIDER=deepseek",
                "DEEPSEEK_API_KEY='test-key'",
                'DEEPSEEK_MODEL="deepseek-v4-pro"',
                "DEEPSEEK_BASE_URL=https://api.deepseek.com",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)

    assert load_config_files(paths=[config_path]) == [config_path.resolve()]

    status = get_ai_provider_status_from_env()

    assert status.provider == "deepseek"
    assert status.configured
    assert status.model == "deepseek-v4-pro"
    assert status.base_url == "https://api.deepseek.com"


def test_load_config_file_does_not_override_existing_environment(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / ".env"
    config_path.write_text(
        "\n".join(
            [
                "AI_PROVIDER=deepseek",
                "DEEPSEEK_MODEL=deepseek-v4-pro",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AI_PROVIDER", "local")
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)

    load_config_files(paths=[config_path])

    assert get_ai_provider_status_from_env().provider == "local"
    assert get_ai_provider_status_from_env().model == ""
    assert "DEEPSEEK_MODEL" in os.environ


def test_load_config_file_uses_ai_config_file_path(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "ai.env"
    config_path.write_text("AI_PROVIDER=deepseek\nDEEPSEEK_API_KEY=test-key\n", encoding="utf-8")
    monkeypatch.setenv("AI_CONFIG_FILE", str(config_path))
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    assert load_config_files() == [config_path.resolve()]
    assert get_ai_provider_status_from_env().provider == "deepseek"
