from __future__ import annotations

import socket
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.security import get_current_user
from app.database.models import User

router = APIRouter()

DatabaseStatus = Literal["detected", "template"]
DetectionConfidence = Literal["high", "medium", "template"]


class SourceTypeResponse(BaseModel):
    id: str
    label: str
    description: str
    enabled: bool
    unavailable_reason: str | None = None


class DatabaseTargetResponse(BaseModel):
    id: str
    engine: str
    engine_label: str
    display_name: str
    status: DatabaseStatus
    confidence: DetectionConfidence
    service_name: str
    source_directories: list[str]
    warnings: list[str]
    pre_backup_script: str
    post_backup_script: str
    script_name_base: str
    documentation_url: str


class DatabaseDiscoveryResponse(BaseModel):
    source_types: list[SourceTypeResponse]
    databases: list[DatabaseTargetResponse]
    templates: list[DatabaseTargetResponse]


DATABASE_DEFINITIONS = [
    {
        "engine": "postgresql",
        "engine_label": "PostgreSQL",
        "service_name": "postgresql",
        "data_directories": ["/var/lib/postgresql", "/var/lib/pgsql"],
        "sockets": ["/var/run/postgresql/.s.PGSQL.5432", "/tmp/.s.PGSQL.5432"],
        "ports": [5432],
        "documentation_url": "https://www.postgresql.org/docs/17/app-pgdump.html",
    },
    {
        "engine": "mysql",
        "engine_label": "MySQL / MariaDB",
        "service_name": "mysql",
        "data_directories": ["/var/lib/mysql"],
        "sockets": ["/var/run/mysqld/mysqld.sock", "/tmp/mysql.sock"],
        "ports": [3306],
        "documentation_url": "https://dev.mysql.com/doc/refman/8.4/en/using-mysqldump.html",
    },
    {
        "engine": "mongodb",
        "engine_label": "MongoDB",
        "service_name": "mongod",
        "data_directories": ["/var/lib/mongodb", "/var/lib/mongo"],
        "sockets": ["/tmp/mongodb-27017.sock"],
        "ports": [27017],
        "documentation_url": "https://www.mongodb.com/docs/database-tools/mongodump/index.html",
    },
    {
        "engine": "redis",
        "engine_label": "Redis",
        "service_name": "redis-server",
        "data_directories": ["/var/lib/redis"],
        "sockets": ["/var/run/redis/redis-server.sock", "/tmp/redis.sock"],
        "ports": [6379],
        "documentation_url": "https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/",
    },
]


def _path_exists(path: str) -> bool:
    return Path(path).exists()


def _is_port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.08)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def _source_types() -> list[SourceTypeResponse]:
    return [
        SourceTypeResponse(
            id="paths",
            label="Files and folders",
            description="Choose files or folders from the Borg UI server or a remote client.",
            enabled=True,
        ),
        SourceTypeResponse(
            id="database",
            label="Database",
            description="Scan supported local databases and prepare backup scripts.",
            enabled=True,
        ),
        SourceTypeResponse(
            id="container",
            label="Docker containers",
            description="Container scanning will use this same source chooser next.",
            enabled=False,
            unavailable_reason="Container scanning is planned for a later release.",
        ),
    ]


def _service_script(service_name: str, action: Literal["start", "stop"]) -> str:
    action_label = "Stop" if action == "stop" else "Start"
    return f"""#!/usr/bin/env bash
set -euo pipefail

# {action_label} the database service around the Borg backup.
# Override SERVICE_NAME if your distribution uses a different unit name.
SERVICE_NAME="${{SERVICE_NAME:-{service_name}}}"

if command -v systemctl >/dev/null 2>&1; then
  sudo -n systemctl {action} "$SERVICE_NAME"
elif command -v service >/dev/null 2>&1; then
  sudo -n service "$SERVICE_NAME" {action}
else
  echo "No supported service manager found. Edit this script for your host." >&2
  exit 1
fi
"""


def _build_target(
    definition: dict[str, object],
    *,
    status: DatabaseStatus,
    confidence: DetectionConfidence,
    source_directories: list[str],
) -> DatabaseTargetResponse:
    engine = str(definition["engine"])
    engine_label = str(definition["engine_label"])
    service_name = str(definition["service_name"])
    return DatabaseTargetResponse(
        id=f"{engine}-{status}",
        engine=engine,
        engine_label=engine_label,
        display_name=(
            f"{engine_label} on this server"
            if status == "detected"
            else f"{engine_label} template"
        ),
        status=status,
        confidence=confidence,
        service_name=service_name,
        source_directories=source_directories,
        warnings=[
            "Review generated scripts before enabling the plan.",
            "Stopping services may require passwordless sudo for the Borg UI runtime user.",
        ],
        pre_backup_script=_service_script(service_name, "stop"),
        post_backup_script=_service_script(service_name, "start"),
        script_name_base=f"{engine_label} stop-start backup",
        documentation_url=str(definition["documentation_url"]),
    )


def _detect_target(definition: dict[str, object]) -> DatabaseTargetResponse | None:
    data_directories = [str(path) for path in definition["data_directories"]]
    sockets = [str(path) for path in definition["sockets"]]
    ports = [int(port) for port in definition["ports"]]

    existing_directories = [path for path in data_directories if _path_exists(path)]
    socket_found = any(_path_exists(path) for path in sockets)
    port_found = any(_is_port_open(port) for port in ports)

    if not existing_directories and not socket_found and not port_found:
        return None

    confidence: DetectionConfidence = "high" if socket_found or port_found else "medium"
    return _build_target(
        definition,
        status="detected",
        confidence=confidence,
        source_directories=existing_directories or [data_directories[0]],
    )


def _template_target(definition: dict[str, object]) -> DatabaseTargetResponse:
    data_directories = [str(path) for path in definition["data_directories"]]
    return _build_target(
        definition,
        status="template",
        confidence="template",
        source_directories=[data_directories[0]],
    )


@router.get("/databases", response_model=DatabaseDiscoveryResponse)
async def scan_databases(
    current_user: User = Depends(get_current_user),
) -> DatabaseDiscoveryResponse:
    _ = current_user
    detected = [
        target
        for definition in DATABASE_DEFINITIONS
        if (target := _detect_target(definition)) is not None
    ]

    return DatabaseDiscoveryResponse(
        source_types=_source_types(),
        databases=detected,
        templates=[_template_target(definition) for definition in DATABASE_DEFINITIONS],
    )
