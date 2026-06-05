import yaml

from app.chapter_parser import parse_novel_chapters
from app.script_draft import build_script_draft, build_script_yaml, dump_script_draft_yaml


def _chapters():
    return parse_novel_chapters(
        """
第一章 初遇
林澈推门而入。

第二章 暗线
苏晚发现信件。

第三章 选择
两人在雨夜分别。
"""
    )


def test_build_script_draft_from_chapters() -> None:
    draft = build_script_draft(title="雨夜来信", chapters=_chapters())

    assert draft.schema_version == "0.1.0"
    assert draft.title == "雨夜来信"
    assert draft.source.type == "novel"
    assert draft.source.chapters_count == 3
    assert draft.source.chapter_titles == ["第一章 初遇", "第二章 暗线", "第三章 选择"]
    assert draft.characters == []
    assert [scene.id for scene in draft.scenes] == ["scene-001", "scene-002", "scene-003"]
    assert draft.scenes[0].title == "第一章 初遇"
    assert draft.scenes[0].source_chapter == "第一章 初遇"
    assert draft.scenes[0].beats[0].type == "narration"
    assert draft.scenes[0].beats[0].text == "林澈推门而入。"


def test_build_script_draft_uses_default_title() -> None:
    draft = build_script_draft(title="  ", chapters=_chapters())

    assert draft.title == "未命名剧本"


def test_dump_script_draft_yaml_matches_schema_shape() -> None:
    draft = build_script_draft(title="雨夜来信", chapters=_chapters())
    yaml_text = dump_script_draft_yaml(draft)
    payload = yaml.safe_load(yaml_text)

    assert list(payload.keys()) == ["script"]
    assert list(payload["script"].keys()) == [
        "schema_version",
        "title",
        "logline",
        "source",
        "characters",
        "scenes",
    ]
    assert payload["script"]["source"] == {
        "type": "novel",
        "chapters_count": 3,
        "chapter_titles": ["第一章 初遇", "第二章 暗线", "第三章 选择"],
    }
    assert payload["script"]["scenes"][0] == {
        "id": "scene-001",
        "title": "第一章 初遇",
        "source_chapter": "第一章 初遇",
        "location": "",
        "time": "",
        "characters": [],
        "beats": [
            {
                "type": "narration",
                "text": "林澈推门而入。",
            }
        ],
    }


def test_build_script_yaml_keeps_unicode_text() -> None:
    yaml_text = build_script_yaml(title="雨夜来信", chapters=_chapters())

    assert "雨夜来信" in yaml_text
    assert "林澈推门而入。" in yaml_text
    assert yaml.safe_load(yaml_text)["script"]["title"] == "雨夜来信"
