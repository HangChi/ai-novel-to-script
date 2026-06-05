from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

import yaml

from app.chapter_parser import Chapter

SCHEMA_VERSION = "0.1.0"
DEFAULT_LOGLINE_PLACEHOLDER = "TBD: add a one-sentence story logline"
DEFAULT_SCENE_FIELD_PLACEHOLDER = "TBD"

BeatType = Literal["action", "dialogue", "narration", "transition"]


class _ScriptYamlDumper(yaml.SafeDumper):
    def increase_indent(self, flow: bool = False, indentless: bool = False):
        return super().increase_indent(flow, False)


@dataclass(frozen=True)
class ScriptSource:
    type: Literal["novel"]
    chapters_count: int
    chapter_titles: list[str]


@dataclass(frozen=True)
class Character:
    id: str
    name: str
    role: str = ""
    description: str = ""


@dataclass(frozen=True)
class Beat:
    type: BeatType
    text: str
    character: str | None = None

    def to_dict(self) -> dict[str, str]:
        payload: dict[str, str] = {
            "type": self.type,
            "text": self.text,
        }

        if self.character:
            payload["character"] = self.character

        return payload


@dataclass(frozen=True)
class Scene:
    id: str
    title: str
    source_chapter: str
    location: str = ""
    time: str = ""
    characters: list[str] = field(default_factory=list)
    beats: list[Beat] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "source_chapter": self.source_chapter,
            "location": self.location,
            "time": self.time,
            "characters": self.characters,
            "beats": [beat.to_dict() for beat in self.beats],
        }


@dataclass(frozen=True)
class ScriptDraft:
    schema_version: str
    title: str
    logline: str
    source: ScriptSource
    characters: list[Character]
    scenes: list[Scene]

    def to_dict(self) -> dict[str, object]:
        return {
            "script": {
                "schema_version": self.schema_version,
                "title": self.title,
                "logline": self.logline,
                "source": asdict(self.source),
                "characters": [asdict(character) for character in self.characters],
                "scenes": [scene.to_dict() for scene in self.scenes],
            }
        }


def build_script_draft(title: str, chapters: list[Chapter]) -> ScriptDraft:
    script_title = title.strip() or "未命名剧本"

    return ScriptDraft(
        schema_version=SCHEMA_VERSION,
        title=script_title,
        logline=DEFAULT_LOGLINE_PLACEHOLDER,
        source=ScriptSource(
            type="novel",
            chapters_count=len(chapters),
            chapter_titles=[chapter.title for chapter in chapters],
        ),
        characters=[],
        scenes=[
            Scene(
                id=f"scene-{chapter.index:03d}",
                title=chapter.title,
                source_chapter=chapter.title,
                location=DEFAULT_SCENE_FIELD_PLACEHOLDER,
                time=DEFAULT_SCENE_FIELD_PLACEHOLDER,
                beats=[
                    Beat(
                        type="narration",
                        text=chapter.content,
                    )
                ],
            )
            for chapter in chapters
        ],
    )


def dump_script_draft_yaml(script_draft: ScriptDraft) -> str:
    return yaml.dump(
        script_draft.to_dict(),
        Dumper=_ScriptYamlDumper,
        allow_unicode=True,
        sort_keys=False,
    )


def build_script_yaml(title: str, chapters: list[Chapter]) -> str:
    return dump_script_draft_yaml(build_script_draft(title=title, chapters=chapters))
