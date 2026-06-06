from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_FILES = (
    REPO_ROOT / ".env",
    BACKEND_ROOT / ".env",
)


def load_config_files(paths: Iterable[Path] | None = None) -> list[Path]:
    configured_path = os.getenv("AI_CONFIG_FILE", "").strip()
    candidate_paths = [Path(configured_path)] if configured_path and paths is None else list(paths or DEFAULT_CONFIG_FILES)
    loaded_paths: list[Path] = []

    for path in candidate_paths:
        resolved_path = path.expanduser().resolve()

        if not resolved_path.is_file():
            continue

        _load_env_file(resolved_path)
        loaded_paths.append(resolved_path)

    return loaded_paths


def _load_env_file(path: Path) -> None:
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[7:].strip()

        if "=" not in line:
            continue

        name, raw_value = line.split("=", 1)
        name = name.strip()

        if not name:
            continue

        os.environ.setdefault(name, _parse_env_value(raw_value))


def _parse_env_value(raw_value: str) -> str:
    value = raw_value.strip()

    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]

    return value
