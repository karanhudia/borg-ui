from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import psutil
from pydantic import BaseModel, Field


Confidence = Literal["high", "medium", "low"]


class SourceTypeDiscovery(BaseModel):
    id: str
    label: str
    description: str
    enabled: bool = True
    planned: bool = False


class ScriptTemplate(BaseModel):
    name: str
    description: str
    content: str
    timeout: int = 120
    run_on: str = "always"


class DatabaseSourceCandidate(BaseModel):
    id: str
    engine: str
    engine_label: str
    name: str
    status: str
    source_directories: list[str]
    service_name: str
    discovery_source: str
    confidence: Confidence
    notes: list[str] = Field(default_factory=list)
    pre_backup_script: ScriptTemplate
    post_backup_script: ScriptTemplate


class SourceDiscoveryResult(BaseModel):
    scanned_at: str
    source_types: list[SourceTypeDiscovery]
    databases: list[DatabaseSourceCandidate]
    templates: list[DatabaseSourceCandidate]


@dataclass(frozen=True)
class DatabaseDefinition:
    engine: str
    label: str
    process_names: tuple[str, ...]
    service_name: str
    path_args: tuple[str, ...]
    default_paths: tuple[str, ...]


DATABASE_DEFINITIONS: tuple[DatabaseDefinition, ...] = (
    DatabaseDefinition(
        engine="postgresql",
        label="PostgreSQL",
        process_names=("postgres", "postmaster"),
        service_name="postgresql",
        path_args=("-D", "--data-directory"),
        default_paths=(
            "/var/lib/postgresql",
            "/var/lib/pgsql",
            "/var/lib/postgres",
        ),
    ),
    DatabaseDefinition(
        engine="mysql",
        label="MySQL / MariaDB",
        process_names=("mysqld", "mariadbd"),
        service_name="mysql",
        path_args=("--datadir",),
        default_paths=("/var/lib/mysql",),
    ),
    DatabaseDefinition(
        engine="mongodb",
        label="MongoDB",
        process_names=("mongod",),
        service_name="mongod",
        path_args=("--dbpath",),
        default_paths=("/var/lib/mongodb", "/data/db"),
    ),
    DatabaseDefinition(
        engine="redis",
        label="Redis",
        process_names=("redis-server",),
        service_name="redis-server",
        path_args=("--dir",),
        default_paths=("/var/lib/redis",),
    ),
)


def _source_types() -> list[SourceTypeDiscovery]:
    return [
        SourceTypeDiscovery(
            id="paths",
            label="Paths",
            description="Pick local or remote files and directories manually.",
        ),
        SourceTypeDiscovery(
            id="database",
            label="Databases",
            description="Scan for supported local database stores.",
        ),
        SourceTypeDiscovery(
            id="container",
            label="Containers",
            description="Docker container scanning is planned for a later workflow.",
            enabled=False,
            planned=True,
        ),
    ]


def _script_content(action: Literal["stop", "start"], service_name: str) -> str:
    title = "Stop" if action == "stop" else "Start"
    return f"""#!/bin/sh
set -eu

SERVICE_NAME="${{DB_SERVICE_NAME:-{service_name}}}"

if command -v systemctl >/dev/null 2>&1; then
  systemctl {action} "$SERVICE_NAME"
elif command -v service >/dev/null 2>&1; then
  service "$SERVICE_NAME" {action}
else
  echo "No service manager found. {title} $SERVICE_NAME manually or edit this script." >&2
  exit 1
fi
"""


def _scripts_for(
    definition: DatabaseDefinition,
) -> tuple[ScriptTemplate, ScriptTemplate]:
    pre = ScriptTemplate(
        name=f"Stop {definition.label} before backup",
        description=(
            f"Stop {definition.label} before the Borg snapshot for a "
            "filesystem-consistent backup."
        ),
        content=_script_content("stop", definition.service_name),
        timeout=120,
        run_on="always",
    )
    post = ScriptTemplate(
        name=f"Start {definition.label} after backup",
        description=f"Start {definition.label} after the Borg snapshot completes.",
        content=_script_content("start", definition.service_name),
        timeout=120,
        run_on="always",
    )
    return pre, post


def _normalize_process(process: Any) -> dict[str, Any]:
    if isinstance(process, dict):
        return process
    return getattr(process, "info", {}) or {}


def _iter_processes() -> list[dict[str, Any]]:
    processes: list[dict[str, Any]] = []
    for process in psutil.process_iter(["name", "cmdline"]):
        try:
            processes.append(_normalize_process(process))
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return processes


def _process_name(process: dict[str, Any]) -> str:
    name = str(process.get("name") or "").strip()
    if name:
        return Path(name).name.lower()
    cmdline = process.get("cmdline") or []
    if cmdline:
        return Path(str(cmdline[0])).name.lower()
    return ""


def _process_matches(process: dict[str, Any], definition: DatabaseDefinition) -> bool:
    process_name = _process_name(process)
    if process_name in definition.process_names:
        return True

    cmdline = [Path(str(part)).name.lower() for part in process.get("cmdline") or []]
    return any(name in cmdline for name in definition.process_names)


def _extract_path_from_cmdline(
    cmdline: list[str], definition: DatabaseDefinition
) -> str | None:
    for index, part in enumerate(cmdline):
        for arg_name in definition.path_args:
            if part == arg_name and index + 1 < len(cmdline):
                return cmdline[index + 1]
            prefix = f"{arg_name}="
            if part.startswith(prefix):
                return part.removeprefix(prefix)
    return None


def _first_existing_path(
    paths: Iterable[str], path_exists: Callable[[str], bool]
) -> str | None:
    for path in paths:
        if path_exists(path):
            return path
    return None


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "source"


def _candidate(
    definition: DatabaseDefinition,
    *,
    status: str,
    source_path: str,
    discovery_source: str,
    confidence: Confidence,
) -> DatabaseSourceCandidate:
    pre, post = _scripts_for(definition)
    source_directories = [source_path]
    return DatabaseSourceCandidate(
        id=f"{definition.engine}-{discovery_source}-{_slug(source_path)}",
        engine=definition.engine,
        engine_label=definition.label,
        name=f"{definition.label} {status.replace('_', ' ')}",
        status=status,
        source_directories=source_directories,
        service_name=definition.service_name,
        discovery_source=discovery_source,
        confidence=confidence,
        notes=[
            (
                f"Back up {definition.label} as a filesystem source by stopping "
                "the service before Borg runs and starting it afterwards."
            ),
            "Review the data path and scripts before saving the plan.",
        ],
        pre_backup_script=pre,
        post_backup_script=post,
    )


def _template(definition: DatabaseDefinition) -> DatabaseSourceCandidate:
    return _candidate(
        definition,
        status="template",
        source_path=definition.default_paths[0],
        discovery_source="template",
        confidence="low",
    )


def scan_database_sources(
    *,
    processes: Iterable[dict[str, Any]] | None = None,
    path_exists: Callable[[str], bool] | None = None,
) -> SourceDiscoveryResult:
    process_list = list(processes) if processes is not None else _iter_processes()
    exists = path_exists or (lambda path: Path(path).exists())
    databases: list[DatabaseSourceCandidate] = []
    seen_ids: set[str] = set()

    for definition in DATABASE_DEFINITIONS:
        matching_processes = [
            process for process in process_list if _process_matches(process, definition)
        ]
        for process in matching_processes:
            cmdline = [str(part) for part in process.get("cmdline") or []]
            source_path = _extract_path_from_cmdline(cmdline, definition)
            confidence: Confidence = "high"
            if not source_path:
                source_path = _first_existing_path(definition.default_paths, exists)
                confidence = "medium" if source_path else "low"
            if not source_path:
                source_path = definition.default_paths[0]

            candidate = _candidate(
                definition,
                status="running",
                source_path=source_path,
                discovery_source="process",
                confidence=confidence,
            )
            if candidate.id not in seen_ids:
                databases.append(candidate)
                seen_ids.add(candidate.id)

        if matching_processes:
            continue

        existing_path = _first_existing_path(definition.default_paths, exists)
        if existing_path:
            candidate = _candidate(
                definition,
                status="path_found",
                source_path=existing_path,
                discovery_source="path",
                confidence="medium",
            )
            if candidate.id not in seen_ids:
                databases.append(candidate)
                seen_ids.add(candidate.id)

    return SourceDiscoveryResult(
        scanned_at=datetime.now(timezone.utc).isoformat(),
        source_types=_source_types(),
        databases=databases,
        templates=[_template(definition) for definition in DATABASE_DEFINITIONS],
    )
