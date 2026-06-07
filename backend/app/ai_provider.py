from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
import re
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml

from app.script_validator import ScriptYamlValidationResult, validate_script_yaml

SYSTEM_PROMPT = """You are an AI script adaptation assistant.
Convert the provided YAML skeleton into a polished screenplay draft YAML.
Return YAML only, without Markdown fences or commentary.

Schema rules:
- Keep the top-level `script` object and schema_version `0.1.0`.
- Preserve `source.type`, `source.chapters_count`, and `source.chapter_titles`.
- Preserve every scene's `source_chapter` traceability.
- Use only beat types: action, dialogue, narration, transition.
- Dialogue beats must include a character string.
- Quote every YAML string scalar with double quotes, especially values that contain colons, apostrophes, or punctuation.
- Do not use block scalars, anchors, aliases, comments, or multiple YAML documents.

Adaptation requirements:
- Fill `script.logline` with one concise sentence.
- Populate `script.characters` with the main characters found in the source text.
- Give each character a stable id such as `char-001`, name, role, and short description.
- Convert chapter narration into screenplay scenes with useful titles, location, and time values.
- Split scene content into ordered beats for visible action, dialogue, necessary narration, and transitions.
- Keep the draft compact: one scene per source chapter, 3 to 5 beats per scene, and each beat text under 180 characters.
- Keep the plot faithful to the provided source text and do not invent unrelated events.
- Prefer concrete, editable screenplay language over literary summary.
"""


class AIProviderError(RuntimeError):
    pass


class _AIYamlDumper(yaml.SafeDumper):
    def increase_indent(self, flow: bool = False, indentless: bool = False):
        return super().increase_indent(flow, False)


YAML_FENCE_PATTERN = re.compile(r"```(?:yaml|yml)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
ROOT_SCRIPT_PATTERN = re.compile(r"""(?m)^["']?script["']?:\s*$""")
MOJIBAKE_RUN_PATTERN = re.compile(r"[\u0080-\u00ff]+")
C1_CONTROL_PATTERN = re.compile(r"[\u0080-\u009f]")
COMMON_MOJIBAKE_REPLACEMENTS = {
    "\u00e2\u0080\u0098": "\u2018",
    "\u00e2\u0080\u0099": "\u2019",
    "\u00e2\u0080\u009c": "\u201c",
    "\u00e2\u0080\u009d": "\u201d",
    "\u00e2\u0080\u0093": "\u2013",
    "\u00e2\u0080\u0094": "\u2014",
    "\u00e2\u0080\u00a6": "\u2026",
    "\u00e2\u20ac\u02dc": "\u2018",
    "\u00e2\u20ac\u2122": "\u2019",
    "\u00e2\u20ac\u0153": "\u201c",
    "\u00e2\u20ac\u009d": "\u201d",
    "\u00e2\u20ac\u201c": "\u2013",
    "\u00e2\u20ac\u201d": "\u2014",
    "\u00e2\u20ac\u00a6": "\u2026",
    "\u00c2\u00a0": " ",
}


@dataclass(frozen=True)
class AIProviderStatus:
    provider: str
    mode: str
    configured: bool
    model: str
    base_url: str
    missing_config: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ScriptAIProvider(Protocol):
    def generate_script_yaml(self, title: str, skeleton_yaml: str) -> str:
        ...


@dataclass(frozen=True)
class LocalScriptAIProvider:
    def generate_script_yaml(self, title: str, skeleton_yaml: str) -> str:
        return skeleton_yaml


@dataclass(frozen=True)
class OpenAICompatibleScriptAIProvider:
    api_key: str
    model: str
    base_url: str = "https://api.openai.com/v1"
    temperature: float = 0.3
    timeout_seconds: float = 60.0
    provider_name: str = "openai"
    api_key_env_name: str = "OPENAI_API_KEY"
    model_env_name: str = "OPENAI_MODEL"

    def __post_init__(self) -> None:
        if not self.api_key:
            raise AIProviderError(
                f"{self.api_key_env_name} is required when AI_PROVIDER={self.provider_name}."
            )

        if not self.model:
            raise AIProviderError(
                f"{self.model_env_name} is required when AI_PROVIDER={self.provider_name}."
            )

    def generate_script_yaml(self, title: str, skeleton_yaml: str) -> str:
        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": _build_rewrite_prompt(title=title, skeleton_yaml=skeleton_yaml),
            },
        ]
        payload = self._build_completion_payload(messages)
        raw_yaml = _normalize_ai_yaml_response(self._request_completion(payload))
        validation = validate_script_yaml(raw_yaml)

        if validation.valid:
            return _canonicalize_script_yaml(raw_yaml)

        repair_messages = [
            *messages,
            {
                "role": "assistant",
                "content": raw_yaml,
            },
            {
                "role": "user",
                "content": _build_repair_prompt(raw_yaml=raw_yaml, validation=validation),
            },
        ]
        repaired_yaml = _normalize_ai_yaml_response(
            self._request_completion(self._build_completion_payload(repair_messages))
        )
        repaired_validation = validate_script_yaml(repaired_yaml)

        if not repaired_validation.valid:
            error_paths = _format_validation_error_paths(repaired_validation)
            raise AIProviderError(f"AI response did not match YAML schema: {error_paths}")

        return _canonicalize_script_yaml(repaired_yaml)

    def _build_completion_payload(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        return {
            "model": self.model,
            "temperature": self.temperature,
            "messages": messages,
        }

    def _request_completion(self, payload: dict[str, Any]) -> str:
        request = Request(
            url=f"{self.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            raise AIProviderError(f"AI provider returned HTTP {error.code}.") from error
        except (TimeoutError, URLError) as error:
            raise AIProviderError("AI provider request failed.") from error
        except json.JSONDecodeError as error:
            raise AIProviderError("AI provider returned invalid JSON.") from error

        try:
            content = response_payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise AIProviderError("AI provider response did not contain message content.") from error

        if not isinstance(content, str) or not content.strip():
            raise AIProviderError("AI provider returned empty content.")

        return content


def _build_rewrite_prompt(title: str, skeleton_yaml: str) -> str:
    script_title = title.strip() or "Untitled Script"

    return (
        f"Title: {script_title}\n\n"
        "Rewrite this screenplay YAML skeleton into an editable first draft.\n"
        "Use the skeleton as the source of truth for structure and traceability.\n\n"
        "Before returning, check that the YAML includes:\n"
        "- script.logline\n"
        "- script.characters with ids, names, roles, and descriptions\n"
        "- scenes with location, time, characters, and source_chapter\n"
        "- ordered beats using action, dialogue, narration, or transition only\n\n"
        "Keep the YAML concise enough to return as one complete response. "
        "Quote every string scalar with double quotes.\n\n"
        "```yaml\n"
        f"{skeleton_yaml}"
        "```"
    )


def _repair_common_utf8_mojibake(text: str) -> str:
    for mojibake, replacement in COMMON_MOJIBAKE_REPLACEMENTS.items():
        text = text.replace(mojibake, replacement)

    def repair_run(match: re.Match[str]) -> str:
        raw_text = match.group(0)

        try:
            return raw_text.encode("latin-1").decode("utf-8")
        except UnicodeError:
            return raw_text

    return C1_CONTROL_PATTERN.sub("", MOJIBAKE_RUN_PATTERN.sub(repair_run, text))


def _extract_yaml_text(content: str) -> str:
    text = content.strip()

    for match in YAML_FENCE_PATTERN.finditer(text):
        fenced_text = match.group(1).strip()

        if ROOT_SCRIPT_PATTERN.search(fenced_text):
            return fenced_text

    if text.startswith("```"):
        return _strip_markdown_fence(text)

    script_match = ROOT_SCRIPT_PATTERN.search(text)

    if script_match and script_match.start() > 0:
        return text[script_match.start() :].strip()

    return text


def _normalize_ai_yaml_response(content: str) -> str:
    return _repair_common_utf8_mojibake(_extract_yaml_text(content))


def _canonicalize_script_yaml(yaml_text: str) -> str:
    payload = yaml.safe_load(yaml_text)

    return yaml.dump(
        payload,
        Dumper=_AIYamlDumper,
        allow_unicode=True,
        sort_keys=False,
        width=4096,
    )


def _format_validation_error_paths(validation: ScriptYamlValidationResult) -> str:
    return ", ".join(error.path or "<root>" for error in validation.errors[:5])


def _build_repair_prompt(raw_yaml: str, validation: ScriptYamlValidationResult) -> str:
    errors = "\n".join(
        f"- {error.path or '<root>'}: {error.message}"
        for error in validation.errors[:10]
    )

    return (
        "The previous response did not match the required screenplay YAML schema.\n"
        "Repair the YAML and return YAML only, without Markdown fences or commentary.\n\n"
        "Keep the repaired YAML concise, quote every string scalar with double quotes, "
        "and avoid block scalars or unquoted values containing colons.\n\n"
        "Validation errors:\n"
        f"{errors}\n\n"
        "Previous YAML:\n"
        "```yaml\n"
        f"{raw_yaml}\n"
        "```"
    )


def _strip_markdown_fence(content: str) -> str:
    text = content.strip()

    if not text.startswith("```"):
        return text

    lines = text.splitlines()

    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]

    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]

    return "\n".join(lines).strip()


def _read_float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name)

    if raw_value is None:
        return default

    try:
        return float(raw_value)
    except ValueError as error:
        raise AIProviderError(f"{name} must be a number.") from error


def _read_string_env(name: str, default: str = "") -> str:
    raw_value = os.getenv(name)

    if raw_value is None:
        return default

    return raw_value.strip()


def get_ai_provider_status_from_env() -> AIProviderStatus:
    provider_name = _read_string_env("AI_PROVIDER", "local").lower()

    if provider_name in {"", "local"}:
        return AIProviderStatus(
            provider="local",
            mode="local",
            configured=True,
            model="",
            base_url="",
            missing_config=[],
        )

    if provider_name == "openai":
        api_key = _read_string_env("OPENAI_API_KEY")
        model = _read_string_env("OPENAI_MODEL")
        base_url = _read_string_env("OPENAI_BASE_URL", "https://api.openai.com/v1")
        missing_config = [
            name
            for name, value in (
                ("OPENAI_API_KEY", api_key),
                ("OPENAI_MODEL", model),
                ("OPENAI_BASE_URL", base_url),
            )
            if not value
        ]

        return AIProviderStatus(
            provider="openai",
            mode="remote",
            configured=not missing_config,
            model=model,
            base_url=base_url,
            missing_config=missing_config,
        )

    if provider_name == "deepseek":
        api_key = _read_string_env("DEEPSEEK_API_KEY")
        model = _read_string_env("DEEPSEEK_MODEL", "deepseek-v4-flash")
        base_url = _read_string_env("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        missing_config = [
            name
            for name, value in (
                ("DEEPSEEK_API_KEY", api_key),
                ("DEEPSEEK_MODEL", model),
                ("DEEPSEEK_BASE_URL", base_url),
            )
            if not value
        ]

        return AIProviderStatus(
            provider="deepseek",
            mode="remote",
            configured=not missing_config,
            model=model,
            base_url=base_url,
            missing_config=missing_config,
        )

    return AIProviderStatus(
        provider=provider_name,
        mode="unsupported",
        configured=False,
        model="",
        base_url="",
        missing_config=["AI_PROVIDER"],
    )


def create_ai_provider_from_env() -> ScriptAIProvider:
    provider_name = _read_string_env("AI_PROVIDER", "local").lower()

    if provider_name in {"", "local"}:
        return LocalScriptAIProvider()

    if provider_name == "openai":
        return OpenAICompatibleScriptAIProvider(
            api_key=_read_string_env("OPENAI_API_KEY"),
            model=_read_string_env("OPENAI_MODEL"),
            base_url=_read_string_env("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            temperature=_read_float_env("OPENAI_TEMPERATURE", 0.3),
            timeout_seconds=_read_float_env("AI_PROVIDER_TIMEOUT_SECONDS", 60.0),
        )

    if provider_name == "deepseek":
        return OpenAICompatibleScriptAIProvider(
            api_key=_read_string_env("DEEPSEEK_API_KEY"),
            model=_read_string_env("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            base_url=_read_string_env("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            temperature=_read_float_env("DEEPSEEK_TEMPERATURE", 0.3),
            timeout_seconds=_read_float_env("AI_PROVIDER_TIMEOUT_SECONDS", 60.0),
            provider_name="deepseek",
            api_key_env_name="DEEPSEEK_API_KEY",
            model_env_name="DEEPSEEK_MODEL",
        )

    raise AIProviderError(f"Unsupported AI_PROVIDER: {provider_name}.")


def generate_script_with_ai(title: str, skeleton_yaml: str) -> str:
    return create_ai_provider_from_env().generate_script_yaml(title=title, skeleton_yaml=skeleton_yaml)
