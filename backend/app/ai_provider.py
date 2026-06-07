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
- Keep every YAML key exactly as the English schema key.
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

Language requirements:
- The user prompt specifies the output language for human-facing YAML string values.
- Write script.title, script.logline, source.chapter_titles, character names/roles/descriptions, scene titles/locations/times/character lists, dialogue character names, and beat text in that output language.
- Keep YAML keys and enum values such as action, dialogue, narration, and transition in English.
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


@dataclass(frozen=True)
class AIModelOption:
    id: str
    label: str
    provider: str
    mode: str
    configured: bool
    model: str
    base_url: str
    missing_config: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class RemoteAIModelDefinition:
    id: str
    label: str
    provider: str
    api_key_env_name: str
    model_env_name: str
    default_model: str
    base_url_env_name: str
    default_base_url: str
    temperature_env_name: str
    default_temperature: float = 0.3


LOCAL_AI_MODEL_ID = "local"
REMOTE_AI_MODEL_DEFINITIONS = (
    RemoteAIModelDefinition(
        id="deepseek-v4-pro",
        label="DeepSeek-V4-Pro",
        provider="deepseek",
        api_key_env_name="DEEPSEEK_API_KEY",
        model_env_name="DEEPSEEK_MODEL",
        default_model="deepseek-v4-pro",
        base_url_env_name="DEEPSEEK_BASE_URL",
        default_base_url="https://api.deepseek.com",
        temperature_env_name="DEEPSEEK_TEMPERATURE",
    ),
    RemoteAIModelDefinition(
        id="kimi-2.6",
        label="Kimi-2.6",
        provider="kimi",
        api_key_env_name="KIMI_API_KEY",
        model_env_name="KIMI_MODEL",
        default_model="kimi-k2.6",
        base_url_env_name="KIMI_BASE_URL",
        default_base_url="https://api.moonshot.cn/v1",
        temperature_env_name="KIMI_TEMPERATURE",
        default_temperature=1.0,
    ),
    RemoteAIModelDefinition(
        id="glm-4.7-flashx",
        label="GLM-4.7-FlashX",
        provider="glm",
        api_key_env_name="GLM_API_KEY",
        model_env_name="GLM_MODEL",
        default_model="glm-4.7-flashx",
        base_url_env_name="GLM_BASE_URL",
        default_base_url="https://open.bigmodel.cn/api/paas/v4",
        temperature_env_name="GLM_TEMPERATURE",
    ),
)
REMOTE_AI_MODEL_DEFINITIONS_BY_ID = {
    definition.id: definition for definition in REMOTE_AI_MODEL_DEFINITIONS
}
PROVIDER_DEFAULT_MODEL_IDS = {
    "deepseek": "deepseek-v4-pro",
    "kimi": "kimi-2.6",
    "glm": "glm-4.7-flashx",
}
CHINESE_CHARACTER_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
LETTER_CHARACTER_PATTERN = re.compile(r"[A-Za-z\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


class ScriptAIProvider(Protocol):
    def generate_script_yaml(
        self,
        title: str,
        skeleton_yaml: str,
        output_language: str = "source language",
    ) -> str:
        ...


@dataclass(frozen=True)
class LocalScriptAIProvider:
    def generate_script_yaml(
        self,
        title: str,
        skeleton_yaml: str,
        output_language: str = "source language",
    ) -> str:
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

    def generate_script_yaml(
        self,
        title: str,
        skeleton_yaml: str,
        output_language: str = "source language",
    ) -> str:
        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": _build_rewrite_prompt(
                    title=title,
                    skeleton_yaml=skeleton_yaml,
                    output_language=output_language,
                ),
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
                "content": _build_repair_prompt(
                    raw_yaml=raw_yaml,
                    validation=validation,
                    output_language=output_language,
                ),
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
            detail = _extract_http_error_detail(error)
            suffix = f" {detail}" if detail else ""
            raise AIProviderError(
                f"AI provider returned HTTP {error.code}.{suffix}"
            ) from error
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


def _extract_http_error_detail(error: HTTPError) -> str:
    try:
        body = error.read().decode("utf-8", errors="replace").strip()
    except (OSError, ValueError):
        return ""

    if not body:
        return ""

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return _truncate_error_detail(body)

    message = _read_error_message(payload)

    return _truncate_error_detail(message) if message else ""


def _read_error_message(payload: Any) -> str:
    if isinstance(payload, str):
        return payload.strip()

    if not isinstance(payload, dict):
        return ""

    error = payload.get("error", payload)

    if isinstance(error, str):
        return error.strip()

    if isinstance(error, dict):
        for key in ("message", "msg", "detail", "reason"):
            value = error.get(key)

            if isinstance(value, str) and value.strip():
                return value.strip()

    for key in ("message", "msg", "detail", "reason"):
        value = payload.get(key)

        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""


def _truncate_error_detail(detail: str, limit: int = 300) -> str:
    collapsed = " ".join(detail.split())

    if len(collapsed) <= limit:
        return collapsed

    return f"{collapsed[:limit].rstrip()}…"


def _build_rewrite_prompt(title: str, skeleton_yaml: str, output_language: str) -> str:
    script_title = title.strip() or "Untitled Script"

    return (
        f"Title: {script_title}\n\n"
        f"Output language: {output_language}\n"
        "Write every human-facing YAML string value in the output language above. "
        "Keep YAML keys and enum values in English exactly as required by the schema.\n\n"
        "Rewrite this screenplay YAML skeleton into an editable first draft.\n"
        "Use the skeleton as the source of truth for structure and traceability.\n\n"
        "Before returning, check that the YAML includes:\n"
        "- script.logline\n"
        "- script.characters with ids, names, roles, and descriptions\n"
        "- scenes with location, time, characters, and source_chapter\n"
        "- ordered beats using action, dialogue, narration, or transition only\n\n"
        "Keep the YAML concise enough to return as one complete response. "
        "Quote every string scalar with double quotes. "
        "Do not translate YAML keys or beat type enum values.\n\n"
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


def _build_repair_prompt(
    raw_yaml: str,
    validation: ScriptYamlValidationResult,
    output_language: str,
) -> str:
    errors = "\n".join(
        f"- {error.path or '<root>'}: {error.message}"
        for error in validation.errors[:10]
    )

    return (
        "The previous response did not match the required screenplay YAML schema.\n"
        "Repair the YAML and return YAML only, without Markdown fences or commentary.\n\n"
        f"Output language: {output_language}\n"
        "Write every human-facing YAML string value in the output language above. "
        "Keep YAML keys and enum values in English exactly as required by the schema.\n\n"
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


def _detect_output_language(title: str, skeleton_yaml: str) -> str:
    title_chinese_characters = CHINESE_CHARACTER_PATTERN.findall(title)
    title_language_characters = LETTER_CHARACTER_PATTERN.findall(title)

    if title_language_characters and len(title_chinese_characters) >= 2:
        title_chinese_ratio = len(title_chinese_characters) / len(title_language_characters)

        if title_chinese_ratio >= 0.5:
            return "Simplified Chinese"

    language_sample = f"{title}\n{skeleton_yaml}"
    chinese_characters = CHINESE_CHARACTER_PATTERN.findall(language_sample)
    language_characters = LETTER_CHARACTER_PATTERN.findall(language_sample)

    if not language_characters:
        return "source language"

    chinese_ratio = len(chinese_characters) / len(language_characters)

    if len(chinese_characters) >= 4 and chinese_ratio >= 0.1:
        return "Simplified Chinese"

    return "source language"


def _resolve_output_language(title: str, skeleton_yaml: str, output_language: str | None = None) -> str:
    configured_language = (output_language or _read_string_env("AI_OUTPUT_LANGUAGE", "auto")).strip()
    normalized_language = configured_language.lower()

    if normalized_language in {"", "auto"}:
        return _detect_output_language(title=title, skeleton_yaml=skeleton_yaml)

    if normalized_language in {"zh", "zh-cn", "cn", "chinese", "simplified chinese"}:
        return "Simplified Chinese"

    if normalized_language in {"en", "en-us", "english"}:
        return "English"

    if normalized_language in {"source", "source language"}:
        return "source language"

    return configured_language


def _normalize_model_id(model_id: str | None) -> str:
    return (model_id or "").strip().lower()


def _get_remote_definition_for_provider(provider_name: str) -> RemoteAIModelDefinition | None:
    model_id = PROVIDER_DEFAULT_MODEL_IDS.get(provider_name)

    if not model_id:
        return None

    return REMOTE_AI_MODEL_DEFINITIONS_BY_ID[model_id]


def _get_local_ai_model_option() -> AIModelOption:
    return AIModelOption(
        id=LOCAL_AI_MODEL_ID,
        label="本地骨架",
        provider="local",
        mode="local",
        configured=True,
        model="",
        base_url="",
        missing_config=[],
    )


def _get_remote_ai_model_option(definition: RemoteAIModelDefinition) -> AIModelOption:
    api_key = _read_string_env(definition.api_key_env_name)
    model = _read_string_env(definition.model_env_name, definition.default_model)
    base_url = _read_string_env(definition.base_url_env_name, definition.default_base_url)
    missing_config = [
        name
        for name, value in (
            (definition.api_key_env_name, api_key),
            (definition.model_env_name, model),
            (definition.base_url_env_name, base_url),
        )
        if not value
    ]

    return AIModelOption(
        id=definition.id,
        label=definition.label,
        provider=definition.provider,
        mode="remote",
        configured=not missing_config,
        model=model,
        base_url=base_url,
        missing_config=missing_config,
    )


def get_ai_model_options_from_env() -> list[AIModelOption]:
    return [
        _get_local_ai_model_option(),
        *(
            _get_remote_ai_model_option(definition)
            for definition in REMOTE_AI_MODEL_DEFINITIONS
        ),
    ]


def get_default_ai_model_id_from_env() -> str:
    configured_model_id = _normalize_model_id(_read_string_env("AI_MODEL_ID"))

    if configured_model_id:
        return configured_model_id

    provider_name = _read_string_env("AI_PROVIDER", "local").lower()

    return PROVIDER_DEFAULT_MODEL_IDS.get(provider_name, LOCAL_AI_MODEL_ID)


def is_ai_model_id_supported(model_id: str) -> bool:
    normalized_model_id = _normalize_model_id(model_id)

    return normalized_model_id == LOCAL_AI_MODEL_ID or normalized_model_id in REMOTE_AI_MODEL_DEFINITIONS_BY_ID


def _get_ai_provider_status_from_model_id(model_id: str) -> AIProviderStatus:
    normalized_model_id = _normalize_model_id(model_id)

    if normalized_model_id == LOCAL_AI_MODEL_ID:
        return AIProviderStatus(
            provider="local",
            mode="local",
            configured=True,
            model="",
            base_url="",
            missing_config=[],
        )

    definition = REMOTE_AI_MODEL_DEFINITIONS_BY_ID.get(normalized_model_id)

    if definition:
        option = _get_remote_ai_model_option(definition)

        return AIProviderStatus(
            provider=option.provider,
            mode=option.mode,
            configured=option.configured,
            model=option.model,
            base_url=option.base_url,
            missing_config=option.missing_config,
        )

    return AIProviderStatus(
        provider=normalized_model_id,
        mode="unsupported",
        configured=False,
        model="",
        base_url="",
        missing_config=["AI_MODEL_ID"],
    )


def _create_ai_provider_for_model_id(model_id: str) -> ScriptAIProvider:
    normalized_model_id = _normalize_model_id(model_id)

    if normalized_model_id == LOCAL_AI_MODEL_ID:
        return LocalScriptAIProvider()

    definition = REMOTE_AI_MODEL_DEFINITIONS_BY_ID.get(normalized_model_id)

    if not definition:
        raise AIProviderError(f"Unsupported AI_MODEL_ID: {model_id}.")

    return OpenAICompatibleScriptAIProvider(
        api_key=_read_string_env(definition.api_key_env_name),
        model=_read_string_env(definition.model_env_name, definition.default_model),
        base_url=_read_string_env(definition.base_url_env_name, definition.default_base_url),
        temperature=_read_float_env(definition.temperature_env_name, definition.default_temperature),
        timeout_seconds=_read_float_env("AI_PROVIDER_TIMEOUT_SECONDS", 60.0),
        provider_name=definition.provider,
        api_key_env_name=definition.api_key_env_name,
        model_env_name=definition.model_env_name,
    )


def get_ai_provider_status_from_env() -> AIProviderStatus:
    configured_model_id = _normalize_model_id(_read_string_env("AI_MODEL_ID"))

    if configured_model_id:
        return _get_ai_provider_status_from_model_id(configured_model_id)

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

    remote_definition = _get_remote_definition_for_provider(provider_name)

    if remote_definition:
        return _get_ai_provider_status_from_model_id(remote_definition.id)

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

    return AIProviderStatus(
        provider=provider_name,
        mode="unsupported",
        configured=False,
        model="",
        base_url="",
        missing_config=["AI_PROVIDER"],
    )


def create_ai_provider_from_env(model_id: str | None = None) -> ScriptAIProvider:
    requested_model_id = _normalize_model_id(model_id) or _normalize_model_id(_read_string_env("AI_MODEL_ID"))

    if requested_model_id:
        return _create_ai_provider_for_model_id(requested_model_id)

    provider_name = _read_string_env("AI_PROVIDER", "local").lower()

    if provider_name in {"", "local"}:
        return LocalScriptAIProvider()

    remote_definition = _get_remote_definition_for_provider(provider_name)

    if remote_definition:
        return _create_ai_provider_for_model_id(remote_definition.id)

    if provider_name == "openai":
        return OpenAICompatibleScriptAIProvider(
            api_key=_read_string_env("OPENAI_API_KEY"),
            model=_read_string_env("OPENAI_MODEL"),
            base_url=_read_string_env("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            temperature=_read_float_env("OPENAI_TEMPERATURE", 0.3),
            timeout_seconds=_read_float_env("AI_PROVIDER_TIMEOUT_SECONDS", 60.0),
        )

    raise AIProviderError(f"Unsupported AI_PROVIDER: {provider_name}.")


def generate_script_with_ai(
    title: str,
    skeleton_yaml: str,
    model_id: str | None = None,
    output_language: str | None = None,
) -> str:
    resolved_output_language = _resolve_output_language(
        title=title,
        skeleton_yaml=skeleton_yaml,
        output_language=output_language,
    )

    return create_ai_provider_from_env(model_id=model_id).generate_script_yaml(
        title=title,
        skeleton_yaml=skeleton_yaml,
        output_language=resolved_output_language,
    )
