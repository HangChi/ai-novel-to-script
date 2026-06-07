from pathlib import Path

import pytest
import yaml

from app.ai_provider import (
    AIProviderError,
    LocalScriptAIProvider,
    OpenAICompatibleScriptAIProvider,
    create_ai_provider_from_env,
    generate_script_with_ai,
    get_ai_model_options_from_env,
    get_default_ai_model_id_from_env,
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
        "model": "deepseek-v4-pro",
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
    assert provider.model == "deepseek-v4-pro"
    assert provider.base_url == "https://api.deepseek.com"
    assert provider.temperature == 0.3
    assert provider.timeout_seconds == 60.0
    assert provider.provider_name == "deepseek"
    assert provider.api_key_env_name == "DEEPSEEK_API_KEY"
    assert provider.model_env_name == "DEEPSEEK_MODEL"


def test_ai_model_options_report_remote_missing_api_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "DEEPSEEK_API_KEY",
        "KIMI_API_KEY",
        "GLM_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    options = {option.id: option.to_dict() for option in get_ai_model_options_from_env()}

    assert options["local"]["configured"] is True
    assert options["deepseek-v4-pro"]["model"] == "deepseek-v4-pro"
    assert options["deepseek-v4-pro"]["missing_config"] == ["DEEPSEEK_API_KEY"]
    assert options["kimi-2.6"]["model"] == "kimi-k2.6"
    assert options["kimi-2.6"]["base_url"] == "https://api.moonshot.cn/v1"
    assert options["kimi-2.6"]["missing_config"] == ["KIMI_API_KEY"]
    assert options["glm-4.7-flashx"]["model"] == "glm-4.7-flashx"
    assert options["glm-4.7-flashx"]["base_url"] == "https://open.bigmodel.cn/api/paas/v4"
    assert options["glm-4.7-flashx"]["missing_config"] == ["GLM_API_KEY"]


def test_default_ai_model_id_can_follow_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODEL_ID", "kimi-2.6")
    monkeypatch.setenv("AI_PROVIDER", "deepseek")

    assert get_default_ai_model_id_from_env() == "kimi-2.6"


def test_create_provider_builds_kimi_provider_from_model_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KIMI_API_KEY", "test-key")
    monkeypatch.delenv("KIMI_MODEL", raising=False)
    monkeypatch.delenv("KIMI_BASE_URL", raising=False)
    monkeypatch.delenv("KIMI_TEMPERATURE", raising=False)

    provider = create_ai_provider_from_env(model_id="kimi-2.6")

    assert isinstance(provider, OpenAICompatibleScriptAIProvider)
    assert provider.api_key == "test-key"
    assert provider.model == "kimi-k2.6"
    assert provider.base_url == "https://api.moonshot.cn/v1"
    assert provider.provider_name == "kimi"
    assert provider.api_key_env_name == "KIMI_API_KEY"
    assert provider.model_env_name == "KIMI_MODEL"


def test_create_provider_builds_glm_provider_from_model_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GLM_API_KEY", "test-key")
    monkeypatch.delenv("GLM_MODEL", raising=False)
    monkeypatch.delenv("GLM_BASE_URL", raising=False)
    monkeypatch.delenv("GLM_TEMPERATURE", raising=False)

    provider = create_ai_provider_from_env(model_id="glm-4.7-flashx")

    assert isinstance(provider, OpenAICompatibleScriptAIProvider)
    assert provider.api_key == "test-key"
    assert provider.model == "glm-4.7-flashx"
    assert provider.base_url == "https://open.bigmodel.cn/api/paas/v4"
    assert provider.provider_name == "glm"
    assert provider.api_key_env_name == "GLM_API_KEY"
    assert provider.model_env_name == "GLM_MODEL"


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

    result = provider.generate_script_yaml("Rain Letter", "skeleton")

    assert result.startswith("script:\n")
    assert yaml.safe_load(result) == yaml.safe_load(valid_yaml)


def test_openai_provider_canonicalizes_quoted_yaml_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICompatibleScriptAIProvider(api_key="test-key", model="test-model")
    quoted_key_yaml = _valid_yaml().replace("script:", '"script":', 1).replace(
        "  schema_version:",
        '  "schema_version":',
        1,
    )

    def fake_request_completion(self, payload):
        return f"Here is the screenplay YAML:\n```yaml\n{quoted_key_yaml}```\nDone."

    monkeypatch.setattr(OpenAICompatibleScriptAIProvider, "_request_completion", fake_request_completion)

    result = provider.generate_script_yaml("Rain Letter", "skeleton")

    assert result.startswith("script:\n")
    assert '"script":' not in result
    assert '"schema_version":' not in result
    assert validate_script_yaml(result).valid


def test_openai_provider_extracts_fenced_yaml_from_surrounding_text(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICompatibleScriptAIProvider(api_key="test-key", model="test-model")
    valid_yaml = _valid_yaml()
    calls = []

    def fake_request_completion(self, payload):
        calls.append(payload)
        return f"Here is the screenplay YAML:\n\n```yaml\n{valid_yaml}```\n\nDone."

    monkeypatch.setattr(OpenAICompatibleScriptAIProvider, "_request_completion", fake_request_completion)

    assert yaml.safe_load(provider.generate_script_yaml("Rain Letter", "skeleton")) == yaml.safe_load(valid_yaml)
    assert len(calls) == 1


def test_openai_provider_repairs_common_utf8_mojibake(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICompatibleScriptAIProvider(api_key="test-key", model="test-model")
    mojibake_yaml = _valid_yaml().replace(
        "Rain Letter",
        "Mira\u00e2\u0080\u0099s Clock \u00e2\u0080\u0094 The Second Minute \u00e2\u20ac\u2122 Again\x85",
    )

    def fake_request_completion(self, payload):
        return mojibake_yaml

    monkeypatch.setattr(OpenAICompatibleScriptAIProvider, "_request_completion", fake_request_completion)

    result = provider.generate_script_yaml("Rain Letter", "skeleton")

    assert "Mira\u2019s Clock \u2014 The Second Minute \u2019 Again" in result
    assert "\u00e2" not in result
    assert "\x85" not in result


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

    assert yaml.safe_load(provider.generate_script_yaml("Rain Letter", "skeleton")) == yaml.safe_load(valid_yaml)
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
    assert "Quote every YAML string scalar" in system_prompt
    assert "3 to 5 beats per scene" in system_prompt
    assert "Title: Rain Letter" in user_prompt
    assert "ordered beats" in user_prompt
    assert "one complete response" in user_prompt
    assert "Quote every string scalar" in user_prompt


def test_generate_script_with_ai_detects_chinese_output_language(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    class CapturingProvider:
        def generate_script_yaml(self, title: str, skeleton_yaml: str, output_language: str = "source language") -> str:
            captured["output_language"] = output_language
            return skeleton_yaml

    chinese_yaml = _valid_yaml().replace("Rain Letter", "雨夜来信").replace(
        "The door opens.",
        "林澈推门而入，雨水顺着衣角滴落。",
    )

    monkeypatch.setattr("app.ai_provider.create_ai_provider_from_env", lambda model_id=None: CapturingProvider())

    generate_script_with_ai("雨夜来信", chinese_yaml)

    assert captured["output_language"] == "Simplified Chinese"


def test_generate_script_with_ai_keeps_english_as_source_language(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    class CapturingProvider:
        def generate_script_yaml(self, title: str, skeleton_yaml: str, output_language: str = "source language") -> str:
            captured["output_language"] = output_language
            return skeleton_yaml

    monkeypatch.setattr("app.ai_provider.create_ai_provider_from_env", lambda model_id=None: CapturingProvider())

    generate_script_with_ai("Rain Letter", _valid_yaml())

    assert captured["output_language"] == "source language"


def test_openai_provider_prompt_includes_chinese_output_language(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICompatibleScriptAIProvider(api_key="test-key", model="test-model")
    captured_payload = {}

    def fake_request_completion(self, payload):
        captured_payload.update(payload)
        return _valid_yaml()

    monkeypatch.setattr(OpenAICompatibleScriptAIProvider, "_request_completion", fake_request_completion)

    provider.generate_script_yaml("雨夜来信", _valid_yaml(), output_language="Simplified Chinese")

    messages = captured_payload["messages"]
    system_prompt = messages[0]["content"]
    user_prompt = messages[1]["content"]

    assert "Keep every YAML key exactly as the English schema key" in system_prompt
    assert "Output language: Simplified Chinese" in user_prompt
    assert "human-facing YAML string value" in user_prompt
    assert "Do not translate YAML keys or beat type enum values" in user_prompt


def test_openai_provider_prompt_keeps_english_source_language(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICompatibleScriptAIProvider(api_key="test-key", model="test-model")
    captured_payload = {}

    def fake_request_completion(self, payload):
        captured_payload.update(payload)
        return _valid_yaml()

    monkeypatch.setattr(OpenAICompatibleScriptAIProvider, "_request_completion", fake_request_completion)

    provider.generate_script_yaml("Rain Letter", _valid_yaml())

    user_prompt = captured_payload["messages"][1]["content"]

    assert "Output language: source language" in user_prompt
    assert "Output language: Simplified Chinese" not in user_prompt


def test_openai_provider_repair_prompt_repeats_output_language(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICompatibleScriptAIProvider(api_key="test-key", model="test-model")
    valid_yaml = _valid_yaml()
    calls = []

    def fake_request_completion(self, payload):
        calls.append(payload)

        if len(calls) == 1:
            return "script:\n  title: 雨夜来信\n"

        return valid_yaml

    monkeypatch.setattr(OpenAICompatibleScriptAIProvider, "_request_completion", fake_request_completion)

    provider.generate_script_yaml("雨夜来信", valid_yaml, output_language="Simplified Chinese")

    repair_prompt = calls[1]["messages"][-1]["content"]

    assert "Output language: Simplified Chinese" in repair_prompt
    assert "human-facing YAML string value" in repair_prompt


def test_remote_model_paths_share_output_language_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setenv("KIMI_API_KEY", "kimi-key")
    monkeypatch.setenv("GLM_API_KEY", "glm-key")
    calls = []

    def fake_request_completion(self, payload):
        calls.append((self.provider_name, payload))
        return _valid_yaml()

    monkeypatch.setattr(OpenAICompatibleScriptAIProvider, "_request_completion", fake_request_completion)

    for model_id in ("deepseek-v4-pro", "kimi-2.6", "glm-4.7-flashx"):
        generate_script_with_ai("雨夜来信", _valid_yaml(), model_id=model_id, output_language="zh-CN")

    assert [provider_name for provider_name, _payload in calls] == ["deepseek", "kimi", "glm"]
    assert all(
        "Output language: Simplified Chinese" in payload["messages"][1]["content"]
        for _provider_name, payload in calls
    )


def test_openai_provider_rejects_invalid_yaml_response(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICompatibleScriptAIProvider(api_key="test-key", model="test-model")

    def fake_request_completion(self, payload):
        return "script:\n  title: Rain Letter\n"

    monkeypatch.setattr(OpenAICompatibleScriptAIProvider, "_request_completion", fake_request_completion)

    with pytest.raises(AIProviderError, match="AI response did not match YAML schema"):
        provider.generate_script_yaml("Rain Letter", "skeleton")
