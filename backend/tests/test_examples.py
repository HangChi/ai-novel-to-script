from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from app.chapter_parser import parse_novel_chapters
from app.main import app
from app.script_draft import build_script_yaml
from app.script_validator import validate_script_yaml


ROOT_DIR = Path(__file__).resolve().parents[2]
EXAMPLE_NOVEL_PATH = ROOT_DIR / "docs" / "examples" / "rain-letter-novel.txt"
EXPECTED_SCRIPT_PATH = ROOT_DIR / "docs" / "examples" / "rain-letter-script.yaml"

client = TestClient(app)


def _example_novel_text() -> str:
    return EXAMPLE_NOVEL_PATH.read_text(encoding="utf-8")


def test_example_novel_generates_expected_yaml_skeleton() -> None:
    chapters = parse_novel_chapters(_example_novel_text())
    yaml_text = build_script_yaml(title="雨夜来信", chapters=chapters)

    assert yaml.safe_load(yaml_text) == yaml.safe_load(EXPECTED_SCRIPT_PATH.read_text(encoding="utf-8"))
    assert validate_script_yaml(yaml_text).valid


def test_generate_api_accepts_example_novel(monkeypatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "local")

    response = client.post(
        "/api/scripts/generate",
        json={
            "title": "雨夜来信",
            "content": _example_novel_text(),
            "output_format": "yaml",
        },
    )

    assert response.status_code == 200

    payload = response.json()
    validation = validate_script_yaml(payload["yaml"])

    assert payload["schema_version"] == "0.1.0"
    assert validation.valid
