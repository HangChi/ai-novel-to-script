from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.script_validator import validate_script_yaml

SYSTEM_PROMPT = """You are an AI script adaptation assistant.
Convert the provided YAML skeleton into a polished screenplay draft YAML.
Return YAML only.
Keep the top-level `script` object and schema_version `0.1.0`.
Use only beat types: action, dialogue, narration, transition.
Preserve source traceability through source_chapter.
Do not invent unrelated plot events.
"""


class AIProviderError(RuntimeError):
    pass


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

    def __post_init__(self) -> None:
        if not self.api_key:
            raise AIProviderError("OPENAI_API_KEY is required when AI_PROVIDER=openai.")

        if not self.model:
            raise AIProviderError("OPENAI_MODEL is required when AI_PROVIDER=openai.")

    def generate_script_yaml(self, title: str, skeleton_yaml: str) -> str:
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": (
                        f"Title: {title or 'Untitled Script'}\n\n"
                        "Rewrite this screenplay YAML skeleton into an editable first draft.\n\n"
                        "```yaml\n"
                        f"{skeleton_yaml}"
                        "```"
                    ),
                },
            ],
        }
        raw_yaml = _strip_markdown_fence(self._request_completion(payload))
        validation = validate_script_yaml(raw_yaml)

        if not validation.valid:
            error_paths = ", ".join(error.path or "<root>" for error in validation.errors[:5])
            raise AIProviderError(f"AI response did not match YAML schema: {error_paths}")

        return raw_yaml

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


def create_ai_provider_from_env() -> ScriptAIProvider:
    provider_name = os.getenv("AI_PROVIDER", "local").strip().lower()

    if provider_name in {"", "local"}:
        return LocalScriptAIProvider()

    if provider_name == "openai":
        return OpenAICompatibleScriptAIProvider(
            api_key=os.getenv("OPENAI_API_KEY", ""),
            model=os.getenv("OPENAI_MODEL", ""),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            temperature=_read_float_env("OPENAI_TEMPERATURE", 0.3),
            timeout_seconds=_read_float_env("AI_PROVIDER_TIMEOUT_SECONDS", 60.0),
        )

    raise AIProviderError(f"Unsupported AI_PROVIDER: {provider_name}.")


def generate_script_with_ai(title: str, skeleton_yaml: str) -> str:
    return create_ai_provider_from_env().generate_script_yaml(title=title, skeleton_yaml=skeleton_yaml)
