"""Add Backup Plans tables and job references."""

from sqlalchemy import text


def _table_exists(db, table_name: str) -> bool:
    result = db.execute(
        text(
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name=:table_name
            """
        ),
        {"table_name": table_name},
    )
    return result.fetchone() is not None


def _columns(db, table_name: str) -> set[str]:
    result = db.execute(text(f"PRAGMA table_info({table_name})"))
    return {row[1] for row in result.fetchall()}


def _add_column_if_missing(db, table_name: str, column_name: str, ddl: str) -> None:
    if column_name not in _columns(db, table_name):
        db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {ddl}"))


def upgrade(db):
    if not _table_exists(db, "backup_plans"):
        db.execute(
            text(
                """
                CREATE TABLE backup_plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR NOT NULL UNIQUE,
                    description TEXT,
                    enabled BOOLEAN NOT NULL DEFAULT 1,
                    source_type VARCHAR NOT NULL DEFAULT 'local',
                    source_ssh_connection_id INTEGER REFERENCES ssh_connections(id),
                    source_directories TEXT NOT NULL,
                    exclude_patterns TEXT,
                    archive_name_template VARCHAR NOT NULL DEFAULT '{plan_name}-{now}',
                    compression VARCHAR NOT NULL DEFAULT 'lz4',
                    custom_flags TEXT,
                    upload_ratelimit_kib INTEGER,
                    repository_run_mode VARCHAR NOT NULL DEFAULT 'series',
                    max_parallel_repositories INTEGER NOT NULL DEFAULT 1,
                    failure_behavior VARCHAR NOT NULL DEFAULT 'continue',
                    schedule_enabled BOOLEAN NOT NULL DEFAULT 0,
                    cron_expression VARCHAR,
                    timezone VARCHAR NOT NULL DEFAULT 'UTC',
                    last_run DATETIME,
                    next_run DATETIME,
                    pre_backup_script_id INTEGER REFERENCES scripts(id),
                    post_backup_script_id INTEGER REFERENCES scripts(id),
                    pre_backup_script_parameters JSON,
                    post_backup_script_parameters JSON,
                    run_repository_scripts BOOLEAN NOT NULL DEFAULT 1,
                    run_prune_after BOOLEAN NOT NULL DEFAULT 0,
                    run_compact_after BOOLEAN NOT NULL DEFAULT 0,
                    run_check_after BOOLEAN NOT NULL DEFAULT 0,
                    check_max_duration INTEGER NOT NULL DEFAULT 3600,
                    prune_keep_hourly INTEGER NOT NULL DEFAULT 0,
                    prune_keep_daily INTEGER NOT NULL DEFAULT 7,
                    prune_keep_weekly INTEGER NOT NULL DEFAULT 4,
                    prune_keep_monthly INTEGER NOT NULL DEFAULT 6,
                    prune_keep_quarterly INTEGER NOT NULL DEFAULT 0,
                    prune_keep_yearly INTEGER NOT NULL DEFAULT 1,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME
                )
                """
            )
        )
        db.execute(text("CREATE INDEX ix_backup_plans_id ON backup_plans (id)"))
        db.execute(text("CREATE INDEX ix_backup_plans_name ON backup_plans (name)"))

    if not _table_exists(db, "backup_plan_repositories"):
        db.execute(
            text(
                """
                CREATE TABLE backup_plan_repositories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    backup_plan_id INTEGER NOT NULL REFERENCES backup_plans(id) ON DELETE CASCADE,
                    repository_id INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
                    enabled BOOLEAN NOT NULL DEFAULT 1,
                    execution_order INTEGER NOT NULL,
                    compression_source VARCHAR NOT NULL DEFAULT 'plan',
                    compression_override VARCHAR,
                    custom_flags_override TEXT,
                    upload_ratelimit_kib_override INTEGER,
                    failure_behavior_override VARCHAR,
                    created_at DATETIME NOT NULL,
                    UNIQUE(backup_plan_id, repository_id)
                )
                """
            )
        )
        db.execute(
            text(
                "CREATE INDEX ix_backup_plan_repositories_id ON backup_plan_repositories (id)"
            )
        )
        db.execute(
            text(
                "CREATE INDEX ix_backup_plan_repositories_backup_plan_id ON backup_plan_repositories (backup_plan_id)"
            )
        )
        db.execute(
            text(
                "CREATE INDEX ix_backup_plan_repositories_repository_id ON backup_plan_repositories (repository_id)"
            )
        )

    if _table_exists(db, "backup_plan_repositories"):
        _add_column_if_missing(
            db,
            "backup_plan_repositories",
            "compression_source",
            "compression_source VARCHAR NOT NULL DEFAULT 'plan'",
        )

    if not _table_exists(db, "backup_plan_runs"):
        db.execute(
            text(
                """
                CREATE TABLE backup_plan_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    backup_plan_id INTEGER REFERENCES backup_plans(id) ON DELETE SET NULL,
                    trigger VARCHAR NOT NULL,
                    status VARCHAR NOT NULL DEFAULT 'pending',
                    started_at DATETIME,
                    completed_at DATETIME,
                    error_message TEXT,
                    created_at DATETIME NOT NULL
                )
                """
            )
        )
        db.execute(text("CREATE INDEX ix_backup_plan_runs_id ON backup_plan_runs (id)"))
        db.execute(
            text(
                "CREATE INDEX ix_backup_plan_runs_backup_plan_id ON backup_plan_runs (backup_plan_id)"
            )
        )

    if not _table_exists(db, "backup_plan_run_repositories"):
        db.execute(
            text(
                """
                CREATE TABLE backup_plan_run_repositories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    backup_plan_run_id INTEGER NOT NULL REFERENCES backup_plan_runs(id) ON DELETE CASCADE,
                    repository_id INTEGER REFERENCES repositories(id) ON DELETE SET NULL,
                    backup_job_id INTEGER REFERENCES backup_jobs(id) ON DELETE SET NULL,
                    status VARCHAR NOT NULL DEFAULT 'pending',
                    started_at DATETIME,
                    completed_at DATETIME,
                    error_message TEXT
                )
                """
            )
        )
        db.execute(
            text(
                "CREATE INDEX ix_backup_plan_run_repositories_id ON backup_plan_run_repositories (id)"
            )
        )
        db.execute(
            text(
                "CREATE INDEX ix_backup_plan_run_repositories_backup_plan_run_id ON backup_plan_run_repositories (backup_plan_run_id)"
            )
        )
        db.execute(
            text(
                "CREATE INDEX ix_backup_plan_run_repositories_repository_id ON backup_plan_run_repositories (repository_id)"
            )
        )

    if _table_exists(db, "backup_jobs"):
        _add_column_if_missing(
            db,
            "backup_jobs",
            "repository_id",
            "repository_id INTEGER REFERENCES repositories(id) ON DELETE SET NULL",
        )
        _add_column_if_missing(
            db,
            "backup_jobs",
            "backup_plan_id",
            "backup_plan_id INTEGER REFERENCES backup_plans(id) ON DELETE SET NULL",
        )
        _add_column_if_missing(
            db,
            "backup_jobs",
            "backup_plan_run_id",
            "backup_plan_run_id INTEGER REFERENCES backup_plan_runs(id) ON DELETE SET NULL",
        )

    if _table_exists(db, "script_executions"):
        _add_column_if_missing(
            db,
            "script_executions",
            "backup_plan_id",
            "backup_plan_id INTEGER REFERENCES backup_plans(id) ON DELETE SET NULL",
        )
        _add_column_if_missing(
            db,
            "script_executions",
            "backup_plan_run_id",
            "backup_plan_run_id INTEGER REFERENCES backup_plan_runs(id) ON DELETE CASCADE",
        )
        db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_script_executions_backup_plan_id ON script_executions (backup_plan_id)"
            )
        )
        db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_script_executions_backup_plan_run_id ON script_executions (backup_plan_run_id)"
            )
        )

    db.commit()


def downgrade(db):
    # SQLite migrations in this project are additive; leave tables/columns in place.
    db.commit()
