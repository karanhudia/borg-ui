"""Add restore check scheduling fields and restore_check_jobs table."""

from sqlalchemy import text
import structlog

logger = structlog.get_logger()


def _add_column_if_missing(db, table_name: str, column_name: str, ddl: str) -> None:
    columns = [row[1] for row in db.execute(text(f"PRAGMA table_info({table_name})"))]
    if column_name not in columns:
        db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"))


def upgrade(db):
    _add_column_if_missing(
        db,
        "repositories",
        "restore_check_cron_expression",
        "VARCHAR",
    )
    _add_column_if_missing(
        db,
        "repositories",
        "restore_check_timezone",
        "VARCHAR DEFAULT 'UTC' NOT NULL",
    )
    _add_column_if_missing(
        db,
        "repositories",
        "restore_check_paths",
        "TEXT",
    )
    _add_column_if_missing(
        db,
        "repositories",
        "restore_check_full_archive",
        "BOOLEAN NOT NULL DEFAULT 0",
    )
    _add_column_if_missing(
        db,
        "repositories",
        "last_restore_check",
        "DATETIME",
    )
    _add_column_if_missing(
        db,
        "repositories",
        "last_scheduled_restore_check",
        "DATETIME",
    )
    _add_column_if_missing(
        db,
        "repositories",
        "next_scheduled_restore_check",
        "DATETIME",
    )
    _add_column_if_missing(
        db,
        "repositories",
        "notify_on_restore_check_success",
        "BOOLEAN NOT NULL DEFAULT 0",
    )
    _add_column_if_missing(
        db,
        "repositories",
        "notify_on_restore_check_failure",
        "BOOLEAN NOT NULL DEFAULT 1",
    )

    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS restore_check_jobs (
                id INTEGER PRIMARY KEY,
                repository_id INTEGER NOT NULL,
                repository_path VARCHAR,
                archive_name VARCHAR,
                status VARCHAR DEFAULT 'pending',
                started_at DATETIME,
                completed_at DATETIME,
                progress INTEGER DEFAULT 0,
                progress_message VARCHAR,
                error_message TEXT,
                logs TEXT,
                log_file_path VARCHAR,
                has_logs BOOLEAN DEFAULT 0,
                probe_paths TEXT,
                full_archive BOOLEAN NOT NULL DEFAULT 0,
                process_pid INTEGER,
                process_start_time BIGINT,
                scheduled_restore_check BOOLEAN NOT NULL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(repository_id) REFERENCES repositories(id)
            )
            """
        )
    )
    _add_column_if_missing(
        db,
        "restore_check_jobs",
        "full_archive",
        "BOOLEAN NOT NULL DEFAULT 0",
    )
    db.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_restore_check_jobs_repository_id ON restore_check_jobs(repository_id)"
        )
    )
    db.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_restore_check_jobs_status ON restore_check_jobs(status)"
        )
    )
    db.commit()
    logger.info("Migration 101_add_restore_check_jobs completed")


def downgrade(db):
    logger.warning(
        "Downgrade not supported for SQLite — restore check schema will remain"
    )
