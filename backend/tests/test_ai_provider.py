from pathlib import Path

import pytest
import yaml

from app.ai_provider import (
    AIProviderError,
    LocalScriptAIProvider,
    OpenAICompatibleScriptAIProvider,
    create_ai_provider_from_env,
    get_ai_provider_status_from_env,
)
from app.chapter_parser import parse_novel_chapters
from app.script_draft import build_script_yaml
from app.script_validator import validate_script_yaml


AI_QUALITY_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ai_quality_outputs.yaml"


def _ai_quality_cases() -> list[dict[str, str]]:
    return yaml.safe_load(AI_QUALITY_FIXTURE_PATH.read_text(encoding="utf-8"))


def _valid_yaml() -> str:
    chapters = parse_novel_chapters(
        """
Chapter 1
The door opens.

Chapter 2
The letter appears.

Chapter 3
The choice is made.
"""
    )

    return build_script_yaml(title="Rain Letter", chapters=chapters)


def test_local_provider_returns_skeleton_yaml() -> None:
    skeleton_yaml = _valid_yaml()

    assert LocalScriptAIProvider().generate_script_yaml("Rain Letter", skeleton_yaml) == skeleton_yaml


def test_create_provider_defaults_to_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_PROVIDER", raising=False)

    assert isinstance(create_ai_provider_from_env(), LocalScriptAIProvider)


def test_ai_provider_status_defaults_to_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_PROVIDER", raising=False)

    assert get_ai_provider_status_from_env().to_dict() == {
        "provider": "local",
        "mode": "local",
        "configured": True,
        "model": "",
        "base_url": "",
        "missing_config": [],
    }


def test_ai_provider_status_reports_openai_missing_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    status = get_ai_provider_status_from_env()

    assert status.provider == "openai"
    assert status.mode == "remote"
    assert not status.configured
    assert status.model == ""
    assert status.base_url == "https://api.openai.com/v1"
    assert status.missing_config == ["OPENAI_API_KEY", "OPENAI_MODEL"]


def test_ai_provider_status_reports_configured_deepseek_without_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret-key")
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)

    status = get_ai_provider_status_from_env().to_dict()

    assert status == {
        "provider": "deepseek",
        "mode": "remote",
        "configured": True,
        "model": "deepseek-v4-flash",
        "base_url": "https://api.deepseek.com",
        "missing_config": [],
    }
    assert "secret-key" not in str(status)


def test_ai_provider_status_reports_unsupported_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "unknown")

    assert get_ai_provider_status_from_env().to_dict() == {
        "provider": "unknown",
        "mode": "unsupported",
        "configured": False,
        "model": "",
        "base_url": "",
        "missing_config": ["AI_PROVIDER"],
    }


def test_create_provider_builds_openai_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("OPENAI_TEMPERATURE", "0.1")
    monkeypatch.setenv("AI_PROVIDER_TIMEOUT_SECONDS", "5")

    provider = create_ai_provider_from_env()

    assert isinstance(provider, OpenAICompatibleScriptAIProvider)
    assert provider.api_key == "test-key"
    assert provider.model == "test-model"
    assert provider.base_url == "https://example.test/v1"
    assert provider.temperature == 0.1
    assert provider.timeout_seconds == 5


def test_create_provider_builds_deepseek_provider_with_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_TEMPERATURE", raising=False)
    monkeypatch.delenv("AI_PROVIDER_TIMEOUT_SECONDS", raising=False)

    provider = create_ai_provider_from_env()

    assert isinstance(provider, OpenAICompatibleScriptAIProvider)
    assert provider.api_key == "test-key"
    assert provider.model == "deepseek-v4-flash"
    assert provider.base_url == "https://api.deepseek.com"
    assert provider.temperature == 0.3
    assert provider.timeout_seconds == 60.0
    assert provider.provider_name == "deepseek"
    assert provider.api_key_env_name == "DEEPSEEK_API_KEY"
    assert provider.model_env_name == "DEEPSEEK_MODEL"


def test_create_provider_builds_deepseek_provider_with_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://example.test")
    monkeypatch.setenv("DEEPSEEK_TEMPERATURE", "0.2")
    monkeypatch.setenv("AI_PROVIDER_TIMEOUT_SECONDS", "10")

    provider = create_ai_provider_from_env()

    assert isinstance(provider, OpenAICompatibleScriptAIProvider)
    assert provider.model == "deepseek-v4-pro"
    assert provider.base_url == "https://example.test"
    assert provider.temperature == 0.2
    assert provider.timeout_seconds == 10


def test_deepseek_provider_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "deepseek")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    with pytest.raises(AIProviderError, match="DEEPSEEK_API_KEY"):
        create_ai_provider_from_env()


def test_openai_provider_requires_model() -> None:
    with pytest.raises(AIProviderError, match="OPENAI_MODEL"):
        OpenAICompatibleScriptAIProvider(api_key="test-key", model="")


def test_openai_provider_strips_fenced_yaml_and_validates(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICompatibleScriptAIProvider(api_key="test-key", model="test-model")
    valid_yaml = _valid_yaml()

    def fake_request_completion(self, payload):
        return f"```yaml\n{valid_yaml}```"

    monkeypatch.setattr(OpenAICompatibleScriptAIProvider, "_request_completion", fake_request_completion)

    assert provider.generate_script_yaml("Rain Letter", "skeleton") == valid_yaml.strip()


def test_openai_provider_retries_once_to_repair_invalid_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICompatibleScriptAIProvider(api_key="test-key", model="test-model")
    valid_yaml = _valid_yaml()
    calls = []

    def fake_request_completion(self, payload):
        calls.append(payload)

        if len(calls) == 1:
            return "script:\n  title: Rain Letter\n"

        return valid_yaml

    monkeypatch.setattr(OpenAICompatibleScriptAIProvider, "_request_completion", fake_request_completion)

    assert provider.generate_script_yaml("Rain Letter", "skeleton") == valid_yaml.strip()
    assert len(calls) == 2

    repair_messages = calls[1]["messages"]
    assert repair_messages[-2]["role"] == "assistant"
    assert "script:\n  title: Rain Letter" in repair_messages[-2]["content"]
    assert repair_messages[-1]["role"] == "user"
    assert "Validation errors" in repair_messages[-1]["content"]
    assert "script.schema_version" in repair_messages[-1]["content"]
    assert "return YAML only" in repair_messages[-1]["content"]


def test_openai_provider_reports_repaired_yaml_validation_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICompatibleScriptAIProvider(api_key="test-key", model="test-model")
    calls = []

    def fake_request_completion(self, payload):
        calls.append(payload)
        return "script:\n  title: Rain Letter\n"

    monkeypatch.setattr(OpenAICompatibleScriptAIProvider, "_request_completion", fake_request_completion)

    with pytest.raises(AIProviderError, match="script.schema_version"):
        provider.generate_script_yaml("Rain Letter", "skeleton")

    assert len(calls) == 2


@pytest.mark.parametrize("case", _ai_quality_cases(), ids=lambda case: case["id"])
def test_openai_provider_accepts_quality_fixture_outputs(monkeypatch: pytest.MonkeyPatch, case: dict[str, str]) -> None:
    provider = OpenAICompatibleScriptAIProvider(api_key="test-key", model="test-model")

    def fake_request_completion(self, payload):
        return case["output"]

    monkeypatch.setattr(OpenAICompatibleScriptAIProvider, "_request_completion", fake_request_completion)

    result = provider.generate_script_yaml(case["title"], _valid_yaml())
    validation = validate_script_yaml(result)
    script = yaml.safe_load(result)["script"]
    beat_types = {
        beat["type"]
        for scene in script["scenes"]
        for beat in scene["beats"]
    }

    assert validation.valid
    assert script["title"] == case["title"]
    assert script["logline"].strip()
    assert script["characters"]
    assert len(script["scenes"]) == script["source"]["chapters_count"]
    assert {"action", "dialogue", "narration", "transition"}.issubset(beat_types)
    assert all(scene["location"] != "TBD" and scene["time"] != "TBD" for scene in script["scenes"])


def test_openai_provider_prompt_requests_complete_screenplay_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICompatibleScriptAIProvider(api_key="test-key", model="test-model")
    captured_payload = {}

    def fake_request_completion(self, payload):
        captured_payload.update(payload)
        return _valid_yaml()

    monkeypatch.setattr(OpenAICompatibleScriptAIProvider, "_request_completion", fake_request_completion)

    provider.generate_script_yaml("Rain Letter", _valid_yaml())

    messages = captured_payload["messages"]
    system_prompt = messages[0]["content"]
    user_prompt = messages[1]["content"]

    assert "script.logline" in system_prompt
    assert "script.characters" in system_prompt
    assert "location" in system_prompt
    assert "dialogue" in system_prompt
    assert "source_chapter" in system_prompt
    assert "do not invent unrelated events" in system_prompt
    assert "Title: Rain Letter" in user_prompt
    assert "ordered beats" in user_prompt


def test_openai_provider_rejects_invalid_yaml_response(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICompatibleScriptAIProvider(api_key="test-key", model="test-model")

    def fake_request_completion(self, payload):
        return "script:\n  title: Rain Letter\n"

    monkeypatch.setattr(OpenAICompatibleScriptAIProvider, "_request_completion", fake_request_completion)

    with pytest.raises(AIProviderError, match="AI response did not match YAML schema"):
        provider.generate_script_yaml("Rain Letter", "skeleton")
