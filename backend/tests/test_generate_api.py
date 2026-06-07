import yaml
from fastapi.testclient import TestClient

from app.ai_provider import AIProviderError
from app.main import app


client = TestClient(app)


def _novel_text() -> str:
    return """
Chapter 1: Arrival
Lin opens the locked door.

Chapter 2: The Letter
Su finds a note under the lamp.

Chapter 3: Decision
They choose to leave before dawn.
"""


def test_generate_script_returns_yaml_draft() -> None:
    response = client.post(
        "/api/scripts/generate",
        json={
            "title": "Rain Letter",
            "content": _novel_text(),
            "output_format": "yaml",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    script = yaml.safe_load(payload["yaml"])["script"]

    assert payload["status"] == "completed"
    assert payload["schema_version"] == "0.1.0"
    assert script["title"] == "Rain Letter"
    assert script["source"]["chapters_count"] == 3
    assert [scene["id"] for scene in script["scenes"]] == ["scene-001", "scene-002", "scene-003"]
    assert script["scenes"][0]["beats"][0] == {
        "type": "narration",
        "text": "Lin opens the locked door.",
    }


def test_generate_script_rejects_less_than_three_chapters() -> None:
    response = client.post(
        "/api/scripts/generate",
        json={
            "title": "Short Story",
            "content": """
Chapter 1
First scene.

Chapter 2
Second scene.
""",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_CHAPTER_COUNT"


def test_generate_script_rejects_invalid_content() -> None:
    response = client.post(
        "/api/scripts/generate",
        json={
            "title": "No Chapter",
            "content": "This paragraph has no chapter headings.",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_INPUT"


def test_generate_script_rejects_unsupported_output_format() -> None:
    response = client.post(
        "/api/scripts/generate",
        json={
            "title": "Rain Letter",
            "content": _novel_text(),
            "output_format": "json",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "code": "INVALID_INPUT",
        "message": "output_format currently only supports yaml.",
    }


def test_generate_script_passes_model_id_and_output_language_to_ai_provider(monkeypatch) -> None:
    captured = {}

    def generate_with_model_id(
        title: str,
        skeleton_yaml: str,
        model_id: str | None = None,
        output_language: str | None = None,
    ) -> str:
        captured["title"] = title
        captured["model_id"] = model_id
        captured["output_language"] = output_language
        return skeleton_yaml

    monkeypatch.setattr("app.main.generate_script_with_ai", generate_with_model_id)

    response = client.post(
        "/api/scripts/generate",
        json={
            "title": "Rain Letter",
            "content": _novel_text(),
            "output_format": "yaml",
            "model_id": "kimi-2.6",
            "output_language": "zh-CN",
        },
    )

    assert response.status_code == 200
    assert captured == {
        "title": "Rain Letter",
        "model_id": "kimi-2.6",
        "output_language": "zh-CN",
    }


def test_generate_script_rejects_unsupported_model_id() -> None:
    response = client.post(
        "/api/scripts/generate",
        json={
            "title": "Rain Letter",
            "content": _novel_text(),
            "output_format": "yaml",
            "model_id": "unknown-model",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "code": "INVALID_INPUT",
        "message": "model_id is not supported.",
    }


def test_generate_script_reports_ai_provider_failure(monkeypatch) -> None:
    def fail_generation(
        title: str,
        skeleton_yaml: str,
        model_id: str | None = None,
        output_language: str | None = None,
    ) -> str:
        raise AIProviderError("provider unavailable")

    monkeypatch.setattr("app.main.generate_script_with_ai", fail_generation)

    response = client.post(
        "/api/scripts/generate",
        json={
            "title": "Rain Letter",
            "content": _novel_text(),
            "output_format": "yaml",
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"] == {
        "code": "AI_GENERATION_FAILED",
        "message": "provider unavailable",
    }
