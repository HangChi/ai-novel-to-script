import os
from typing import Any, NoReturn

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.ai_provider import AIProviderError, generate_script_with_ai, get_ai_provider_status_from_env
from app.chapter_parser import ChapterParseError, parse_novel_chapters
from app.config_file import load_config_files
from app.script_draft import SCHEMA_VERSION, build_script_yaml
from app.script_validator import validate_script_yaml

load_config_files()


def _build_frontend_dev_origins() -> list[str]:
    ports = {"5173", os.getenv("FRONTEND_PORT", "").strip()}

    return [
        origin
        for port in sorted(port for port in ports if port)
        for origin in (f"http://localhost:{port}", f"http://127.0.0.1:{port}")
    ]


FRONTEND_DEV_ORIGINS = _build_frontend_dev_origins()

app = FastAPI(
    title="AI Novel to Script API",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_DEV_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/api/health", tags=["system"])
def read_health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/ai/status", tags=["ai"])
def read_ai_status() -> dict[str, object]:
    return get_ai_provider_status_from_env().to_dict()


def _api_error(status_code: int, code: str, message: str) -> NoReturn:
    raise HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "message": message,
        },
    )


def _bad_request(code: str, message: str) -> NoReturn:
    _api_error(400, code, message)


def _read_text_field(payload: dict[str, Any], field_name: str, default: str = "") -> str:
    value = payload.get(field_name, default)

    if not isinstance(value, str):
        _bad_request("INVALID_INPUT", f"{field_name} must be a string.")

    return value


@app.post("/api/scripts/generate", tags=["scripts"])
def generate_script(payload: dict[str, Any] = Body(...)) -> dict[str, str]:
    title = _read_text_field(payload, "title")
    content = _read_text_field(payload, "content")
    output_format = _read_text_field(payload, "output_format", "yaml")

    if output_format != "yaml":
        _bad_request("INVALID_INPUT", "output_format currently only supports yaml.")

    try:
        chapters = parse_novel_chapters(content)
    except ChapterParseError as error:
        _bad_request(error.code, error.message)

    skeleton_yaml = build_script_yaml(title=title, chapters=chapters)

    try:
        yaml_text = generate_script_with_ai(title=title, skeleton_yaml=skeleton_yaml)
    except AIProviderError as error:
        _api_error(502, "AI_GENERATION_FAILED", str(error))

    return {
        "status": "completed",
        "schema_version": SCHEMA_VERSION,
        "yaml": yaml_text,
    }


@app.post("/api/scripts/validate", tags=["scripts"])
def validate_script(payload: dict[str, Any] = Body(...)) -> dict[str, object]:
    yaml_text = _read_text_field(payload, "yaml")

    return validate_script_yaml(yaml_text).to_dict()
