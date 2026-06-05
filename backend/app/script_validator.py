from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import yaml

from app.script_draft import SCHEMA_VERSION

ERROR_CODE = "YAML_VALIDATION_FAILED"
VALID_BEAT_TYPES = {"action", "dialogue", "narration", "transition"}


@dataclass(frozen=True)
class ScriptYamlValidationError:
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class ScriptYamlValidationResult:
    valid: bool
    errors: list[ScriptYamlValidationError] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "errors": [asdict(error) for error in self.errors],
        }


def _add_error(errors: list[ScriptYamlValidationError], path: str, message: str) -> None:
    errors.append(ScriptYamlValidationError(code=ERROR_CODE, path=path, message=message))


def _is_string(value: Any) -> bool:
    return isinstance(value, str)


def _is_int(value: Any) -> bool:
    return type(value) is int


def _validate_string_field(payload: dict[str, Any], field_name: str, path: str, errors: list[ScriptYamlValidationError]) -> None:
    if not _is_string(payload.get(field_name)):
        _add_error(errors, f"{path}.{field_name}", "must be a string.")


def _validate_string_list(value: Any, path: str, errors: list[ScriptYamlValidationError]) -> None:
    if not isinstance(value, list):
        _add_error(errors, path, "must be a list of strings.")
        return

    for index, item in enumerate(value):
        if not _is_string(item):
            _add_error(errors, f"{path}[{index}]", "must be a string.")


def _validate_source(source: Any, errors: list[ScriptYamlValidationError]) -> None:
    if not isinstance(source, dict):
        _add_error(errors, "script.source", "must be a mapping.")
        return

    if source.get("type") != "novel":
        _add_error(errors, "script.source.type", "must be novel.")

    chapters_count = source.get("chapters_count")

    if not _is_int(chapters_count):
        _add_error(errors, "script.source.chapters_count", "must be an integer.")
    elif chapters_count < 3:
        _add_error(errors, "script.source.chapters_count", "must be at least 3.")

    chapter_titles = source.get("chapter_titles")
    _validate_string_list(chapter_titles, "script.source.chapter_titles", errors)

    if _is_int(chapters_count) and isinstance(chapter_titles, list) and chapters_count != len(chapter_titles):
        _add_error(errors, "script.source.chapter_titles", "must match chapters_count.")


def _validate_characters(characters: Any, errors: list[ScriptYamlValidationError]) -> None:
    if not isinstance(characters, list):
        _add_error(errors, "script.characters", "must be a list.")
        return

    for index, character in enumerate(characters):
        path = f"script.characters[{index}]"

        if not isinstance(character, dict):
            _add_error(errors, path, "must be a mapping.")
            continue

        _validate_string_field(character, "id", path, errors)
        _validate_string_field(character, "name", path, errors)

        for optional_field in ("role", "description"):
            if optional_field in character and not _is_string(character[optional_field]):
                _add_error(errors, f"{path}.{optional_field}", "must be a string.")


def _validate_beats(beats: Any, scene_path: str, errors: list[ScriptYamlValidationError]) -> None:
    path = f"{scene_path}.beats"

    if not isinstance(beats, list):
        _add_error(errors, path, "must be a list.")
        return

    if not beats:
        _add_error(errors, path, "must contain at least one beat.")
        return

    for index, beat in enumerate(beats):
        beat_path = f"{path}[{index}]"

        if not isinstance(beat, dict):
            _add_error(errors, beat_path, "must be a mapping.")
            continue

        beat_type = beat.get("type")

        if beat_type not in VALID_BEAT_TYPES:
            _add_error(errors, f"{beat_path}.type", "must be action, dialogue, narration, or transition.")

        _validate_string_field(beat, "text", beat_path, errors)

        if beat_type == "dialogue" and not _is_string(beat.get("character")):
            _add_error(errors, f"{beat_path}.character", "must be a string for dialogue beats.")
        elif "character" in beat and not _is_string(beat["character"]):
            _add_error(errors, f"{beat_path}.character", "must be a string.")


def _validate_scenes(scenes: Any, errors: list[ScriptYamlValidationError]) -> None:
    if not isinstance(scenes, list):
        _add_error(errors, "script.scenes", "must be a list.")
        return

    if not scenes:
        _add_error(errors, "script.scenes", "must contain at least one scene.")
        return

    for index, scene in enumerate(scenes):
        path = f"script.scenes[{index}]"

        if not isinstance(scene, dict):
            _add_error(errors, path, "must be a mapping.")
            continue

        for field_name in ("id", "title", "source_chapter", "location", "time"):
            _validate_string_field(scene, field_name, path, errors)

        _validate_string_list(scene.get("characters"), f"{path}.characters", errors)
        _validate_beats(scene.get("beats"), path, errors)


def _validate_script(script: Any, errors: list[ScriptYamlValidationError]) -> None:
    if not isinstance(script, dict):
        _add_error(errors, "script", "must be a mapping.")
        return

    for field_name in ("schema_version", "title", "logline"):
        _validate_string_field(script, field_name, "script", errors)

    if _is_string(script.get("schema_version")) and script["schema_version"] != SCHEMA_VERSION:
        _add_error(errors, "script.schema_version", f"must be {SCHEMA_VERSION}.")

    _validate_source(script.get("source"), errors)
    _validate_characters(script.get("characters"), errors)
    _validate_scenes(script.get("scenes"), errors)


def validate_script_yaml(yaml_text: str) -> ScriptYamlValidationResult:
    errors: list[ScriptYamlValidationError] = []

    if not yaml_text.strip():
        _add_error(errors, "", "YAML content cannot be empty.")
        return ScriptYamlValidationResult(valid=False, errors=errors)

    try:
        payload = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        _add_error(errors, "", "YAML syntax error.")
        return ScriptYamlValidationResult(valid=False, errors=errors)

    if not isinstance(payload, dict):
        _add_error(errors, "", "YAML root must be a mapping.")
        return ScriptYamlValidationResult(valid=False, errors=errors)

    _validate_script(payload.get("script"), errors)

    return ScriptYamlValidationResult(valid=not errors, errors=errors)
