from pathlib import Path
from shutil import which
from textwrap import dedent

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.security import get_current_user
from app.database.models import User

router = APIRouter()


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
    ]


def _detect_template(template: DatabaseCandidate) -> DatabaseCandidate | None:
    known_paths = {
        "postgresql": [Path("/var/lib/postgresql"), Path("/var/lib/pgsql")],
        "mysql": [Path("/var/lib/mysql")],
        "mongodb": [Path("/var/lib/mongodb")],
        "redis": [Path("/var/lib/redis")],
    }
    existing_path = next(
        (path for path in known_paths.get(template.id, []) if path.exists()),
        None,
    )
    available_command = next(
        (command for command in template.client_commands if which(command)),
        None,
    )

    if not existing_path and not available_command:
        return None

    detection_source = (
        str(existing_path)
        if existing_path
        else f"{available_command} available on PATH"
    )
    return template.model_copy(
        update={
            "detected": True,
            "detection_source": detection_source,
        }
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
