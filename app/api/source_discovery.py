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
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import get_current_user
from app.database.database import get_db
from app.database.models import SSHConnection, SSHKey, User
from app.services.filesystem_snapshot_service import DEFAULT_SNAPSHOT_STAGING_ROOT
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

# Recursive walk configuration. The user picks any value within these bounds
# from the Advanced section of the scan dialog. Depth 0 reproduces the legacy
# non-recursive behavior; depth 6 reaches /var/lib/docker/volumes/<name>/_data
# from a / root.
DEFAULT_SCAN_MAX_DEPTH = 6
MIN_SCAN_MAX_DEPTH = 0
MAX_SCAN_MAX_DEPTH = 10
DEFAULT_SCAN_TIMEOUT_SECONDS = 30
MIN_SCAN_TIMEOUT_SECONDS = 1
MAX_SCAN_TIMEOUT_SECONDS = 300

# Directories that almost never contain a real DB the user wants to discover
# and almost always contain a lot of noise. Safe to skip by default.
DEFAULT_SCAN_IGNORE_PATTERNS = [
    "node_modules",
    ".git",
    ".cache",
    "dist",
    "target",
    "build",
    "__pycache__",
    "overlay2",  # /var/lib/docker/overlay2 image layer storage
    "bin",
    "boot",
    "dev",
    "proc",
    "run",
    "sbin",
    "sys",
    "tmp",
    "usr",
]

# Ignore patterns are matched against directory basenames during the walk.
# They get pasted into a sh `find -name` clause, so they must be ordinary
# filename tokens: no shell metacharacters, no slashes, no glob trickery
# beyond `*` (we accept that for things like "*.tmp" if anyone wants it).
ALLOWED_IGNORE_PATTERN_CHARS = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-*"
)
MAX_IGNORE_PATTERN_LENGTH = 64
MAX_IGNORE_PATTERN_COUNT = 32


class SourceTypeOption(BaseModel):
    id: str
    label: str
    description: str
    status: str
    disabled: bool = False


class FilesystemSnapshotProviderCapability(BaseModel):
    id: str
    label: str
    command: str
    available: bool
    requirements: list[str]


class FilesystemSnapshotCapabilitiesResponse(BaseModel):
    providers: list[FilesystemSnapshotProviderCapability]
    supported_source_types: list[str]
    unsupported_source_targets: list[str]
    default_staging_path: str


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
    # Recursive walk options. All optional; validation fills in safe defaults
    # so existing clients that do not set these continue to work unchanged.
    max_depth: int | None = None
    ignore_patterns: list[str] | None = None
    timeout_seconds: int | None = None


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
            "Uses the SQLite Online Backup API through sqlite3, or Python 3 as a fallback.",
            "Set SQLITE_DATABASE_PATH to the source database file.",
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
                    SQLITE_DATABASE_PATH="${{BORG_UI_DB_SOURCE_PATH:-${{SQLITE_DATABASE_PATH:-}}}}"
                    DUMP_FILE="$DUMP_DIR/database.sqlite3"

                    if [[ -z "$SQLITE_DATABASE_PATH" ]]; then
                      echo "Set SQLITE_DATABASE_PATH to the SQLite database file." >&2
                      exit 2
                    fi

                    if [[ ! -f "$SQLITE_DATABASE_PATH" ]]; then
                      echo "SQLite database file not found: $SQLITE_DATABASE_PATH" >&2
                      exit 2
                    fi

                    mkdir -p "$DUMP_DIR"
                    rm -f "$DUMP_FILE"

                    if command -v sqlite3 >/dev/null 2>&1; then
                      sqlite3 "$SQLITE_DATABASE_PATH" <<SQL
                    .backup '$DUMP_FILE'
                    SQL
                    elif command -v python3 >/dev/null 2>&1; then
                      python3 - "$SQLITE_DATABASE_PATH" "$DUMP_FILE" <<'PY'
                    import sys

                    try:
                        import sqlite3
                    except ImportError:
                        print(
                            "Python 3 is installed, but its sqlite3 module is unavailable. "
                            "Install sqlite3 or Python sqlite3 support on the source machine.",
                            file=sys.stderr,
                        )
                        raise SystemExit(127)

                    source_path, dump_file = sys.argv[1], sys.argv[2]
                    source = sqlite3.connect("file:" + source_path + "?mode=ro", uri=True)
                    try:
                        destination = sqlite3.connect(dump_file)
                        try:
                            source.backup(destination)
                        finally:
                            destination.close()
                    finally:
                        source.close()
                    PY
                    else
                      echo "SQLite backup requires sqlite3 or python3 with sqlite3 support on the source machine." >&2
                      exit 127
                    fi
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
            description="Export a Docker container filesystem into a Borg-readable staging path.",
            status="enabled",
        ),
    ]


def _filesystem_snapshot_provider_capabilities() -> list[
    FilesystemSnapshotProviderCapability
]:
    return [
        FilesystemSnapshotProviderCapability(
            id="btrfs",
            label="btrfs read-only subvolume snapshot",
            command="btrfs",
            available=which("btrfs") is not None,
            requirements=[
                "The selected path must be a btrfs subvolume visible to the Borg UI server.",
                "The Borg UI runtime user needs permission to create and delete read-only subvolume snapshots.",
            ],
        ),
        FilesystemSnapshotProviderCapability(
            id="zfs",
            label="zfs dataset snapshot",
            command="zfs",
            available=which("zfs") is not None,
            requirements=[
                "The selected path must live under the configured zfs dataset mountpoint.",
                "The Borg UI runtime user needs permission to create and destroy zfs snapshots.",
            ],
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

    # Normalise the recursive-walk options in place. Anything missing or out
    # of range gets clamped to a safe default rather than rejected, so the
    # client never has to know the bounds.
    max_depth = (
        request.max_depth if request.max_depth is not None else DEFAULT_SCAN_MAX_DEPTH
    )
    if max_depth < MIN_SCAN_MAX_DEPTH or max_depth > MAX_SCAN_MAX_DEPTH:
        raise HTTPException(
            status_code=400,
            detail=(
                f"max_depth must be between {MIN_SCAN_MAX_DEPTH} and {MAX_SCAN_MAX_DEPTH}"
            ),
        )
    request.max_depth = max_depth

    timeout_seconds = (
        request.timeout_seconds
        if request.timeout_seconds is not None
        else DEFAULT_SCAN_TIMEOUT_SECONDS
    )
    if (
        timeout_seconds < MIN_SCAN_TIMEOUT_SECONDS
        or timeout_seconds > MAX_SCAN_TIMEOUT_SECONDS
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                f"timeout_seconds must be between {MIN_SCAN_TIMEOUT_SECONDS}"
                f" and {MAX_SCAN_TIMEOUT_SECONDS}"
            ),
        )
    request.timeout_seconds = timeout_seconds

    raw_patterns = (
        request.ignore_patterns
        if request.ignore_patterns is not None
        else list(DEFAULT_SCAN_IGNORE_PATTERNS)
    )
    if len(raw_patterns) > MAX_IGNORE_PATTERN_COUNT:
        raise HTTPException(
            status_code=400,
            detail=f"ignore_patterns may not have more than {MAX_IGNORE_PATTERN_COUNT} entries",
        )
    validated_patterns: list[str] = []
    for raw_pattern in raw_patterns:
        pattern = str(raw_pattern).strip()
        if not pattern:
            continue
        if len(pattern) > MAX_IGNORE_PATTERN_LENGTH:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"ignore pattern is longer than {MAX_IGNORE_PATTERN_LENGTH} characters"
                ),
            )
        if any(char not in ALLOWED_IGNORE_PATTERN_CHARS for char in pattern):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"ignore pattern contains disallowed characters: {pattern!r}"
                    " (allowed: letters, digits, '.', '_', '-', '*')"
                ),
            )
        validated_patterns.append(pattern)
    request.ignore_patterns = validated_patterns

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


def _configured_sqlite_database_path() -> Path | None:
    try:
        database_url = make_url(settings.database_url)
    except Exception:
        return None

    if not database_url.drivername.startswith("sqlite"):
        return None

    database_path = database_url.database
    if not database_path or database_path == ":memory:":
        return None

    try:
        return Path(database_path).expanduser().resolve(strict=False)
    except OSError:
        return Path(os.path.abspath(database_path))


def _is_configured_sqlite_database(path: Path) -> bool:
    configured_path = _configured_sqlite_database_path()
    if configured_path is None:
        return False

    try:
        candidate_path = path.expanduser().resolve(strict=False)
    except OSError:
        candidate_path = Path(os.path.abspath(path))

    return candidate_path == configured_path


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
            candidate.is_file()
            and candidate.suffix.lower() in SQLITE_DATABASE_SUFFIXES
            and not _is_configured_sqlite_database(candidate)
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


def _inject_detected_path_into_script(content: str, detected_path: str) -> str:
    """Prepend a context block to a bash script that names the detected DB
    instance and exposes its path as BORG_UI_DETECTED_PATH. The injection
    sits right after `set -euo pipefail` so the variable is available to
    everything that follows. Scripts that don't use pipefail still get the
    injection at the top, after any shebang."""
    safe_path = shlex.quote(detected_path)
    block = (
        "\n# Discovered by Borg UI at:\n"
        f"#   {detected_path}\n"
        "# Override by exporting BORG_UI_DB_SOURCE_PATH before this script runs.\n"
        f'BORG_UI_DB_SOURCE_PATH="${{BORG_UI_DB_SOURCE_PATH:-{safe_path}}}"\n'
        f'BORG_UI_DETECTED_PATH="${{BORG_UI_DETECTED_PATH:-$BORG_UI_DB_SOURCE_PATH}}"\n'
    )

    pipefail_marker = "set -euo pipefail\n"
    if pipefail_marker in content:
        return content.replace(pipefail_marker, pipefail_marker + block, 1)

    # No pipefail line; insert after the shebang if present, else at the top.
    lines = content.splitlines(keepends=True)
    if lines and lines[0].startswith("#!"):
        return lines[0] + block + "".join(lines[1:])
    return block + content


def _path_probe_match_score(template_id: str, probe: PathProbe) -> int:
    if not _path_probe_matches_template(template_id, probe):
        return 0
    if template_id == "postgresql" and probe.pg_version_file:
        return 3
    if template_id == "mysql" and probe.mysql_directory:
        return 3
    if template_id == "mongodb" and probe.wired_tiger_file:
        return 3
    if template_id == "redis" and probe.redis_dump_file:
        return 3
    if template_id == "sqlite" and probe.sqlite_database_file:
        return 3
    return 1


def _matching_probes_for_template(
    template_id: str, probes: list[PathProbe]
) -> list[PathProbe]:
    scored_probes = [
        (probe, score)
        for probe in probes
        if (score := _path_probe_match_score(template_id, probe)) > 0
    ]
    if not scored_probes:
        return []

    best_score = max(score for _, score in scored_probes)
    seen_paths: set[str] = set()
    matches: list[PathProbe] = []
    for probe, score in scored_probes:
        if score != best_score or probe.path in seen_paths:
            continue
        seen_paths.add(probe.path)
        matches.append(probe)
    return matches


def _detect_templates_from_probes(
    templates: list[DatabaseCandidate],
    probes: list[PathProbe],
    command_available: dict[str, bool],
) -> list[DatabaseCandidate]:
    detections: list[DatabaseCandidate] = []
    for template in templates:
        matching_probes = _matching_probes_for_template(template.id, probes)
        available_command = next(
            (
                command
                for command in template.client_commands
                if command_available.get(command, False)
            ),
            None,
        )

        if not matching_probes and not available_command:
            continue

        if matching_probes:
            for matching_probe in matching_probes:
                detections.append(
                    template.model_copy(
                        update={
                            "detected": True,
                            "detection_source": matching_probe.path,
                        }
                    )
                )
            continue

        # A SQLite client on PATH is not a database instance. Unlike server
        # engines, SQLite needs an actual file path before the backup can be
        # configured.
        if template.id == "sqlite":
            continue

        detections.append(
            template.model_copy(
                update={
                    "detected": True,
                    "detection_source": f"{available_command} available on PATH",
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


def _walk_local_path(
    root: str,
    max_depth: int,
    ignore_patterns: list[str],
) -> tuple[list[PathProbe], list[ScanWarning]]:
    """Walk one root path emitting probes for every directory that looks like
    a DB data dir plus every file that looks like a SQLite database. Depth 0
    only probes the root itself; depth 1 also probes its immediate children;
    and so on up to max_depth. Directories whose basename matches one of the
    ignore patterns are pruned before descending."""
    probes: list[PathProbe] = []
    warnings: list[ScanWarning] = []
    root_path = Path(root)

    # Always probe the root itself; this preserves the legacy "you can point
    # at a specific dir" behaviour even when max_depth is 0.
    root_probe, root_warning = _local_path_probe(root)
    probes.append(root_probe)
    if root_warning is not None:
        warnings.append(root_warning)
    if not root_probe.exists or not root_path.is_dir() or max_depth == 0:
        return probes, warnings

    ignore_set = {p for p in ignore_patterns if "*" not in p}
    # Patterns with a glob char get matched via fnmatch; pure-text patterns
    # use a set for O(1) lookup.
    glob_patterns = [p for p in ignore_patterns if "*" in p]

    def is_ignored(name: str) -> bool:
        if name in ignore_set:
            return True
        if not glob_patterns:
            return False
        from fnmatch import fnmatchcase

        return any(fnmatchcase(name, pattern) for pattern in glob_patterns)

    # os.walk gives us topdown control so we can prune in-place.
    root_depth = len(root_path.parts)
    try:
        for current_dir, dirnames, filenames in os.walk(root, followlinks=False):
            current_depth = len(Path(current_dir).parts) - root_depth
            # We already probed the root above; descend further only if depth
            # budget remains.
            if current_depth >= max_depth:
                dirnames[:] = []
                continue

            # Prune ignored dirs in-place so os.walk does not descend into
            # them. This is the key cost-control mechanism.
            dirnames[:] = [d for d in dirnames if not is_ignored(d)]

            # Probe each surviving subdirectory at this level. We avoid
            # probing the root again (already done above).
            for dirname in dirnames:
                child = os.path.join(current_dir, dirname)
                if child == root:
                    continue
                probe, warning = _local_path_probe(child)
                if probe.exists:
                    probes.append(probe)
                if warning is not None:
                    warnings.append(warning)

            # Sqlite databases live as files, not dirs. Pick them up here.
            for filename in filenames:
                lower = filename.lower()
                if not any(
                    lower.endswith(suffix) for suffix in SQLITE_DATABASE_SUFFIXES
                ):
                    continue
                file_path = os.path.join(current_dir, filename)
                probe, warning = _local_path_probe(file_path)
                if probe.exists:
                    probes.append(probe)
                if warning is not None:
                    warnings.append(warning)
    except PermissionError:
        warnings.append(
            ScanWarning(
                code="PATH_PERMISSION_DENIED",
                message=f"Permission denied while walking {root}",
                path=root,
            )
        )
    except OSError as exc:
        warnings.append(
            ScanWarning(
                code="PATH_PERMISSION_DENIED",
                message=f"Could not walk {root}: {exc}",
                path=root,
            )
        )

    return probes, warnings


def _scan_local_database_paths(
    paths: list[str],
    max_depth: int = DEFAULT_SCAN_MAX_DEPTH,
    ignore_patterns: list[str] | None = None,
) -> DatabaseScanResponse:
    templates = _templates()
    patterns = (
        ignore_patterns if ignore_patterns is not None else DEFAULT_SCAN_IGNORE_PATTERNS
    )
    probes: list[PathProbe] = []
    warnings: list[ScanWarning] = []

    for path in paths:
        path_probes, path_warnings = _walk_local_path(path, max_depth, patterns)
        probes.extend(path_probes)
        warnings.extend(path_warnings)

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
    max_depth: int,
    ignore_patterns: list[str],
    timeout_seconds: int,
) -> DatabaseScanResponse:
    return await asyncio.wait_for(
        asyncio.to_thread(
            _scan_local_database_paths, paths, max_depth, ignore_patterns
        ),
        timeout=timeout_seconds,
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


def _build_remote_probe_script(
    paths: list[str],
    commands: set[str],
    max_depth: int,
    ignore_patterns: list[str],
) -> str:
    """Build a POSIX sh script that walks each root with `find -maxdepth -prune`
    and emits one MATCH line per discovered DB signature, plus EXIST lines for
    each root and COMMAND lines for each client CLI. Output is tab-separated;
    see _parse_remote_probe_output for the format."""
    lines = ["set +e"]

    # Build the `-name X -o -name Y ...` prune clause once. ignore_patterns
    # are pre-validated to allowed chars only, so they are safe to inline.
    prune_clause = ""
    if ignore_patterns:
        ored = " -o ".join(f"-name {shlex.quote(p)}" for p in ignore_patterns)
        prune_clause = f"\\( -type d \\( {ored} \\) -prune \\) -o"

    # The match expression. We list every signature we care about; classify
    # what kind of match it is on the server from the basename + extension.
    match_expr = (
        "\\("
        " \\( -type f -name PG_VERSION \\)"
        " -o \\( -type f -name WiredTiger \\)"
        " -o \\( -type f -name dump.rdb \\)"
        " -o \\( -type d \\("
        " -name mysql -o -name mariadb"
        " -o -name postgresql -o -name pgsql -o -name postgres"
        " -o -name mongodb -o -name mongo"
        " -o -name redis"
        " -o -name sqlite -o -name sqlite3"
        " \\) \\)"
        " -o \\( -type f \\("
        " -name '*.db' -o -name '*.sqlite' -o -name '*.sqlite3'"
        " \\) \\)"
        " \\) -print"
    )

    for path in paths:
        quoted_path = shlex.quote(path)
        lines.append(
            f"if test -e {quoted_path}; then "
            f"printf 'EXIST\\t%s\\t1\\n' {quoted_path}; else "
            f"printf 'EXIST\\t%s\\t0\\n' {quoted_path}; fi"
        )
        # Stream find's output, prepending MATCH<TAB>. Stderr is muted because
        # walking from / will produce a flood of "Permission denied" lines
        # that we cannot act on anyway.
        find_cmd = (
            f"find {quoted_path} -maxdepth {max_depth} "
            f"{prune_clause} {match_expr} 2>/dev/null"
        )
        lines.append(
            f"{find_cmd} | while IFS= read -r __m; do "
            f"printf 'MATCH\\t%s\\n' \"$__m\"; done"
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
    """Parse the tab-separated probe output. The script emits:
      EXIST<TAB>root<TAB>0|1            - root existence
      MATCH<TAB>absolute_match_path     - a discovered DB signature
      COMMAND<TAB>cmd<TAB>0|1           - client CLI availability
    Each MATCH is classified by basename/extension into a PathProbe.
    """
    # Roots get a probe even if no matches inside, so the caller can warn
    # about a non-existent root path.
    probes_by_path: dict[str, PathProbe] = {
        path: PathProbe(path=path) for path in paths
    }
    command_available: dict[str, bool] = {}

    for raw_line in stdout.splitlines():
        parts = raw_line.split("\t")
        if not parts:
            continue

        record_type = parts[0]
        if record_type in {"EXIST", "PATH"} and len(parts) >= 3:
            root = parts[1]
            if root in probes_by_path:
                probes_by_path[root].exists = parts[2] == "1"
        elif record_type == "FILE" and len(parts) >= 4:
            parent_path = parts[1]
            file_marker = parts[2].lower()
            if parts[3] != "1":
                continue

            if file_marker == "pg_version":
                probe = probes_by_path.setdefault(
                    parent_path, PathProbe(path=parent_path)
                )
                probe.exists = True
                probe.pg_version_file = True
            elif file_marker == "wiredtiger":
                probe = probes_by_path.setdefault(
                    parent_path, PathProbe(path=parent_path)
                )
                probe.exists = True
                probe.wired_tiger_file = True
            elif file_marker == "dump.rdb":
                probe = probes_by_path.setdefault(
                    parent_path, PathProbe(path=parent_path)
                )
                probe.exists = True
                probe.redis_dump_file = True
            elif file_marker == "sqlite_db":
                probe = probes_by_path.setdefault(
                    parent_path, PathProbe(path=parent_path)
                )
                probe.exists = True
                probe.sqlite_database_file = True
        elif record_type == "MATCH" and len(parts) >= 2:
            match_path = parts[1]
            if not match_path:
                continue
            basename = _path_basename(match_path)
            extension = posixpath.splitext(match_path)[1].lower()

            # PG_VERSION / WiredTiger / dump.rdb are sentinel files. The
            # *parent directory* is the DB data dir; key the probe on that.
            if basename == "pg_version":
                data_dir = posixpath.dirname(match_path) or match_path
                probe = probes_by_path.setdefault(data_dir, PathProbe(path=data_dir))
                probe.exists = True
                probe.pg_version_file = True
            elif basename == "wiredtiger":
                data_dir = posixpath.dirname(match_path) or match_path
                probe = probes_by_path.setdefault(data_dir, PathProbe(path=data_dir))
                probe.exists = True
                probe.wired_tiger_file = True
            elif basename == "dump.rdb":
                data_dir = posixpath.dirname(match_path) or match_path
                probe = probes_by_path.setdefault(data_dir, PathProbe(path=data_dir))
                probe.exists = True
                probe.redis_dump_file = True
            elif extension in SQLITE_DATABASE_SUFFIXES:
                # The file itself is the DB.
                probe = probes_by_path.setdefault(
                    match_path, PathProbe(path=match_path)
                )
                probe.exists = True
                probe.sqlite_database_file = True
            elif basename in {"mysql", "mariadb"}:
                # The matched dir is itself the MySQL data dir, but it can
                # also appear as a child of /var/lib/<engine>/mysql which is
                # the historical signature. Either way, keying on the match
                # gives us a probe that _path_probe_matches_template will
                # recognise via basename.
                probe = probes_by_path.setdefault(
                    match_path, PathProbe(path=match_path)
                )
                probe.exists = True
                probe.mysql_directory = True
            elif basename in {
                "postgresql",
                "pgsql",
                "postgres",
                "mongodb",
                "mongo",
                "redis",
                "sqlite",
                "sqlite3",
            }:
                probe = probes_by_path.setdefault(
                    match_path, PathProbe(path=match_path)
                )
                probe.exists = True
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
    max_depth = (
        request.max_depth if request.max_depth is not None else DEFAULT_SCAN_MAX_DEPTH
    )
    ignore_patterns = (
        request.ignore_patterns
        if request.ignore_patterns is not None
        else list(DEFAULT_SCAN_IGNORE_PATTERNS)
    )
    script = _build_remote_probe_script(
        paths,
        _client_commands(templates),
        max_depth=max_depth,
        ignore_patterns=ignore_patterns,
    )
    timeout_seconds = (
        request.timeout_seconds
        if request.timeout_seconds is not None
        else DEFAULT_SCAN_TIMEOUT_SECONDS
    )
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


@router.get(
    "/filesystem-snapshots", response_model=FilesystemSnapshotCapabilitiesResponse
)
async def discover_filesystem_snapshot_capabilities(
    current_user: User = Depends(get_current_user),
) -> FilesystemSnapshotCapabilitiesResponse:
    del current_user
    return FilesystemSnapshotCapabilitiesResponse(
        providers=_filesystem_snapshot_provider_capabilities(),
        supported_source_types=["local"],
        unsupported_source_targets=[
            "Remote SSH sources are not supported because snapshot commands must run on the source host.",
            "Managed-agent sources are not supported in this server-side snapshot flow.",
        ],
        default_staging_path=DEFAULT_SNAPSHOT_STAGING_ROOT,
    )


@router.post("/databases/scan", response_model=DatabaseScanResponse)
async def scan_databases(
    request: DatabaseScanRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DatabaseScanResponse | JSONResponse:
    del current_user
    paths = _validate_database_scan_request(request)

    # Validation already normalised these to safe values; assert for type
    # narrowing.
    assert request.max_depth is not None
    assert request.ignore_patterns is not None
    assert request.timeout_seconds is not None

    try:
        if request.source_type == "remote":
            return await _scan_remote_database_paths(request, paths, db)
        return await _scan_local_database_paths_with_timeout(
            paths,
            max_depth=request.max_depth,
            ignore_patterns=request.ignore_patterns,
            timeout_seconds=request.timeout_seconds,
        )
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
