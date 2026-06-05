import pytest

from app.ai_provider import (
    AIProviderError,
    LocalScriptAIProvider,
    OpenAICompatibleScriptAIProvider,
    create_ai_provider_from_env,
)
from app.chapter_parser import parse_novel_chapters
from app.script_draft import build_script_yaml


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
