import asyncio
import os
import posixpath
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from shutil import which
from textwrap import dedent

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import get_current_user
from app.database.database import get_db
from app.database.models import SSHConnection, SSHKey, User
from app.utils.ssh_utils import write_ssh_key_to_tempfile

router = APIRouter()

MAX_SCAN_PATH_LENGTH = 4096
SHELL_META_CHARS = set(";&|`$()<>")
DEFAULT_DATABASE_SCAN_PATHS_BY_ENGINE = {
    "postgresql": ["/var/lib/postgresql", "/var/lib/pgsql"],
    "mysql": ["/var/lib/mysql"],
    "mongodb": ["/var/lib/mongodb"],
    "redis": ["/var/lib/redis"],
    "sqlite": ["/var/lib/sqlite", "/var/lib/sqlite3"],
}
SQLITE_DATABASE_SUFFIXES = {".db", ".sqlite", ".sqlite3"}


class SourceTypeOption(BaseModel):
    id: str
    label: str
    description: str
    status: str
    disabled: bool = False


class ScriptDraft(BaseModel):
    name: str
    description: str
    content: str
    timeout: int


class DatabaseScriptDrafts(BaseModel):
    pre_backup: ScriptDraft
    post_backup: ScriptDraft


class DatabaseCandidate(BaseModel):
    id: str
    engine: str
    display_name: str
    backup_strategy: str
    source_directories: list[str]
    client_commands: list[str]
    documentation_url: str
    detected: bool = False
    detection_source: str | None = None
    notes: list[str]
    script_drafts: DatabaseScriptDrafts


class DatabaseDiscoveryResponse(BaseModel):
    source_types: list[SourceTypeOption]
    detections: list[DatabaseCandidate]
    templates: list[DatabaseCandidate]


class DatabaseScanRequest(BaseModel):
    source_type: str
    source_ssh_connection_id: int | None = None
    paths: list[str]


class DatabaseScanTarget(BaseModel):
    source_type: str
    source_ssh_connection_id: int | None
    label: str


class ScanWarning(BaseModel):
    code: str
    message: str
    path: str | None = None


class DatabaseScanResponse(BaseModel):
    scan_target: DatabaseScanTarget
    scanned_paths: list[str]
    detections: list[DatabaseCandidate]
    templates: list[DatabaseCandidate]
    warnings: list[ScanWarning]


@dataclass
class PathProbe:
    path: str
    exists: bool = False
    pg_version_file: bool = False
    mysql_directory: bool = False
    wired_tiger_file: bool = False
    redis_dump_file: bool = False
    sqlite_database_file: bool = False


def _script(content: str) -> str:
    return dedent(content).strip() + "\n"


def _cleanup_script(dump_dir: str) -> str:
    return _script(
        f"""
        #!/usr/bin/env bash
        set -euo pipefail

        DUMP_DIR="${{BORG_UI_DB_DUMP_DIR:-{dump_dir}}}"

        if [[ -d "$DUMP_DIR" ]]; then
          rm -rf "$DUMP_DIR"
        fi
        """
    )


def _postgresql_template() -> DatabaseCandidate:
    dump_dir = "/var/tmp/borg-ui/database-dumps/postgresql"
    return DatabaseCandidate(
        id="postgresql",
        engine="PostgreSQL",
        display_name="PostgreSQL database",
        backup_strategy="logical_dump",
        source_directories=[dump_dir],
        client_commands=["pg_dump"],
        documentation_url="https://www.postgresql.org/docs/17/app-pgdump.html",
        notes=[
            "Uses pg_dump custom format so the backup can be restored with pg_restore.",
            "Set POSTGRES_DB and standard libpq environment variables if defaults are not enough.",
        ],
        script_drafts=DatabaseScriptDrafts(
            pre_backup=ScriptDraft(
                name="Prepare PostgreSQL dump",
                description="Create a PostgreSQL custom-format dump before Borg starts.",
                timeout=900,
                content=_script(
                    f"""
                    #!/usr/bin/env bash
                    set -euo pipefail

                    DUMP_DIR="${{BORG_UI_DB_DUMP_DIR:-{dump_dir}}}"
                    DB_NAME="${{POSTGRES_DB:-postgres}}"

                    mkdir -p "$DUMP_DIR"
                    rm -f "$DUMP_DIR/${{DB_NAME}}.dump"

                    pg_dump --format=custom --file="$DUMP_DIR/${{DB_NAME}}.dump" "$DB_NAME"
                    """
                ),
            ),
            post_backup=ScriptDraft(
                name="Clean PostgreSQL dump",
                description="Remove transient PostgreSQL dump files after Borg captures them.",
                timeout=120,
                content=_cleanup_script(dump_dir),
            ),
        ),
    )


def _mysql_template() -> DatabaseCandidate:
    dump_dir = "/var/tmp/borg-ui/database-dumps/mysql"
    return DatabaseCandidate(
        id="mysql",
        engine="MySQL / MariaDB",
        display_name="MySQL or MariaDB database",
        backup_strategy="logical_dump",
        source_directories=[dump_dir],
        client_commands=["mysqldump"],
        documentation_url="https://dev.mysql.com/doc/refman/8.0/en/mysqldump.html",
        notes=[
            "Uses --single-transaction for a consistent InnoDB dump without table locks.",
            "Set MYSQL_DATABASE to dump one database, or leave it empty for all databases.",
        ],
        script_drafts=DatabaseScriptDrafts(
            pre_backup=ScriptDraft(
                name="Prepare MySQL dump",
                description="Create a MySQL dump before Borg starts.",
                timeout=900,
                content=_script(
                    f"""
                    #!/usr/bin/env bash
                    set -euo pipefail

                    DUMP_DIR="${{BORG_UI_DB_DUMP_DIR:-{dump_dir}}}"
                    MYSQL_DATABASE="${{MYSQL_DATABASE:-}}"

                    mkdir -p "$DUMP_DIR"

                    if [[ -n "$MYSQL_DATABASE" ]]; then
                      mysqldump --single-transaction --quick --routines --events \\
                        "$MYSQL_DATABASE" > "$DUMP_DIR/${{MYSQL_DATABASE}}.sql"
                    else
                      mysqldump --single-transaction --quick --routines --events \\
                        --all-databases > "$DUMP_DIR/all-databases.sql"
                    fi
                    """
                ),
            ),
            post_backup=ScriptDraft(
                name="Clean MySQL dump",
                description="Remove transient MySQL dump files after Borg captures them.",
                timeout=120,
                content=_cleanup_script(dump_dir),
            ),
        ),
    )


def _mongodb_template() -> DatabaseCandidate:
    dump_dir = "/var/tmp/borg-ui/database-dumps/mongodb"
    return DatabaseCandidate(
        id="mongodb",
        engine="MongoDB",
        display_name="MongoDB database",
        backup_strategy="logical_dump",
        source_directories=[dump_dir],
        client_commands=["mongodump"],
        documentation_url="https://www.mongodb.com/docs/database-tools/mongodump/index.html",
        notes=[
            "Uses mongodump into a Borg-managed staging directory.",
            "Set MONGODB_URI when the default local connection is not enough.",
        ],
        script_drafts=DatabaseScriptDrafts(
            pre_backup=ScriptDraft(
                name="Prepare MongoDB dump",
                description="Create a MongoDB dump before Borg starts.",
                timeout=900,
                content=_script(
                    f"""
                    #!/usr/bin/env bash
                    set -euo pipefail

                    DUMP_DIR="${{BORG_UI_DB_DUMP_DIR:-{dump_dir}}}"
                    MONGODB_URI="${{MONGODB_URI:-}}"

                    rm -rf "$DUMP_DIR"
                    mkdir -p "$DUMP_DIR"

                    if [[ -n "$MONGODB_URI" ]]; then
                      mongodump --uri "$MONGODB_URI" --out "$DUMP_DIR"
                    else
                      mongodump --out "$DUMP_DIR"
                    fi
                    """
                ),
            ),
            post_backup=ScriptDraft(
                name="Clean MongoDB dump",
                description="Remove transient MongoDB dump files after Borg captures them.",
                timeout=120,
                content=_cleanup_script(dump_dir),
            ),
        ),
    )


def _redis_template() -> DatabaseCandidate:
    dump_dir = "/var/tmp/borg-ui/database-dumps/redis"
    return DatabaseCandidate(
        id="redis",
        engine="Redis",
        display_name="Redis database",
        backup_strategy="rdb_snapshot",
        source_directories=[dump_dir],
        client_commands=["redis-cli"],
        documentation_url=(
            "https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/"
        ),
        notes=[
            "Triggers BGSAVE, waits for it to finish, then copies the RDB snapshot.",
            "Set REDIS_CLI_ARGS for host, port, TLS, or auth flags.",
        ],
        script_drafts=DatabaseScriptDrafts(
            pre_backup=ScriptDraft(
                name="Prepare Redis snapshot",
                description="Create and stage a Redis RDB snapshot before Borg starts.",
                timeout=600,
                content=_script(
                    f"""
                    #!/usr/bin/env bash
                    set -euo pipefail

                    DUMP_DIR="${{BORG_UI_DB_DUMP_DIR:-{dump_dir}}}"
                    mkdir -p "$DUMP_DIR"

                    # shellcheck disable=SC2086
                    redis-cli ${{REDIS_CLI_ARGS:-}} BGSAVE

                    while [[ "$(redis-cli ${{REDIS_CLI_ARGS:-}} INFO persistence \\
                      | awk -F: '/rdb_bgsave_in_progress/ {{print $2}}' \\
                      | tr -d '\\r')" == "1" ]]; do
                      sleep 1
                    done

                    REDIS_DIR="$(redis-cli ${{REDIS_CLI_ARGS:-}} CONFIG GET dir | tail -n 1)"
                    REDIS_RDB="$(redis-cli ${{REDIS_CLI_ARGS:-}} CONFIG GET dbfilename | tail -n 1)"
                    cp "$REDIS_DIR/$REDIS_RDB" "$DUMP_DIR/$REDIS_RDB"
                    """
                ),
            ),
            post_backup=ScriptDraft(
                name="Clean Redis snapshot",
                description="Remove transient Redis snapshot files after Borg captures them.",
                timeout=120,
                content=_cleanup_script(dump_dir),
            ),
        ),
    )


def _sqlite_template() -> DatabaseCandidate:
    dump_dir = "/var/tmp/borg-ui/database-dumps/sqlite"
    return DatabaseCandidate(
        id="sqlite",
        engine="SQLite",
        display_name="SQLite database",
        backup_strategy="online_backup",
        source_directories=[dump_dir],
        client_commands=["sqlite3"],
        documentation_url="https://www.sqlite.org/backup.html",
        notes=[
            "Uses the SQLite Online Backup API through sqlite3 .backup.",
            "Set SQLITE_DATABASE_PATH to the source database file.",
            "Set SQLITE_DATABASE_NAME when the staged backup filename should be customized.",
        ],
        script_drafts=DatabaseScriptDrafts(
            pre_backup=ScriptDraft(
                name="Prepare SQLite backup",
                description="Create a consistent SQLite backup before Borg starts.",
                timeout=300,
                content=_script(
                    f"""
                    #!/usr/bin/env bash
                    set -euo pipefail

                    DUMP_DIR="${{BORG_UI_DB_DUMP_DIR:-{dump_dir}}}"
                    SQLITE_DATABASE_PATH="${{SQLITE_DATABASE_PATH:-}}"
                    SQLITE_DATABASE_NAME="${{SQLITE_DATABASE_NAME:-database.sqlite3}}"

                    if [[ -z "$SQLITE_DATABASE_PATH" ]]; then
                      echo "Set SQLITE_DATABASE_PATH to the SQLite database file." >&2
                      exit 2
                    fi

                    if [[ ! -f "$SQLITE_DATABASE_PATH" ]]; then
                      echo "SQLite database file not found: $SQLITE_DATABASE_PATH" >&2
                      exit 2
                    fi

                    mkdir -p "$DUMP_DIR"
                    rm -f "$DUMP_DIR/$SQLITE_DATABASE_NAME"

                    sqlite3 "$SQLITE_DATABASE_PATH" <<SQL
                    .backup '$DUMP_DIR/$SQLITE_DATABASE_NAME'
                    SQL
                    """
                ),
            ),
            post_backup=ScriptDraft(
                name="Clean SQLite backup",
                description="Remove transient SQLite backup files after Borg captures them.",
                timeout=120,
                content=_cleanup_script(dump_dir),
            ),
        ),
    )


def _source_types() -> list[SourceTypeOption]:
    return [
        SourceTypeOption(
            id="paths",
            label="Files and folders",
            description="Back up local or remote paths with optional browsing.",
            status="enabled",
        ),
        SourceTypeOption(
            id="database",
            label="Database",
            description="Scan for supported databases or start from a template.",
            status="enabled",
        ),
        SourceTypeOption(
            id="container",
            label="Docker containers",
            description="Container scanning will use the same source chooser later.",
            status="planned",
            disabled=True,
        ),
    ]


def _templates() -> list[DatabaseCandidate]:
    return [
        _mongodb_template(),
        _mysql_template(),
        _postgresql_template(),
        _redis_template(),
        _sqlite_template(),
    ]


def _validate_database_scan_request(request: DatabaseScanRequest) -> list[str]:
    source_type = request.source_type.strip().lower()
    if source_type not in {"local", "remote"}:
        raise HTTPException(
            status_code=400,
            detail="source_type must be 'local' or 'remote'",
        )
    request.source_type = source_type

    if source_type == "remote" and request.source_ssh_connection_id is None:
        raise HTTPException(
            status_code=400,
            detail="source_ssh_connection_id is required for remote database scans",
        )

    if not request.paths:
        raise HTTPException(
            status_code=400,
            detail="paths must contain at least one absolute path",
        )

    validated_paths: list[str] = []
    for raw_path in request.paths:
        path = str(raw_path).strip()
        if not path:
            raise HTTPException(
                status_code=400,
                detail="paths must not contain empty values",
            )
        if len(path) > MAX_SCAN_PATH_LENGTH:
            raise HTTPException(
                status_code=400,
                detail=f"path is longer than {MAX_SCAN_PATH_LENGTH} characters",
            )
        if not path.startswith("/"):
            raise HTTPException(
                status_code=400,
                detail=f"PATH_NOT_ABSOLUTE: {path}",
            )
        if any(char in path for char in SHELL_META_CHARS):
            raise HTTPException(
                status_code=400,
                detail=f"path contains shell metacharacters: {path}",
            )
        validated_paths.append(path)

    return validated_paths


def _path_basename(path: str) -> str:
    normalized_path = path.rstrip("/")
    if not normalized_path:
        return ""
    return posixpath.basename(normalized_path).lower()


def _path_probe_matches_template(template_id: str, probe: PathProbe) -> bool:
    if not probe.exists:
        return False

    basename = _path_basename(probe.path)
    if template_id == "postgresql":
        return basename in {"postgresql", "pgsql", "postgres"} or probe.pg_version_file
    if template_id == "mysql":
        return basename in {"mysql", "mariadb"} or probe.mysql_directory
    if template_id == "mongodb":
        return basename in {"mongodb", "mongo"} or probe.wired_tiger_file
    if template_id == "redis":
        return basename == "redis" or probe.redis_dump_file
    if template_id == "sqlite":
        return basename in {"sqlite", "sqlite3"} or probe.sqlite_database_file
    return False


def _local_path_probe(path: str) -> tuple[PathProbe, ScanWarning | None]:
    candidate = Path(path)
    probe = PathProbe(path=path)
    try:
        probe.exists = candidate.exists()
        if not probe.exists:
            return probe, None

        probe.pg_version_file = (candidate / "PG_VERSION").exists()
        probe.mysql_directory = (candidate / "mysql").is_dir()
        probe.wired_tiger_file = (candidate / "WiredTiger").exists()
        probe.redis_dump_file = (candidate / "dump.rdb").exists()
        probe.sqlite_database_file = (
            candidate.is_file() and candidate.suffix.lower() in SQLITE_DATABASE_SUFFIXES
        )
        return probe, None
    except PermissionError:
        return probe, ScanWarning(
            code="PATH_PERMISSION_DENIED",
            message=f"Permission denied while scanning {path}",
            path=path,
        )
    except OSError as exc:
        return probe, ScanWarning(
            code="PATH_PERMISSION_DENIED",
            message=f"Could not scan {path}: {exc}",
            path=path,
        )


def _detect_templates_from_probes(
    templates: list[DatabaseCandidate],
    probes: list[PathProbe],
    command_available: dict[str, bool],
) -> list[DatabaseCandidate]:
    detections: list[DatabaseCandidate] = []
    for template in templates:
        matching_probe = next(
            (
                probe
                for probe in probes
                if _path_probe_matches_template(template.id, probe)
            ),
            None,
        )
        available_command = next(
            (
                command
                for command in template.client_commands
                if command_available.get(command, False)
            ),
            None,
        )

        if not matching_probe and not available_command:
            continue

        detection_source = (
            matching_probe.path
            if matching_probe
            else f"{available_command} available on PATH"
        )
        detections.append(
            template.model_copy(
                update={
                    "detected": True,
                    "detection_source": detection_source,
                }
            )
        )

    return detections


def _client_commands(templates: list[DatabaseCandidate]) -> set[str]:
    return {command for template in templates for command in template.client_commands}


def _scan_target(
    source_type: str, connection: SSHConnection | None = None
) -> DatabaseScanTarget:
    if source_type == "remote" and connection is not None:
        return DatabaseScanTarget(
            source_type="remote",
            source_ssh_connection_id=connection.id,
            label=f"{connection.username}@{connection.host}",
        )
    return DatabaseScanTarget(
        source_type="local",
        source_ssh_connection_id=None,
        label="This Borg UI server",
    )


def _scan_local_database_paths(paths: list[str]) -> DatabaseScanResponse:
    templates = _templates()
    probes: list[PathProbe] = []
    warnings: list[ScanWarning] = []

    for path in paths:
        probe, warning = _local_path_probe(path)
        probes.append(probe)
        if warning is not None:
            warnings.append(warning)

    command_available = {
        command: which(command) is not None for command in _client_commands(templates)
    }
    detections = _detect_templates_from_probes(templates, probes, command_available)
    return DatabaseScanResponse(
        scan_target=_scan_target("local"),
        scanned_paths=paths,
        detections=detections,
        templates=templates,
        warnings=warnings,
    )


async def _scan_local_database_paths_with_timeout(
    paths: list[str],
) -> DatabaseScanResponse:
    return await asyncio.wait_for(
        asyncio.to_thread(_scan_local_database_paths, paths),
        timeout=settings.scan_timeout_seconds,
    )


def _default_paths_for_template(template_id: str) -> list[str]:
    return DEFAULT_DATABASE_SCAN_PATHS_BY_ENGINE.get(template_id, [])


def _detect_template(template: DatabaseCandidate) -> DatabaseCandidate | None:
    probes = [
        _local_path_probe(path)[0] for path in _default_paths_for_template(template.id)
    ]
    command_available = {
        command: which(command) is not None for command in template.client_commands
    }
    detections = _detect_templates_from_probes(
        [template],
        probes,
        command_available,
    )
    return detections[0] if detections else None


def _build_remote_probe_script(paths: list[str], commands: set[str]) -> str:
    lines = ["set +e"]
    for path in paths:
        quoted_path = shlex.quote(path)
        lines.extend(
            [
                (
                    f"if test -e {quoted_path}; then "
                    f"printf 'PATH\\t%s\\t1\\n' {quoted_path}; else "
                    f"printf 'PATH\\t%s\\t0\\n' {quoted_path}; fi"
                ),
                (
                    f"if test -e {quoted_path}/PG_VERSION; then "
                    f"printf 'FILE\\t%s\\tPG_VERSION\\t1\\n' {quoted_path}; fi"
                ),
                (
                    f"if test -d {quoted_path}/mysql; then "
                    f"printf 'DIR\\t%s\\tmysql\\t1\\n' {quoted_path}; fi"
                ),
                (
                    f"if test -e {quoted_path}/WiredTiger; then "
                    f"printf 'FILE\\t%s\\tWiredTiger\\t1\\n' {quoted_path}; fi"
                ),
                (
                    f"if test -e {quoted_path}/dump.rdb; then "
                    f"printf 'FILE\\t%s\\tdump.rdb\\t1\\n' {quoted_path}; fi"
                ),
                (
                    f"case {quoted_path} in "
                    f"*.db|*.sqlite|*.sqlite3) "
                    f"if test -f {quoted_path}; then "
                    f"printf 'FILE\\t%s\\tSQLITE_DB\\t1\\n' {quoted_path}; fi ;; "
                    f"esac"
                ),
            ]
        )

    for command in sorted(commands):
        quoted_command = shlex.quote(command)
        lines.append(
            f"if command -v {quoted_command} >/dev/null 2>&1; then "
            f"printf 'COMMAND\\t%s\\t1\\n' {quoted_command}; else "
            f"printf 'COMMAND\\t%s\\t0\\n' {quoted_command}; fi"
        )

    return "\n".join(lines)


def _run_remote_database_probe(
    *,
    connection: SSHConnection,
    key_file_path: str,
    script: str,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    remote_command = f"sh -c {shlex.quote(script)}"
    ssh_cmd = [
        "ssh",
        "-i",
        key_file_path,
        "-p",
        str(connection.port or 22),
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        f"ConnectTimeout={max(1, int(timeout_seconds))}",
        f"{connection.username}@{connection.host}",
        remote_command,
    ]
    return subprocess.run(
        ssh_cmd,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )


def _parse_remote_probe_output(
    stdout: str, paths: list[str]
) -> tuple[list[PathProbe], dict[str, bool]]:
    probes_by_path = {path: PathProbe(path=path) for path in paths}
    command_available: dict[str, bool] = {}

    for raw_line in stdout.splitlines():
        parts = raw_line.split("\t")
        if not parts:
            continue

        record_type = parts[0]
        if record_type == "PATH" and len(parts) >= 3:
            path = parts[1]
            if path in probes_by_path:
                probes_by_path[path].exists = parts[2] == "1"
        elif record_type == "FILE" and len(parts) >= 4:
            path, file_name = parts[1], parts[2]
            probe = probes_by_path.get(path)
            if probe is None or parts[3] != "1":
                continue
            probe.exists = True
            if file_name == "PG_VERSION":
                probe.pg_version_file = True
            elif file_name == "WiredTiger":
                probe.wired_tiger_file = True
            elif file_name == "dump.rdb":
                probe.redis_dump_file = True
            elif file_name == "SQLITE_DB":
                probe.sqlite_database_file = True
        elif record_type == "DIR" and len(parts) >= 4:
            path, directory_name = parts[1], parts[2]
            probe = probes_by_path.get(path)
            if probe is not None and directory_name == "mysql" and parts[3] == "1":
                probe.exists = True
                probe.mysql_directory = True
        elif record_type == "COMMAND" and len(parts) >= 3:
            command_available[parts[1]] = parts[2] == "1"

    return list(probes_by_path.values()), command_available


def _ssh_warning_code(stderr: str) -> str:
    normalized_stderr = stderr.lower()
    if (
        "permission denied" in normalized_stderr
        or "authentication" in normalized_stderr
    ):
        return "SSH_AUTH_FAILED"
    return "SSH_HOST_UNREACHABLE"


def _failure_response(
    *,
    status_code: int,
    scan_target: DatabaseScanTarget,
    scanned_paths: list[str],
    warning: ScanWarning,
) -> JSONResponse:
    response = DatabaseScanResponse(
        scan_target=scan_target,
        scanned_paths=scanned_paths,
        detections=[],
        templates=_templates(),
        warnings=[warning],
    )
    return JSONResponse(status_code=status_code, content=response.model_dump())


async def _scan_remote_database_paths(
    request: DatabaseScanRequest,
    paths: list[str],
    db: Session,
) -> DatabaseScanResponse | JSONResponse:
    connection = (
        db.query(SSHConnection)
        .filter(SSHConnection.id == request.source_ssh_connection_id)
        .first()
    )
    if not connection:
        raise HTTPException(
            status_code=400,
            detail=(
                "source_ssh_connection_id must reference an existing SSH connection"
            ),
        )

    scan_target = _scan_target("remote", connection)
    if connection.ssh_key_id is None:
        raise HTTPException(
            status_code=400,
            detail="SSH connection has no SSH key configured",
        )

    ssh_key = db.query(SSHKey).filter(SSHKey.id == connection.ssh_key_id).first()
    if not ssh_key:
        raise HTTPException(
            status_code=400,
            detail="SSH connection references a missing SSH key",
        )

    templates = _templates()
    script = _build_remote_probe_script(paths, _client_commands(templates))
    timeout_seconds = settings.scan_timeout_seconds
    key_file_path = write_ssh_key_to_tempfile(ssh_key)
    try:
        result = await asyncio.to_thread(
            _run_remote_database_probe,
            connection=connection,
            key_file_path=key_file_path,
            script=script,
            timeout_seconds=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return _failure_response(
            status_code=504,
            scan_target=scan_target,
            scanned_paths=paths,
            warning=ScanWarning(
                code="SCAN_TIMEOUT",
                message=f"Database scan timed out for {scan_target.label}",
                path=None,
            ),
        )
    finally:
        if os.path.exists(key_file_path):
            os.unlink(key_file_path)

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        return _failure_response(
            status_code=502,
            scan_target=scan_target,
            scanned_paths=paths,
            warning=ScanWarning(
                code=_ssh_warning_code(stderr),
                message=f"Could not connect to {scan_target.label}: {stderr}",
                path=None,
            ),
        )

    probes, command_available = _parse_remote_probe_output(result.stdout or "", paths)
    detections = _detect_templates_from_probes(templates, probes, command_available)
    return DatabaseScanResponse(
        scan_target=scan_target,
        scanned_paths=paths,
        detections=detections,
        templates=templates,
        warnings=[],
    )


@router.post("/databases/scan", response_model=DatabaseScanResponse)
async def scan_databases(
    request: DatabaseScanRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DatabaseScanResponse | JSONResponse:
    del current_user
    paths = _validate_database_scan_request(request)

    try:
        if request.source_type == "remote":
            return await _scan_remote_database_paths(request, paths, db)
        return await _scan_local_database_paths_with_timeout(paths)
    except asyncio.TimeoutError:
        return _failure_response(
            status_code=504,
            scan_target=_scan_target(request.source_type),
            scanned_paths=paths,
            warning=ScanWarning(
                code="SCAN_TIMEOUT",
                message="Database scan timed out",
                path=None,
            ),
        )


@router.get("/databases", response_model=DatabaseDiscoveryResponse)
async def discover_databases(
    current_user: User = Depends(get_current_user),
) -> DatabaseDiscoveryResponse:
    del current_user
    templates = _templates()
    detections = [
        detection for template in templates if (detection := _detect_template(template))
    ]
    return DatabaseDiscoveryResponse(
        source_types=_source_types(),
        detections=detections,
        templates=templates,
    )
