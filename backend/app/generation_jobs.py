from __future__ import annotations

from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
from threading import Condition, Lock
from uuid import uuid4


JobStatus = str
ProgressCallback = Callable[[str, int, str], None]
JobRunner = Callable[[ProgressCallback], dict[str, str]]

TERMINAL_STATUSES = {"completed", "failed"}


@dataclass(frozen=True)
class GenerationJobError:
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
        }


@dataclass(frozen=True)
class GenerationJobEvent:
    name: str
    payload: dict[str, object]


@dataclass
class GenerationJob:
    job_id: str
    status: JobStatus = "queued"
    phase: str = "queued"
    progress: int = 0
    message: str = "任务已提交，等待开始。"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    schema_version: str | None = None
    yaml: str | None = None
    error: GenerationJobError | None = None
    events: list[GenerationJobEvent] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "job_id": self.job_id,
            "status": self.status,
            "phase": self.phase,
            "progress": self.progress,
            "message": self.message,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

        if self.schema_version is not None:
            payload["schema_version"] = self.schema_version

        if self.yaml is not None:
            payload["yaml"] = self.yaml

        if self.error is not None:
            payload["error"] = self.error.to_dict()

        return payload


class GenerationJobStore:
    def __init__(self, max_workers: int = 1) -> None:
        self._jobs: dict[str, GenerationJob] = {}
        self._lock = Lock()
        self._condition = Condition(self._lock)
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="script-generation")

    def create(self, runner: JobRunner) -> GenerationJob:
        job = GenerationJob(job_id=f"job-{uuid4().hex}")

        with self._condition:
            job.events.append(GenerationJobEvent(name="job.status", payload=job.to_dict()))
            self._jobs[job.job_id] = job
            self._condition.notify_all()

        self._executor.submit(self._run, job.job_id, runner)

        return job

    def get(self, job_id: str) -> GenerationJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def stream(self, job_id: str, heartbeat_seconds: float = 15.0) -> Iterator[str]:
        next_event_index = 0

        while True:
            missing_payload: dict[str, object] | None = None

            with self._condition:
                job = self._jobs.get(job_id)

                if job is None:
                    missing_payload = {
                        "job_id": job_id,
                        "status": "failed",
                        "phase": "failed",
                        "progress": 100,
                        "message": "任务不存在或已过期。",
                        "error": {
                            "code": "JOB_NOT_FOUND",
                            "message": "Generation job was not found.",
                        },
                    }
                else:
                    while next_event_index >= len(job.events) and job.status not in TERMINAL_STATUSES:
                        self._condition.wait(timeout=heartbeat_seconds)

                        if next_event_index >= len(job.events):
                            break

                    events = job.events[next_event_index:]
                    next_event_index = len(job.events)
                    is_terminal = job.status in TERMINAL_STATUSES

            if missing_payload is not None:
                yield _format_sse("job.failed", missing_payload)
                return

            if events:
                for event in events:
                    yield _format_sse(event.name, event.payload)
            elif not is_terminal:
                yield ": heartbeat\n\n"

            if is_terminal and not events:
                return

            if is_terminal and events:
                return

    def _run(self, job_id: str, runner: JobRunner) -> None:
        try:
            result = runner(
                lambda phase, progress, message: self.update(
                    job_id,
                    phase=phase,
                    progress=progress,
                    message=message,
                )
            )

            self.complete(
                job_id,
                yaml_text=result["yaml"],
                schema_version=result["schema_version"],
                message="生成完成。",
            )
        except Exception as error:
            code = getattr(error, "code", "AI_GENERATION_FAILED")
            message = getattr(error, "message", str(error) or "生成任务失败。")
            self.fail(job_id, code=code, message=message)

    def update(self, job_id: str, phase: str, progress: int, message: str) -> None:
        with self._condition:
            job = self._jobs.get(job_id)

            if job is None or job.status in TERMINAL_STATUSES:
                return

            job.status = "running"
            job.phase = phase
            job.progress = progress
            job.message = message
            job.updated_at = datetime.now(UTC)
            job.events.append(GenerationJobEvent(name="job.status", payload=job.to_dict()))
            self._condition.notify_all()

    def complete(self, job_id: str, yaml_text: str, schema_version: str, message: str) -> None:
        with self._condition:
            job = self._jobs.get(job_id)

            if job is None:
                return

            job.status = "completed"
            job.phase = "completed"
            job.progress = 100
            job.message = message
            job.yaml = yaml_text
            job.schema_version = schema_version
            job.updated_at = datetime.now(UTC)
            job.events.append(GenerationJobEvent(name="job.completed", payload=job.to_dict()))
            self._condition.notify_all()

    def fail(self, job_id: str, code: str, message: str) -> None:
        with self._condition:
            job = self._jobs.get(job_id)

            if job is None:
                return

            job.status = "failed"
            job.phase = "failed"
            job.progress = 100
            job.message = message
            job.error = GenerationJobError(code=code, message=message)
            job.updated_at = datetime.now(UTC)
            job.events.append(GenerationJobEvent(name="job.failed", payload=job.to_dict()))
            self._condition.notify_all()


def _format_sse(event_name: str, payload: dict[str, object]) -> str:
    return f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
