import os
from time import monotonic
from typing import Any, NoReturn

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.ai_provider import (
    AIProviderError,
    generate_script_with_ai,
    get_ai_model_options_from_env,
    get_ai_provider_status_from_env,
    get_default_ai_model_id_from_env,
    is_ai_model_id_supported,
    normalize_streaming_yaml_preview,
)
from app.chapter_parser import ChapterParseError, parse_novel_chapters
from app.config_file import load_config_files
from app.generation_jobs import GenerationJobStore, ProgressCallback
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
generation_jobs = GenerationJobStore(max_workers=1)

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


@app.get("/api/ai/models", tags=["ai"])
def read_ai_models() -> dict[str, object]:
    return {
        "default_model_id": get_default_ai_model_id_from_env(),
        "models": [option.to_dict() for option in get_ai_model_options_from_env()],
    }


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


class ScriptGenerationError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _read_generate_script_request(payload: dict[str, Any]) -> dict[str, str]:
    return {
        "title": _read_text_field(payload, "title"),
        "content": _read_text_field(payload, "content"),
        "output_format": _read_text_field(payload, "output_format", "yaml"),
        "model_id": _read_text_field(payload, "model_id", "").strip(),
        "output_language": _read_text_field(payload, "output_language", "").strip(),
    }


def _generate_script_result(
    request_payload: dict[str, str],
    progress: ProgressCallback | None = None,
) -> dict[str, str]:
    title = request_payload["title"]
    content = request_payload["content"]
    output_format = request_payload["output_format"]
    model_id = request_payload["model_id"]
    output_language = request_payload["output_language"]

    if output_format != "yaml":
        raise ScriptGenerationError("INVALID_INPUT", "output_format currently only supports yaml.")

    if model_id and not is_ai_model_id_supported(model_id):
        raise ScriptGenerationError("INVALID_INPUT", "model_id is not supported.")

    if progress:
        progress("parsing", 10, "正在解析章节。")

    try:
        chapters = parse_novel_chapters(content)
    except ChapterParseError as error:
        raise ScriptGenerationError(error.code, error.message) from error

    if progress:
        progress("building_skeleton", 25, "正在构建 YAML 骨架。")

    skeleton_yaml = build_script_yaml(title=title, chapters=chapters)

    if progress:
        progress("ai_generating", 55, "正在调用 AI 模型生成剧本。", skeleton_yaml)

    last_stream_update = {
        "content_length": 0,
        "sent_at": 0.0,
    }

    def handle_stream_content(raw_content: str) -> None:
        if not progress:
            return

        stream_yaml = normalize_streaming_yaml_preview(raw_content)

        if not stream_yaml:
            return

        now = monotonic()
        length_delta = len(stream_yaml) - last_stream_update["content_length"]

        if length_delta < 160 and now - last_stream_update["sent_at"] < 0.2:
            return

        last_stream_update["content_length"] = len(stream_yaml)
        last_stream_update["sent_at"] = now
        estimated_progress = min(84, 55 + len(stream_yaml) // 260)
        progress(
            "ai_generating",
            estimated_progress,
            "正在接收模型流式输出。",
            skeleton_yaml,
            stream_yaml,
        )

    try:
        yaml_text = generate_script_with_ai(
            title=title,
            skeleton_yaml=skeleton_yaml,
            model_id=model_id or None,
            output_language=output_language or None,
            stream_callback=handle_stream_content if progress else None,
        )
    except AIProviderError as error:
        raise ScriptGenerationError("AI_GENERATION_FAILED", str(error), status_code=502) from error

    if progress:
        progress("validating", 85, "正在校验 YAML 结构。")

    validation = validate_script_yaml(yaml_text)

    if not validation.valid:
        error_paths = ", ".join(error.path or "<root>" for error in validation.errors[:5])
        raise ScriptGenerationError(
            "AI_GENERATION_FAILED",
            f"AI response did not match YAML schema: {error_paths}",
            status_code=502,
        )

    return {
        "status": "completed",
        "schema_version": SCHEMA_VERSION,
        "yaml": yaml_text,
    }


@app.post("/api/scripts/generate", tags=["scripts"])
def generate_script(payload: dict[str, Any] = Body(...)) -> dict[str, str]:
    try:
        return _generate_script_result(_read_generate_script_request(payload))
    except ScriptGenerationError as error:
        _api_error(error.status_code, error.code, error.message)


@app.post("/api/scripts/generate/jobs", tags=["scripts"])
def create_generate_script_job(payload: dict[str, Any] = Body(...)) -> dict[str, str]:
    request_payload = _read_generate_script_request(payload)
    job = generation_jobs.create(lambda progress: _generate_script_result(request_payload, progress=progress))

    return {
        "job_id": job.job_id,
        "status": "queued",
        "status_url": f"/api/scripts/generate/jobs/{job.job_id}",
        "events_url": f"/api/scripts/generate/jobs/{job.job_id}/events",
    }


@app.get("/api/scripts/generate/jobs/{job_id}", tags=["scripts"])
def read_generate_script_job(job_id: str) -> dict[str, object]:
    job = generation_jobs.get(job_id)

    if job is None:
        _api_error(404, "JOB_NOT_FOUND", "Generation job was not found.")

    return job.to_dict()


@app.get("/api/scripts/generate/jobs/{job_id}/events", tags=["scripts"])
def stream_generate_script_job_events(job_id: str) -> StreamingResponse:
    return StreamingResponse(
        generation_jobs.stream(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.post("/api/scripts/validate", tags=["scripts"])
def validate_script(payload: dict[str, Any] = Body(...)) -> dict[str, object]:
    yaml_text = _read_text_field(payload, "yaml")

    return validate_script_yaml(yaml_text).to_dict()
