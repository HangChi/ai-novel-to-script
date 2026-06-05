from fastapi.testclient import TestClient

from app.chapter_parser import parse_novel_chapters
from app.main import app
from app.script_draft import build_script_yaml


client = TestClient(app)


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


def test_validate_script_accepts_generated_yaml() -> None:
    response = client.post(
        "/api/scripts/validate",
        json={
            "schema_version": "0.1.0",
            "yaml": _valid_yaml(),
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "valid": True,
        "errors": [],
    }


def test_validate_script_reports_yaml_syntax_error() -> None:
    response = client.post(
        "/api/scripts/validate",
        json={
            "schema_version": "0.1.0",
            "yaml": "script:\n  title: [broken",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["valid"] is False
    assert payload["errors"][0]["code"] == "YAML_VALIDATION_FAILED"
    assert payload["errors"][0]["path"] == ""


def test_validate_script_reports_missing_required_fields() -> None:
    response = client.post(
        "/api/scripts/validate",
        json={
            "schema_version": "0.1.0",
            "yaml": "script:\n  schema_version: \"0.1.0\"\n  title: Rain Letter\n",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    paths = {error["path"] for error in payload["errors"]}

    assert payload["valid"] is False
    assert "script.logline" in paths
    assert "script.source" in paths
    assert "script.characters" in paths
    assert "script.scenes" in paths


def test_validate_script_reports_invalid_beat_type() -> None:
    yaml_text = _valid_yaml().replace("type: narration", "type: inner_thought", 1)
    response = client.post(
        "/api/scripts/validate",
        json={
            "schema_version": "0.1.0",
            "yaml": yaml_text,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["valid"] is False
    assert {
        "code": "YAML_VALIDATION_FAILED",
        "path": "script.scenes[0].beats[0].type",
        "message": "must be action, dialogue, narration, or transition.",
    } in payload["errors"]


def test_validate_script_rejects_non_string_yaml_field() -> None:
    response = client.post(
        "/api/scripts/validate",
        json={
            "schema_version": "0.1.0",
            "yaml": 123,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "code": "INVALID_INPUT",
        "message": "yaml must be a string.",
    }
